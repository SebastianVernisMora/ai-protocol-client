#!/usr/bin/env python3
"""
AI Protocol Dashboard Backend
Sistema backend para el monitoreo de tareas de IA distribuidas
"""

import json
import os
import subprocess
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading
import asyncio
import websockets
import signal
import sys

from flask import Flask, jsonify, request, render_template_string, send_from_directory
from flask_cors import CORS
import psutil
import paramiko

class AITaskMonitor:
    def __init__(self, workspace_path: str = "~/ai-workspace"):
        self.workspace = Path(workspace_path).expanduser()
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # Initialize directories
        for subdir in ['sessions', 'logs', 'tasks', 'results', 'configs', 'scripts']:
            (self.workspace / subdir).mkdir(exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            filename=self.workspace / 'logs' / 'monitor.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config = self.load_config()
        
        # Task and host tracking
        self.tasks = {}
        self.hosts = {}
        self.active_sessions = {}
        
        # WebSocket connections for real-time updates
        self.websocket_clients = set()
        
        # Monitoring thread
        self.monitoring_active = True
        self.monitor_thread = None
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        config_file = self.workspace / 'configs' / 'dashboard.json'
        
        default_config = {
            "refresh_interval": 30,
            "ssh_hosts": [
                {
                    "id": "server1",
                    "name": "Production Server 1",
                    "host": "192.168.1.100",
                    "port": 22,
                    "username": "ai-user",
                    "key_file": "~/.ssh/id_rsa"
                },
                {
                    "id": "server2", 
                    "name": "Development Server",
                    "host": "192.168.1.101",
                    "port": 22,
                    "username": "ai-user",
                    "key_file": "~/.ssh/id_rsa"
                }
            ],
            "ai_tools": {
                "crush": {
                    "command": "crush",
                    "env_setup": "source ~/.bashrc"
                },
                "blackbox": {
                    "command": "blackbox-cli",
                    "env_setup": "blackbox-cli auth"
                },
                "qwen": {
                    "command": "qwen-cli",
                    "env_setup": "source ~/qwen-env/bin/activate"
                },
                "gemini": {
                    "command": "gemini-cli",
                    "env_setup": "export GEMINI_API_KEY=$GEMINI_KEY"
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
    
    def save_config(self):
        """Save current configuration"""
        config_file = self.workspace / 'configs' / 'dashboard.json'
        with open(config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def create_task(self, task_config: Dict[str, Any]) -> str:
        """Create a new AI task"""
        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(self.tasks)}"
        
        task = {
            "id": task_id,
            "tool": task_config.get("tool"),
            "host": task_config.get("host"),
            "command": task_config.get("command"),
            "parameters": task_config.get("parameters", {}),
            "priority": task_config.get("priority", "medium"),
            "status": "queued",
            "progress": 0,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_message": None,
            "session_name": f"ai-{task_id}",
            "log_file": self.workspace / 'logs' / f'{task_id}.log'
        }
        
        self.tasks[task_id] = task
        self.save_task(task)
        
        self.logger.info(f"Task {task_id} created")
        return task_id
    
    def save_task(self, task: Dict[str, Any]):
        """Save task to file"""
        task_file = self.workspace / 'tasks' / f"{task['id']}.json"
        
        # Convert Path objects to strings for JSON serialization
        task_copy = task.copy()
        if 'log_file' in task_copy:
            task_copy['log_file'] = str(task_copy['log_file'])
        
        with open(task_file, 'w') as f:
            json.dump(task_copy, f, indent=2)
    
    def execute_task(self, task_id: str) -> bool:
        """Execute a task on remote host"""
        if task_id not in self.tasks:
            self.logger.error(f"Task {task_id} not found")
            return False
        
        task = self.tasks[task_id]
        host_config = self.get_host_config(task['host'])
        
        if not host_config:
            self.logger.error(f"Host {task['host']} not configured")
            task['status'] = 'failed'
            task['error_message'] = 'Host not configured'
            return False
        
        try:
            # Connect to SSH host
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            key_file = Path(host_config['key_file']).expanduser()
            ssh.connect(
                hostname=host_config['host'],
                port=host_config['port'],
                username=host_config['username'],
                key_filename=str(key_file)
            )
            
            # Create tmux session and execute task
            session_name = task['session_name']
            tool_config = self.config['ai_tools'][task['tool']]
            
            commands = [
                f"tmux new-session -d -s {session_name}",
                f"tmux send-keys -t {session_name} '{tool_config['env_setup']}' Enter",
                f"tmux send-keys -t {session_name} 'mkdir -p ~/ai-workspace/logs' Enter",
                f"tmux send-keys -t {session_name} 'exec > >(tee ~/ai-workspace/logs/{task_id}.log)' Enter",
                f"tmux send-keys -t {session_name} 'exec 2>&1' Enter"
            ]
            
            # Add task-specific command
            task_command = self.build_task_command(task)
            commands.append(f"tmux send-keys -t {session_name} '{task_command}' Enter")
            
            for cmd in commands:
                stdin, stdout, stderr = ssh.exec_command(cmd)
                stdout.read()  # Wait for command completion
            
            ssh.close()
            
            # Update task status
            task['status'] = 'running'
            task['started_at'] = datetime.now().isoformat()
            self.save_task(task)
            
            self.logger.info(f"Task {task_id} started on {task['host']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to execute task {task_id}: {e}")
            task['status'] = 'failed'
            task['error_message'] = str(e)
            self.save_task(task)
            return False
    
    def build_task_command(self, task: Dict[str, Any]) -> str:
        """Build the command string for the task"""
        tool = task['tool']
        command = task['command']
        params = task.get('parameters', {})
        
        tool_config = self.config['ai_tools'][tool]
        base_command = tool_config['command']
        
        # Build parameter string
        param_str = ""
        if params:
            if tool == 'crush':
                # Crush uses command-line arguments
                for key, value in params.items():
                    param_str += f" --{key} {value}"
            else:
                # Other tools might use JSON config files
                config_file = f"~/ai-workspace/configs/{task['id']}_params.json"
                param_str = f" --config {config_file}"
                # We'd need to upload the config file separately
        
        return f"{base_command} {command}{param_str}"
    
    def get_host_config(self, host_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific host"""
        for host in self.config['ssh_hosts']:
            if host['id'] == host_id:
                return host
        return None
    
    def monitor_tasks(self):
        """Monitor running tasks"""
        while self.monitoring_active:
            try:
                for task_id, task in self.tasks.items():
                    if task['status'] == 'running':
                        self.check_task_status(task_id)
                
                # Monitor host status
                self.update_host_status()
                
                # Broadcast updates to WebSocket clients
                self.broadcast_updates()
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(self.config['refresh_interval'])
    
    def check_task_status(self, task_id: str):
        """Check status of a running task"""
        task = self.tasks[task_id]
        host_config = self.get_host_config(task['host'])
        
        if not host_config:
            return
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            key_file = Path(host_config['key_file']).expanduser()
            ssh.connect(
                hostname=host_config['host'],
                port=host_config['port'],
                username=host_config['username'],
                key_filename=str(key_file)
            )
            
            # Check if tmux session exists
            session_name = task['session_name']
            stdin, stdout, stderr = ssh.exec_command(f"tmux has-session -t {session_name}")
            
            if stdout.channel.recv_exit_status() != 0:
                # Session ended, task is complete or failed
                self.finalize_task(task_id, ssh)
            else:
                # Task is still running, update progress if possible
                self.update_task_progress(task_id, ssh)
            
            ssh.close()
            
        except Exception as e:
            self.logger.error(f"Error checking task {task_id}: {e}")
    
    def finalize_task(self, task_id: str, ssh: paramiko.SSHClient):
        """Finalize a completed task"""
        task = self.tasks[task_id]
        
        try:
            # Get the exit status from logs or session
            stdin, stdout, stderr = ssh.exec_command(f"cat ~/ai-workspace/logs/{task_id}.log | tail -20")
            log_output = stdout.read().decode()
            
            # Simple heuristic to determine if task succeeded
            if any(keyword in log_output.lower() for keyword in ['error', 'failed', 'exception']):
                task['status'] = 'failed'
                # Extract error message from logs
                error_lines = [line for line in log_output.split('\n') if 'error' in line.lower()]
                if error_lines:
                    task['error_message'] = error_lines[-1]
            else:
                task['status'] = 'completed'
                task['progress'] = 100
            
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
            
            self.logger.info(f"Task {task_id} finalized with status: {task['status']}")
            
        except Exception as e:
            self.logger.error(f"Error finalizing task {task_id}: {e}")
            task['status'] = 'failed'
            task['error_message'] = f"Finalization error: {str(e)}"
    
    def update_task_progress(self, task_id: str, ssh: paramiko.SSHClient):
        """Update task progress from logs"""
        try:
            # Look for progress indicators in logs
            stdin, stdout, stderr = ssh.exec_command(f"grep -i 'progress\\|%' ~/ai-workspace/logs/{task_id}.log | tail -1")
            progress_line = stdout.read().decode().strip()
            
            if progress_line:
                # Extract percentage from progress line
                import re
                percentage_match = re.search(r'(\d+)%', progress_line)
                if percentage_match:
                    progress = int(percentage_match.group(1))
                    self.tasks[task_id]['progress'] = min(progress, 99)  # Don't set to 100 until actually complete
                    
        except Exception as e:
            self.logger.debug(f"Could not update progress for {task_id}: {e}")
    
    def update_host_status(self):
        """Update status of all configured hosts"""
        for host_config in self.config['ssh_hosts']:
            host_id = host_config['id']
            
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                key_file = Path(host_config['key_file']).expanduser()
                ssh.connect(
                    hostname=host_config['host'],
                    port=host_config['port'],
                    username=host_config['username'],
                    key_filename=str(key_file),
                    timeout=10
                )
                
                # Get system stats
                stdin, stdout, stderr = ssh.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1")
                cpu_usage = float(stdout.read().decode().strip() or 0)
                
                stdin, stdout, stderr = ssh.exec_command("free | grep Mem | awk '{printf \"%.1f\", $3/$2 * 100.0}'")
                memory_usage = float(stdout.read().decode().strip() or 0)
                
                # Count active AI tasks
                stdin, stdout, stderr = ssh.exec_command("tmux list-sessions | grep -E 'ai-task' | wc -l")
                active_tasks = int(stdout.read().decode().strip() or 0)
                
                self.hosts[host_id] = {
                    "id": host_id,
                    "name": host_config['name'],
                    "ip": host_config['host'],
                    "status": "online",
                    "cpu": cpu_usage,
                    "memory": memory_usage,
                    "active_tasks": active_tasks,
                    "last_ping": datetime.now().isoformat()
                }
                
                ssh.close()
                
            except Exception as e:
                self.logger.warning(f"Host {host_id} check failed: {e}")
                self.hosts[host_id] = {
                    "id": host_id,
                    "name": host_config['name'],
                    "ip": host_config['host'],
                    "status": "offline",
                    "cpu": 0,
                    "memory": 0,
                    "active_tasks": 0,
                    "last_ping": datetime.now().isoformat(),
                    "error": str(e)
                }
    
    def kill_task(self, task_id: str) -> bool:
        """Kill a running task"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        if task['status'] != 'running':
            return False
        
        host_config = self.get_host_config(task['host'])
        if not host_config:
            return False
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            key_file = Path(host_config['key_file']).expanduser()
            ssh.connect(
                hostname=host_config['host'],
                port=host_config['port'], 
                username=host_config['username'],
                key_filename=str(key_file)
            )
            
            # Kill tmux session
            session_name = task['session_name']
            stdin, stdout, stderr = ssh.exec_command(f"tmux kill-session -t {session_name}")
            
            ssh.close()
            
            # Update task status
            task['status'] = 'failed'
            task['error_message'] = 'Task killed by user'
            task['completed_at'] = datetime.now().isoformat()
            self.save_task(task)
            
            self.logger.info(f"Task {task_id} killed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error killing task {task_id}: {e}")
            return False
    
    def get_task_logs(self, task_id: str) -> str:
        """Get logs for a specific task"""
        if task_id not in self.tasks:
            return "Task not found"
        
        task = self.tasks[task_id]
        host_config = self.get_host_config(task['host'])
        
        if not host_config:
            return "Host configuration not found"
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            key_file = Path(host_config['key_file']).expanduser()
            ssh.connect(
                hostname=host_config['host'],
                port=host_config['port'],
                username=host_config['username'],
                key_filename=str(key_file)
            )
            
            stdin, stdout, stderr = ssh.exec_command(f"cat ~/ai-workspace/logs/{task_id}.log")
            logs = stdout.read().decode()
            
            ssh.close()
            return logs
            
        except Exception as e:
            self.logger.error(f"Error getting logs for {task_id}: {e}")
            return f"Error retrieving logs: {str(e)}"
    
    def broadcast_updates(self):
        """Broadcast updates to WebSocket clients"""
        if not self.websocket_clients:
            return
        
        update_data = {
            "type": "status_update",
            "timestamp": datetime.now().isoformat(),
            "tasks": list(self.tasks.values()),
            "hosts": list(self.hosts.values())
        }
        
        # Remove clients that have disconnected
        disconnected = set()
        for client in self.websocket_clients:
            try:
                asyncio.create_task(client.send(json.dumps(update_data)))
            except:
                disconnected.add(client)
        
        self.websocket_clients -= disconnected
    
    def start_monitoring(self):
        """Start the monitoring thread"""
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self.monitor_tasks)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        self.logger.info("Monitoring started")
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("Monitoring stopped")


# Flask web server
app = Flask(__name__)
CORS(app)
monitor = AITaskMonitor()

@app.route('/')
def dashboard():
    """Serve the main dashboard"""
    dashboard_file = Path(__file__).parent / 'ai-monitoring-dashboard.html'
    if dashboard_file.exists():
        with open(dashboard_file, 'r') as f:
            return f.read()
    return "Dashboard not found. Make sure ai-monitoring-dashboard.html is in the same directory."

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get all tasks"""
    return jsonify(list(monitor.tasks.values()))

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Create a new task"""
    task_config = request.json
    task_id = monitor.create_task(task_config)
    
    # Auto-execute if requested
    if task_config.get('auto_execute', False):
        monitor.execute_task(task_id)
    
    return jsonify({"task_id": task_id, "status": "created"})

@app.route('/api/tasks/<task_id>/execute', methods=['POST'])
def execute_task(task_id):
    """Execute a specific task"""
    success = monitor.execute_task(task_id)
    return jsonify({"success": success})

@app.route('/api/tasks/<task_id>/kill', methods=['POST'])
def kill_task(task_id):
    """Kill a running task"""
    success = monitor.kill_task(task_id)
    return jsonify({"success": success})

@app.route('/api/tasks/<task_id>/logs', methods=['GET'])
def get_task_logs(task_id):
    """Get logs for a task"""
    logs = monitor.get_task_logs(task_id)
    return jsonify({"logs": logs})

@app.route('/api/hosts', methods=['GET'])
def get_hosts():
    """Get all hosts status"""
    return jsonify(list(monitor.hosts.values()))

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get system statistics"""
    stats = {
        "active_tasks": len([t for t in monitor.tasks.values() if t['status'] == 'running']),
        "completed_today": len([t for t in monitor.tasks.values() if t['status'] == 'completed' and 
                               datetime.fromisoformat(t.get('completed_at', '1970-01-01')).date() == datetime.now().date()]),
        "online_hosts": len([h for h in monitor.hosts.values() if h['status'] == 'online']),
        "total_tasks": len(monitor.tasks),
        "total_hosts": len(monitor.hosts)
    }
    return jsonify(stats)

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify(monitor.config)

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration"""
    new_config = request.json
    monitor.config.update(new_config)
    monitor.save_config()
    return jsonify({"status": "updated"})

# WebSocket handler for real-time updates
async def websocket_handler(websocket, path):
    """Handle WebSocket connections for real-time updates"""
    monitor.websocket_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        monitor.websocket_clients.discard(websocket)

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print("Shutting down AI Dashboard...")
    monitor.stop_monitoring()
    sys.exit(0)

if __name__ == '__main__':
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start monitoring
    monitor.start_monitoring()
    
    # Start WebSocket server
    start_server = websockets.serve(websocket_handler, "localhost", 8765)
    asyncio.get_event_loop().run_until_complete(start_server)
    
    # Start Flask app
    print("Starting AI Dashboard Backend...")
    print("Dashboard: http://localhost:5000")
    print("WebSocket: ws://localhost:8765")
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)