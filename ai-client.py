#!/usr/bin/env python3
"""
AI Client - Cliente para enviar tareas a servidores SSH remotos
Este script se ejecuta en tu máquina local y envía tareas a los servidores
"""

import json
import argparse
import paramiko
import time
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

class AIClient:
    def __init__(self, config_file: str = "~/.ai-client-config.json"):
        self.config_file = Path(config_file).expanduser()
        self.config = self.load_config()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> Dict[str, Any]:
        """Load client configuration"""
        default_config = {
            "servers": {
                "server1": {
                    "name": "Servidor Producción",
                    "host": "192.168.1.100",
                    "port": 22,
                    "username": "ai-user",
                    "key_file": "~/.ssh/id_rsa",
                    "workspace": "~/ai-workspace"
                },
                "server2": {
                    "name": "Servidor Desarrollo", 
                    "host": "192.168.1.101",
                    "port": 22,
                    "username": "ai-user", 
                    "key_file": "~/.ssh/id_rsa",
                    "workspace": "~/ai-workspace"
                }
            },
            "default_server": "server1",
            "connection_timeout": 30,
            "command_timeout": 10
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")
        else:
            # Save default config
            self.save_config(default_config)
        
        return default_config
    
    def save_config(self, config: Dict[str, Any] = None):
        """Save configuration to file"""
        config = config or self.config
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def connect_to_server(self, server_id: str) -> paramiko.SSHClient:
        """Establish SSH connection to server"""
        if server_id not in self.config['servers']:
            raise ValueError(f"Server '{server_id}' not found in configuration")
        
        server_config = self.config['servers'][server_id]
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            key_file = Path(server_config['key_file']).expanduser()
            ssh.connect(
                hostname=server_config['host'],
                port=server_config['port'],
                username=server_config['username'],
                key_filename=str(key_file),
                timeout=self.config['connection_timeout']
            )
            
            self.logger.info(f"Connected to {server_config['name']} ({server_config['host']})")
            return ssh
            
        except Exception as e:
            self.logger.error(f"Failed to connect to {server_id}: {e}")
            raise
    
    def ensure_daemon_running(self, ssh: paramiko.SSHClient, workspace: str) -> bool:
        """Ensure AI daemon is running on the server"""
        try:
            # Check if daemon is running
            stdin, stdout, stderr = ssh.exec_command(
                f"python3 {workspace}/scripts/ai-server-daemon.py status",
                timeout=self.config['command_timeout']
            )
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                self.logger.info("AI daemon is already running")
                return True
            
            # Start daemon if not running
            self.logger.info("Starting AI daemon on server...")
            stdin, stdout, stderr = ssh.exec_command(
                f"nohup python3 {workspace}/scripts/ai-server-daemon.py start > {workspace}/logs/daemon-startup.log 2>&1 &",
                timeout=self.config['command_timeout']
            )
            
            # Wait a moment for daemon to start
            time.sleep(2)
            
            # Check if it started successfully
            stdin, stdout, stderr = ssh.exec_command(
                f"python3 {workspace}/scripts/ai-server-daemon.py status",
                timeout=self.config['command_timeout']
            )
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                self.logger.info("AI daemon started successfully")
                return True
            else:
                error_output = stderr.read().decode().strip()
                self.logger.error(f"Failed to start daemon: {error_output}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error managing daemon: {e}")
            return False
    
    def create_task(self, server_id: str, tool: str, command: str, 
                   parameters: Dict[str, Any] = None, priority: str = "medium",
                   working_dir: str = None, timeout: int = None) -> Optional[str]:
        """Create a task on remote server"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            # Ensure daemon is running
            if not self.ensure_daemon_running(ssh, workspace):
                return None
            
            # Build task parameters
            params_json = json.dumps(parameters or {})
            
            # Create task command
            task_cmd_parts = [
                f"python3 {workspace}/scripts/ai-server-daemon.py create-task",
                f"--tool {tool}",
                f"--command-name '{command}'", 
                f"--priority {priority}"
            ]
            
            if parameters:
                task_cmd_parts.append(f"--params '{params_json}'")
            
            task_cmd = " ".join(task_cmd_parts)
            
            # Execute task creation
            stdin, stdout, stderr = ssh.exec_command(task_cmd, timeout=self.config['command_timeout'])
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                output = stdout.read().decode().strip()
                # Extract task ID from output
                if "Task created:" in output:
                    task_id = output.split("Task created:")[1].strip()
                    self.logger.info(f"Task {task_id} created successfully on {server_id}")
                    ssh.close()
                    return task_id
                else:
                    self.logger.error(f"Unexpected output: {output}")
            else:
                error_output = stderr.read().decode().strip()
                self.logger.error(f"Failed to create task: {error_output}")
            
            ssh.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error creating task: {e}")
            return None
    
    def get_server_status(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get status from remote server"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            # Get daemon status
            stdin, stdout, stderr = ssh.exec_command(
                f"python3 {workspace}/scripts/ai-server-daemon.py status",
                timeout=self.config['command_timeout']
            )
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                status_json = stdout.read().decode().strip()
                status = json.loads(status_json)
                ssh.close()
                return status
            else:
                error_output = stderr.read().decode().strip()
                self.logger.error(f"Failed to get status: {error_output}")
            
            ssh.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting server status: {e}")
            return None
    
    def get_task_logs(self, server_id: str, task_id: str) -> Optional[str]:
        """Get logs for a specific task"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            # Get task logs
            stdin, stdout, stderr = ssh.exec_command(
                f"cat {workspace}/logs/{task_id}.log",
                timeout=self.config['command_timeout']
            )
            
            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                logs = stdout.read().decode()
                ssh.close()
                return logs
            else:
                self.logger.error(f"Task log file not found for {task_id}")
            
            ssh.close()
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting task logs: {e}")
            return None
    
    def list_tasks(self, server_id: str, status_filter: str = None) -> List[Dict[str, Any]]:
        """List tasks on remote server"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            # List task files
            stdin, stdout, stderr = ssh.exec_command(
                f"find {workspace}/tasks -name '*.json' -type f",
                timeout=self.config['command_timeout']
            )
            
            task_files = stdout.read().decode().strip().split('\n')
            tasks = []
            
            for task_file in task_files:
                if task_file.strip():
                    # Read task file
                    stdin, stdout, stderr = ssh.exec_command(
                        f"cat '{task_file}'",
                        timeout=self.config['command_timeout']
                    )
                    
                    if stdout.channel.recv_exit_status() == 0:
                        try:
                            task_data = json.loads(stdout.read().decode())
                            if not status_filter or task_data.get('status') == status_filter:
                                tasks.append(task_data)
                        except json.JSONDecodeError:
                            continue
            
            ssh.close()
            return sorted(tasks, key=lambda x: x.get('created_at', ''), reverse=True)
            
        except Exception as e:
            self.logger.error(f"Error listing tasks: {e}")
            return []
    
    def kill_task(self, server_id: str, task_id: str) -> bool:
        """Kill a running task on remote server"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            # Kill task
            stdin, stdout, stderr = ssh.exec_command(
                f"tmux kill-session -t ai-{task_id}",
                timeout=self.config['command_timeout']
            )
            
            ssh.close()
            self.logger.info(f"Task {task_id} killed on {server_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error killing task: {e}")
            return False
    
    def install_on_server(self, server_id: str) -> bool:
        """Install AI daemon on remote server"""
        try:
            ssh = self.connect_to_server(server_id)
            server_config = self.config['servers'][server_id]
            workspace = server_config['workspace']
            
            self.logger.info(f"Installing AI daemon on {server_id}...")
            
            # Create workspace directories
            stdin, stdout, stderr = ssh.exec_command(
                f"mkdir -p {workspace}/{{scripts,logs,tasks,results,configs,pid}}",
                timeout=self.config['command_timeout']
            )
            
            # Upload daemon script
            daemon_script = Path(__file__).parent / 'ai-server-daemon.py'
            if daemon_script.exists():
                with open(daemon_script, 'r') as f:
                    daemon_code = f.read()
                
                # Create remote script file
                stdin, stdout, stderr = ssh.exec_command(
                    f"cat > {workspace}/scripts/ai-server-daemon.py << 'EOF'\n{daemon_code}\nEOF",
                    timeout=30
                )
                
                # Make executable
                stdin, stdout, stderr = ssh.exec_command(
                    f"chmod +x {workspace}/scripts/ai-server-daemon.py",
                    timeout=self.config['command_timeout']
                )
                
                self.logger.info(f"AI daemon installed successfully on {server_id}")
                ssh.close()
                return True
            else:
                self.logger.error("ai-server-daemon.py not found locally")
                ssh.close()
                return False
                
        except Exception as e:
            self.logger.error(f"Error installing daemon: {e}")
            return False
    
    def list_servers(self):
        """List configured servers"""
        print("Configured servers:")
        for server_id, server_config in self.config['servers'].items():
            print(f"  {server_id}: {server_config['name']} ({server_config['host']})")


def main():
    parser = argparse.ArgumentParser(description='AI Client - Send tasks to remote AI servers')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create task command
    create_parser = subparsers.add_parser('create', help='Create a new task')
    create_parser.add_argument('--server', default='server1', help='Target server ID')
    create_parser.add_argument('--tool', required=True, choices=['crush', 'blackbox', 'qwen', 'gemini'],
                             help='AI tool to use')
    create_parser.add_argument('--command', required=True, help='Command to execute')
    create_parser.add_argument('--params', help='JSON parameters')
    create_parser.add_argument('--priority', default='medium', 
                             choices=['low', 'medium', 'high', 'critical'], help='Task priority')
    create_parser.add_argument('--working-dir', help='Working directory for task')
    create_parser.add_argument('--timeout', type=int, help='Task timeout in seconds')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Get server status')
    status_parser.add_argument('--server', default='server1', help='Target server ID')
    
    # List tasks command
    list_parser = subparsers.add_parser('list', help='List tasks')
    list_parser.add_argument('--server', default='server1', help='Target server ID') 
    list_parser.add_argument('--status', choices=['queued', 'running', 'completed', 'failed'],
                           help='Filter by task status')
    
    # Logs command
    logs_parser = subparsers.add_parser('logs', help='Get task logs')
    logs_parser.add_argument('--server', default='server1', help='Target server ID')
    logs_parser.add_argument('task_id', help='Task ID')
    
    # Kill task command
    kill_parser = subparsers.add_parser('kill', help='Kill a running task')
    kill_parser.add_argument('--server', default='server1', help='Target server ID')
    kill_parser.add_argument('task_id', help='Task ID to kill')
    
    # Install command
    install_parser = subparsers.add_parser('install', help='Install daemon on server')
    install_parser.add_argument('--server', default='server1', help='Target server ID')
    
    # Servers command
    subparsers.add_parser('servers', help='List configured servers')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_parser.add_argument('--add-server', nargs=5, metavar=('ID', 'NAME', 'HOST', 'USER', 'KEYFILE'),
                              help='Add server: id name host username keyfile')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    client = AIClient()
    
    if args.command == 'create':
        params = None
        if args.params:
            try:
                params = json.loads(args.params)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON parameters: {e}")
                return
        
        task_id = client.create_task(
            server_id=args.server,
            tool=args.tool,
            command=args.command,
            parameters=params,
            priority=args.priority,
            working_dir=args.working_dir,
            timeout=args.timeout
        )
        
        if task_id:
            print(f"✅ Task created successfully: {task_id}")
            print(f"🖥️  Server: {args.server}")
            print(f"🔧 Tool: {args.tool}")
            print(f"📋 Command: {args.command}")
            print(f"⚡ Priority: {args.priority}")
            print()
            print("The task is now running in the background on the remote server.")
            print("It will continue even if you disconnect.")
            print(f"Use 'python3 ai-client.py logs --server {args.server} {task_id}' to view progress.")
        else:
            print("❌ Failed to create task")
    
    elif args.command == 'status':
        status = client.get_server_status(args.server)
        if status:
            print(f"🖥️  Server Status ({args.server}):")
            print(f"   Daemon PID: {status['daemon_pid']}")
            print(f"   Uptime: {status['uptime']:.1f} seconds")
            print(f"   Queue size: {status['queue_size']}")
            print(f"   Active sessions: {status['active_sessions']}")
            print()
            print("📋 Task Counts:")
            for status_type, count in status['task_counts'].items():
                print(f"   {status_type.capitalize()}: {count}")
            print()
            print("💻 System Resources:")
            print(f"   CPU: {status['system']['cpu_percent']:.1f}%")
            print(f"   Memory: {status['system']['memory_percent']:.1f}%")
            print(f"   Disk: {status['system']['disk_usage']:.1f}%")
        else:
            print("❌ Failed to get server status")
    
    elif args.command == 'list':
        tasks = client.list_tasks(args.server, args.status)
        if tasks:
            print(f"📋 Tasks on {args.server}:")
            print()
            for task in tasks:
                status_emoji = {
                    'queued': '⏳',
                    'running': '🚀', 
                    'completed': '✅',
                    'failed': '❌'
                }.get(task['status'], '❓')
                
                print(f"{status_emoji} {task['id']}")
                print(f"   Tool: {task['tool']}")
                print(f"   Command: {task['command']}")
                print(f"   Status: {task['status']}")
                print(f"   Priority: {task.get('priority', 'medium')}")
                print(f"   Created: {task['created_at']}")
                if task.get('progress'):
                    print(f"   Progress: {task['progress']}%")
                if task.get('error_message'):
                    print(f"   Error: {task['error_message']}")
                print()
        else:
            print(f"No tasks found on {args.server}")
    
    elif args.command == 'logs':
        logs = client.get_task_logs(args.server, args.task_id)
        if logs:
            print(f"📄 Logs for task {args.task_id} on {args.server}:")
            print("=" * 60)
            print(logs)
        else:
            print(f"❌ Could not retrieve logs for task {args.task_id}")
    
    elif args.command == 'kill':
        if client.kill_task(args.server, args.task_id):
            print(f"✅ Task {args.task_id} killed on {args.server}")
        else:
            print(f"❌ Failed to kill task {args.task_id}")
    
    elif args.command == 'install':
        if client.install_on_server(args.server):
            print(f"✅ AI daemon installed on {args.server}")
        else:
            print(f"❌ Failed to install AI daemon on {args.server}")
    
    elif args.command == 'servers':
        client.list_servers()
    
    elif args.command == 'config':
        if args.add_server:
            server_id, name, host, username, keyfile = args.add_server
            client.config['servers'][server_id] = {
                "name": name,
                "host": host,
                "port": 22,
                "username": username,
                "key_file": keyfile,
                "workspace": "~/ai-workspace"
            }
            client.save_config()
            print(f"✅ Server {server_id} added to configuration")
        else:
            print("Current configuration:")
            print(json.dumps(client.config, indent=2))


if __name__ == '__main__':
    main()