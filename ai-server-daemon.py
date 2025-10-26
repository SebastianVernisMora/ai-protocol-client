#!/usr/bin/env python3
"""
AI Server Daemon - Demonio que se ejecuta en servidores SSH remotos
Este script se instala en cada servidor y maneja tareas de IA de forma independiente
"""

import json
import os
import subprocess
import time
import logging
import signal
import sys
import threading
import queue
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import psutil
import socket
import fcntl

class AIServerDaemon:
    def __init__(self, workspace_path: str = "~/ai-workspace"):
        self.workspace = Path(workspace_path).expanduser()
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        for subdir in ['tasks', 'logs', 'sessions', 'results', 'configs', 'pid']:
            (self.workspace / subdir).mkdir(exist_ok=True)
        
        # Setup logging
        log_file = self.workspace / 'logs' / 'daemon.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config = self.load_config()
        
        # Task management
        self.tasks = {}
        self.task_queue = queue.Queue()
        self.running = True
        
        # Lock file for single instance
        self.lock_file = self.workspace / 'pid' / 'daemon.lock'
        self.lock_fd = None
        
        # Worker threads
        self.worker_threads = []
        self.monitor_thread = None
        
    def load_config(self) -> Dict[str, Any]:
        """Load daemon configuration"""
        config_file = self.workspace / 'configs' / 'daemon.json'
        
        default_config = {
            "max_concurrent_tasks": 4,
            "task_timeout": 3600,  # 1 hour default
            "cleanup_interval": 300,  # 5 minutes
            "heartbeat_interval": 30,
            "log_retention_days": 7,
            "ai_tools": {
                "crush": {
                    "command": "crush",
                    "env_setup": ["source ~/.bashrc"],
                    "working_dir": "~/projects",
                    "timeout": 1800
                },
                "blackbox": {
                    "command": "blackbox-cli",
                    "env_setup": ["blackbox-cli auth"],
                    "working_dir": "~/projects",
                    "timeout": 900
                },
                "qwen": {
                    "command": "qwen-cli",
                    "env_setup": ["source ~/qwen-env/bin/activate"],
                    "working_dir": "~/projects",
                    "timeout": 2400
                },
                "gemini": {
                    "command": "gemini-cli",
                    "env_setup": ["export GEMINI_API_KEY=$GEMINI_KEY"],
                    "working_dir": "~/projects",
                    "timeout": 1200
                }
            }
        }
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")
        
        return default_config
    
    def acquire_lock(self) -> bool:
        """Acquire lock to ensure single instance"""
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return True
        except (OSError, IOError):
            return False
    
    def release_lock(self):
        """Release the lock file"""
        if self.lock_fd:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()
            if self.lock_file.exists():
                self.lock_file.unlink()
    
    def create_task(self, task_request: Dict[str, Any]) -> str:
        """Create a new task and add to queue"""
        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        task = {
            "id": task_id,
            "tool": task_request.get("tool"),
            "command": task_request.get("command"),
            "parameters": task_request.get("parameters", {}),
            "working_dir": task_request.get("working_dir"),
            "priority": task_request.get("priority", "medium"),
            "timeout": task_request.get("timeout"),
            "status": "queued",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "session_name": f"ai-{task_id}",
            "log_file": str(self.workspace / 'logs' / f'{task_id}.log'),
            "result_file": str(self.workspace / 'results' / f'{task_id}.json'),
            "pid": None
        }
        
        # Validate task
        if not self.validate_task(task):
            raise ValueError(f"Invalid task configuration")
        
        # Save task to disk
        self.save_task(task)
        self.tasks[task_id] = task
        
        # Add to queue
        self.task_queue.put(task_id)
        
        self.logger.info(f"Task {task_id} created and queued")
        return task_id
    
    def validate_task(self, task: Dict[str, Any]) -> bool:
        """Validate task configuration"""
        required_fields = ['tool', 'command']
        for field in required_fields:
            if not task.get(field):
                self.logger.error(f"Task missing required field: {field}")
                return False
        
        if task['tool'] not in self.config['ai_tools']:
            self.logger.error(f"Unknown tool: {task['tool']}")
            return False
        
        return True
    
    def save_task(self, task: Dict[str, Any]):
        """Save task to disk"""
        task_file = self.workspace / 'tasks' / f"{task['id']}.json"
        with open(task_file, 'w') as f:
            json.dump(task, f, indent=2)
    
    def load_tasks(self):
        """Load existing tasks from disk"""
        tasks_dir = self.workspace / 'tasks'
        for task_file in tasks_dir.glob('*.json'):
            try:
                with open(task_file, 'r') as f:
                    task = json.load(f)
                    self.tasks[task['id']] = task
                    
                    # Re-queue unfinished tasks
                    if task['status'] in ['queued', 'running']:
                        if task['status'] == 'running':
                            # Check if process is still running
                            if not self.is_task_running(task):
                                task['status'] = 'failed'
                                task['error_message'] = 'Process died unexpectedly'
                                task['completed_at'] = datetime.now().isoformat()
                                self.save_task(task)
                            else:
                                self.logger.info(f"Recovered running task: {task['id']}")
                        else:
                            self.task_queue.put(task['id'])
                            self.logger.info(f"Re-queued task: {task['id']}")
                            
            except Exception as e:
                self.logger.error(f"Error loading task {task_file}: {e}")
    
    def is_task_running(self, task: Dict[str, Any]) -> bool:
        """Check if task process is still running"""
        if not task.get('pid'):
            return False
        
        try:
            # Check if tmux session exists
            result = subprocess.run(
                ['tmux', 'has-session', '-t', task['session_name']],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def execute_task(self, task_id: str) -> bool:
        """Execute a task in tmux session"""
        if task_id not in self.tasks:
            self.logger.error(f"Task {task_id} not found")
            return False
        
        task = self.tasks[task_id]
        
        try:
            # Update task status
            task['status'] = 'running'
            task['started_at'] = datetime.now().isoformat()
            self.save_task(task)
            
            # Get tool configuration
            tool_config = self.config['ai_tools'][task['tool']]
            
            # Determine working directory
            work_dir = task.get('working_dir') or tool_config.get('working_dir', '~')
            work_dir = Path(work_dir).expanduser()
            
            # Create tmux session
            session_name = task['session_name']
            
            # Kill session if it already exists
            subprocess.run(['tmux', 'kill-session', '-t', session_name], 
                          capture_output=True)
            
            # Create new session
            subprocess.run([
                'tmux', 'new-session', '-d', '-s', session_name,
                '-c', str(work_dir)
            ], check=True)
            
            # Setup logging in session
            log_setup_commands = [
                f"mkdir -p {self.workspace}/logs",
                f"exec > >(tee {task['log_file']})",
                "exec 2>&1",
                f"echo '[{datetime.now()}] Starting task {task_id}'"
            ]
            
            for cmd in log_setup_commands:
                subprocess.run([
                    'tmux', 'send-keys', '-t', session_name, cmd, 'Enter'
                ], check=True)
                time.sleep(0.1)
            
            # Environment setup
            for env_cmd in tool_config.get('env_setup', []):
                subprocess.run([
                    'tmux', 'send-keys', '-t', session_name, env_cmd, 'Enter'
                ], check=True)
                time.sleep(0.5)
            
            # Build and execute task command
            task_command = self.build_task_command(task)
            subprocess.run([
                'tmux', 'send-keys', '-t', session_name, task_command, 'Enter'
            ], check=True)
            
            # Add completion marker command
            completion_cmd = f"echo '[TASK_COMPLETED:{task_id}:{datetime.now().isoformat()}]'"
            subprocess.run([
                'tmux', 'send-keys', '-t', session_name, 
                f"{task_command} && {completion_cmd} || echo '[TASK_FAILED:{task_id}:{datetime.now().isoformat()}]'",
                'Enter'
            ], check=True)
            
            self.logger.info(f"Task {task_id} started in session {session_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to start task {task_id}: {e}")
            task['status'] = 'failed'
            task['error_message'] = f"Failed to start: {str(e)}"
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error starting task {task_id}: {e}")
            task['status'] = 'failed'
            task['error_message'] = f"Unexpected error: {str(e)}"
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
            return False
    
    def build_task_command(self, task: Dict[str, Any]) -> str:
        """Build the command string for execution"""
        tool_config = self.config['ai_tools'][task['tool']]
        base_command = tool_config['command']
        command = task['command']
        parameters = task.get('parameters', {})
        
        # Build parameter string based on tool type
        param_str = ""
        if parameters:
            if task['tool'] == 'crush':
                # Crush uses command-line arguments
                for key, value in parameters.items():
                    param_str += f" --{key} '{value}'"
            elif task['tool'] in ['blackbox', 'qwen', 'gemini']:
                # Create config file for other tools
                config_file = self.workspace / 'configs' / f"{task['id']}_params.json"
                with open(config_file, 'w') as f:
                    json.dump(parameters, f, indent=2)
                param_str = f" --config {config_file}"
        
        # Set timeout if specified
        timeout = task.get('timeout') or tool_config.get('timeout')
        if timeout:
            return f"timeout {timeout} {base_command} {command}{param_str}"
        else:
            return f"{base_command} {command}{param_str}"
    
    def monitor_tasks(self):
        """Monitor running tasks for completion"""
        while self.running:
            try:
                for task_id, task in list(self.tasks.items()):
                    if task['status'] == 'running':
                        self.check_task_completion(task_id)
                
                # Cleanup old completed tasks
                self.cleanup_old_tasks()
                
            except Exception as e:
                self.logger.error(f"Error in monitor loop: {e}")
            
            time.sleep(self.config['heartbeat_interval'])
    
    def check_task_completion(self, task_id: str):
        """Check if a running task has completed"""
        task = self.tasks[task_id]
        
        try:
            # Check if tmux session still exists
            result = subprocess.run(
                ['tmux', 'has-session', '-t', task['session_name']],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                # Session ended, check logs for completion status
                self.finalize_task_from_logs(task_id)
                return
            
            # Check for timeout
            if task.get('started_at'):
                started = datetime.fromisoformat(task['started_at'])
                timeout = task.get('timeout') or self.config['ai_tools'][task['tool']].get('timeout', 3600)
                
                if datetime.now() - started > timedelta(seconds=timeout):
                    self.logger.warning(f"Task {task_id} timed out")
                    self.kill_task(task_id, reason="timeout")
            
        except Exception as e:
            self.logger.error(f"Error checking task {task_id}: {e}")
    
    def finalize_task_from_logs(self, task_id: str):
        """Finalize task by checking its logs"""
        task = self.tasks[task_id]
        log_file = Path(task['log_file'])
        
        try:
            if log_file.exists():
                with open(log_file, 'r') as f:
                    log_content = f.read()
                
                # Look for completion markers
                if f'[TASK_COMPLETED:{task_id}:' in log_content:
                    task['status'] = 'completed'
                    task['progress'] = 100
                    # Extract completion time from log
                    import re
                    match = re.search(f'\\[TASK_COMPLETED:{task_id}:([^\\]]+)\\]', log_content)
                    if match:
                        task['completed_at'] = match.group(1)
                    else:
                        task['completed_at'] = datetime.now().isoformat()
                        
                elif f'[TASK_FAILED:{task_id}:' in log_content:
                    task['status'] = 'failed'
                    # Extract error from logs
                    error_lines = [line for line in log_content.split('\n') 
                                 if any(keyword in line.lower() for keyword in ['error', 'failed', 'exception'])]
                    if error_lines:
                        task['error_message'] = error_lines[-1][:500]  # Limit error message length
                    task['completed_at'] = datetime.now().isoformat()
                    
                else:
                    # No explicit completion marker, assume failure
                    task['status'] = 'failed'
                    task['error_message'] = 'Task ended without completion marker'
                    task['completed_at'] = datetime.now().isoformat()
                
                # Try to extract progress from logs
                self.extract_progress_from_logs(task_id, log_content)
                
            else:
                task['status'] = 'failed'
                task['error_message'] = 'Log file not found'
                task['completed_at'] = datetime.now().isoformat()
            
            self.save_task(task)
            self.logger.info(f"Task {task_id} finalized with status: {task['status']}")
            
        except Exception as e:
            self.logger.error(f"Error finalizing task {task_id}: {e}")
            task['status'] = 'failed'
            task['error_message'] = f"Finalization error: {str(e)}"
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
    
    def extract_progress_from_logs(self, task_id: str, log_content: str):
        """Extract progress information from task logs"""
        task = self.tasks[task_id]
        
        try:
            # Look for various progress patterns
            import re
            
            # Pattern 1: "Progress: 65%"
            progress_matches = re.findall(r'[Pp]rogress:?\s*(\d+)%', log_content)
            if progress_matches:
                task['progress'] = int(progress_matches[-1])
                return
            
            # Pattern 2: "65% complete"
            complete_matches = re.findall(r'(\d+)%\s+complete', log_content)
            if complete_matches:
                task['progress'] = int(complete_matches[-1])
                return
            
            # Pattern 3: "Processing file 45 of 100"
            file_matches = re.findall(r'Processing.*?(\d+)\s+of\s+(\d+)', log_content)
            if file_matches:
                current, total = map(int, file_matches[-1])
                task['progress'] = int((current / total) * 100)
                return
                
        except Exception as e:
            self.logger.debug(f"Could not extract progress for {task_id}: {e}")
    
    def kill_task(self, task_id: str, reason: str = "manual"):
        """Kill a running task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        
        try:
            # Kill tmux session
            subprocess.run(['tmux', 'kill-session', '-t', task['session_name']], 
                          capture_output=True)
            
            # Update task status
            task['status'] = 'failed'
            task['error_message'] = f'Task killed: {reason}'
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
            
            self.logger.info(f"Task {task_id} killed ({reason})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error killing task {task_id}: {e}")
            return False
    
    def cleanup_old_tasks(self):
        """Clean up old completed tasks"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config['log_retention_days'])
            
            for task_id, task in list(self.tasks.items()):
                if task['status'] in ['completed', 'failed'] and task.get('completed_at'):
                    completed_at = datetime.fromisoformat(task['completed_at'])
                    if completed_at < cutoff_date:
                        # Remove old task files
                        task_file = self.workspace / 'tasks' / f"{task_id}.json"
                        if task_file.exists():
                            task_file.unlink()
                        
                        # Optionally remove old logs
                        log_file = Path(task['log_file'])
                        if log_file.exists():
                            log_file.unlink()
                        
                        # Remove from memory
                        del self.tasks[task_id]
                        
                        self.logger.info(f"Cleaned up old task: {task_id}")
                        
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def worker(self):
        """Worker thread to process task queue"""
        while self.running:
            try:
                # Get task from queue with timeout
                task_id = self.task_queue.get(timeout=1)
                
                if task_id in self.tasks:
                    self.execute_task(task_id)
                
                self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Worker error: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get daemon status"""
        status = {
            "daemon_pid": os.getpid(),
            "uptime": time.time() - self.start_time if hasattr(self, 'start_time') else 0,
            "task_counts": {
                "queued": len([t for t in self.tasks.values() if t['status'] == 'queued']),
                "running": len([t for t in self.tasks.values() if t['status'] == 'running']),
                "completed": len([t for t in self.tasks.values() if t['status'] == 'completed']),
                "failed": len([t for t in self.tasks.values() if t['status'] == 'failed'])
            },
            "system": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent
            },
            "queue_size": self.task_queue.qsize(),
            "active_sessions": self.count_active_sessions()
        }
        return status
    
    def count_active_sessions(self) -> int:
        """Count active tmux sessions"""
        try:
            result = subprocess.run(['tmux', 'list-sessions'], capture_output=True, text=True)
            if result.returncode == 0:
                return len([line for line in result.stdout.split('\n') if 'ai-task' in line])
        except:
            pass
        return 0
    
    def start(self):
        """Start the daemon"""
        if not self.acquire_lock():
            self.logger.error("Another daemon instance is already running")
            return False
        
        self.logger.info("Starting AI Server Daemon")
        self.start_time = time.time()
        
        try:
            # Load existing tasks
            self.load_tasks()
            
            # Start worker threads
            for i in range(self.config['max_concurrent_tasks']):
                worker_thread = threading.Thread(target=self.worker, daemon=True)
                worker_thread.start()
                self.worker_threads.append(worker_thread)
            
            # Start monitor thread
            self.monitor_thread = threading.Thread(target=self.monitor_tasks, daemon=True)
            self.monitor_thread.start()
            
            self.logger.info(f"Daemon started with {self.config['max_concurrent_tasks']} workers")
            
            # Main loop
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Daemon error: {e}")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the daemon"""
        self.logger.info("Shutting down daemon")
        self.running = False
        
        # Wait for workers to finish
        for thread in self.worker_threads:
            thread.join(timeout=5)
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.release_lock()
        self.logger.info("Daemon shutdown complete")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global daemon
    if daemon:
        daemon.shutdown()
    sys.exit(0)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Server Daemon')
    parser.add_argument('command', choices=['start', 'stop', 'status', 'create-task'], 
                       help='Daemon command')
    parser.add_argument('--workspace', default='~/ai-workspace', 
                       help='Workspace directory')
    parser.add_argument('--tool', help='AI tool (for create-task)')
    parser.add_argument('--command-name', help='Command to execute (for create-task)')
    parser.add_argument('--params', help='JSON parameters (for create-task)')
    parser.add_argument('--priority', default='medium', choices=['low', 'medium', 'high', 'critical'],
                       help='Task priority (for create-task)')
    
    args = parser.parse_args()
    
    daemon = AIServerDaemon(args.workspace)
    
    if args.command == 'start':
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        daemon.start()
        
    elif args.command == 'stop':
        # Send stop signal to running daemon
        pid_file = daemon.workspace / 'pid' / 'daemon.lock'
        if pid_file.exists():
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"Stop signal sent to daemon (PID: {pid})")
            except (ValueError, ProcessLookupError):
                print("No running daemon found")
        else:
            print("Daemon not running")
    
    elif args.command == 'status':
        try:
            status = daemon.get_status()
            print(json.dumps(status, indent=2))
        except Exception as e:
            print(f"Error getting status: {e}")
    
    elif args.command == 'create-task':
        if not args.tool or not args.command_name:
            print("--tool and --command-name are required for create-task")
            sys.exit(1)
        
        task_request = {
            "tool": args.tool,
            "command": args.command_name,
            "priority": args.priority
        }
        
        if args.params:
            try:
                task_request["parameters"] = json.loads(args.params)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON parameters: {e}")
                sys.exit(1)
        
        try:
            task_id = daemon.create_task(task_request)
            print(f"Task created: {task_id}")
        except Exception as e:
            print(f"Error creating task: {e}")
            sys.exit(1)