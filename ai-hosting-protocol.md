# Protocolo de IA Distribuida con Persistencia SSH

## Arquitectura del Sistema

### Herramientas de IA Disponibles
- **Crush**: CLI interactivo para tareas de ingeniería de software
- **Blackbox**: Generación y análisis de código
- **Qwen**: Modelo de lenguaje para tareas generales
- **Gemini**: Análisis avanzado y procesamiento multimodal

### Infraestructura de Hosting
- Servidores SSH remotos configurados
- Sesiones persistentes usando `tmux`/`screen`
- Sistema de logs centralizado
- Monitoreo de estado de tareas

## Configuración Base

### 1. Estructura de Directorios en Servidores

```bash
~/ai-workspace/
├── sessions/           # Sesiones activas de tmux
├── logs/              # Logs de cada herramienta
├── tasks/             # Definiciones de tareas
├── results/           # Resultados de ejecución
├── configs/           # Configuraciones específicas
└── scripts/           # Scripts de automatización
```

### 2. Configuración de Sesiones Persistentes

#### tmux.conf optimizada
```bash
# Configuración en ~/.tmux.conf
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g base-index 1
setw -g pane-base-index 1

# Auto-rename windows
setw -g automatic-rename on
set -g renumber-windows on

# Session persistence
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @continuum-restore 'on'
```

## Protocolo de Ejecución

### 1. Inicialización de Sesión
```bash
#!/bin/bash
# init-ai-session.sh

SESSION_NAME="ai-work-$(date +%Y%m%d-%H%M%S)"
TOOL=$1
TASK_ID=$2

# Crear sesión tmux
tmux new-session -d -s $SESSION_NAME

# Configurar logging
tmux send-keys -t $SESSION_NAME "mkdir -p ~/ai-workspace/logs" Enter
tmux send-keys -t $SESSION_NAME "exec > >(tee ~/ai-workspace/logs/${TOOL}-${TASK_ID}.log)" Enter
tmux send-keys -t $SESSION_NAME "exec 2>&1" Enter

# Activar entorno específico según herramienta
case $TOOL in
    "crush")
        tmux send-keys -t $SESSION_NAME "cd ~/ai-workspace" Enter
        ;;
    "blackbox")
        tmux send-keys -t $SESSION_NAME "blackbox-cli auth" Enter
        ;;
    "qwen")
        tmux send-keys -t $SESSION_NAME "source ~/qwen-env/bin/activate" Enter
        ;;
    "gemini")
        tmux send-keys -t $SESSION_NAME "export GEMINI_API_KEY=\$GEMINI_KEY" Enter
        ;;
esac

echo "Session $SESSION_NAME created for $TOOL"
```

### 2. Sistema de Tareas

#### Definición de Tarea (JSON)
```json
{
  "task_id": "task-001",
  "tool": "crush",
  "priority": "high",
  "command": "analyze-codebase",
  "parameters": {
    "path": "/path/to/project",
    "output": "results/analysis-001.json"
  },
  "retry_policy": {
    "max_retries": 3,
    "backoff": "exponential"
  },
  "timeout": 3600,
  "dependencies": [],
  "created_at": "2024-10-25T10:30:00Z"
}
```

#### Executor de Tareas
```bash
#!/bin/bash
# task-executor.sh

TASK_FILE=$1
TASK_ID=$(jq -r '.task_id' $TASK_FILE)
TOOL=$(jq -r '.tool' $TASK_FILE)
COMMAND=$(jq -r '.command' $TASK_FILE)

# Crear sesión para la tarea
SESSION_NAME="task-${TASK_ID}"
tmux new-session -d -s $SESSION_NAME

# Ejecutar según herramienta
execute_task() {
    case $TOOL in
        "crush")
            tmux send-keys -t $SESSION_NAME "crush $COMMAND" Enter
            ;;
        "blackbox")
            tmux send-keys -t $SESSION_NAME "blackbox $COMMAND" Enter
            ;;
        "qwen")
            tmux send-keys -t $SESSION_NAME "qwen-cli $COMMAND" Enter
            ;;
        "gemini")
            tmux send-keys -t $SESSION_NAME "gemini-cli $COMMAND" Enter
            ;;
    esac
}

# Monitorear ejecución
monitor_task() {
    while tmux has-session -t $SESSION_NAME 2>/dev/null; do
        sleep 30
        # Verificar si la tarea sigue activa
        if ! tmux list-panes -t $SESSION_NAME -F '#{pane_current_command}' | grep -q "$TOOL"; then
            echo "Task $TASK_ID completed"
            break
        fi
    done
}

execute_task &
monitor_task &
```

### 3. Sistema de Monitoreo

#### Healthcheck Script
```bash
#!/bin/bash
# healthcheck.sh

check_sessions() {
    echo "=== Active AI Sessions ==="
    tmux list-sessions | grep -E "(crush|blackbox|qwen|gemini)"
    
    echo "=== Resource Usage ==="
    ps aux | grep -E "(crush|blackbox|qwen|gemini)" | head -10
    
    echo "=== Recent Logs ==="
    find ~/ai-workspace/logs -name "*.log" -mmin -60 | while read log; do
        echo "--- $log ---"
        tail -5 "$log"
    done
}

check_sessions > ~/ai-workspace/logs/healthcheck-$(date +%Y%m%d-%H%M%S).log
```

### 4. Coordinador de Tareas

#### Main Coordinator
```python
#!/usr/bin/env python3
# ai-coordinator.py

import json
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path

class AICoordinator:
    def __init__(self):
        self.workspace = Path.home() / "ai-workspace"
        self.tasks_dir = self.workspace / "tasks"
        self.logs_dir = self.workspace / "logs"
        
        # Setup logging
        logging.basicConfig(
            filename=self.logs_dir / "coordinator.log",
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
    
    def submit_task(self, task_config):
        """Submit a new task to the queue"""
        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        task_config['task_id'] = task_id
        task_config['status'] = 'queued'
        task_config['created_at'] = datetime.now().isoformat()
        
        task_file = self.tasks_dir / f"{task_id}.json"
        with open(task_file, 'w') as f:
            json.dump(task_config, f, indent=2)
        
        logging.info(f"Task {task_id} queued")
        return task_id
    
    def execute_task(self, task_id):
        """Execute a specific task"""
        task_file = self.tasks_dir / f"{task_id}.json"
        
        if not task_file.exists():
            logging.error(f"Task file {task_file} not found")
            return False
        
        # Execute task in background
        subprocess.Popen([
            "bash", "task-executor.sh", str(task_file)
        ], cwd=self.workspace)
        
        logging.info(f"Task {task_id} started")
        return True
    
    def monitor_tasks(self):
        """Monitor all active tasks"""
        while True:
            # Check tmux sessions
            result = subprocess.run(
                ["tmux", "list-sessions", "-f", "#{session_name}: #{?session_attached,attached,not attached}"],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                sessions = result.stdout.strip().split('\n')
                ai_sessions = [s for s in sessions if any(tool in s for tool in ['crush', 'blackbox', 'qwen', 'gemini'])]
                
                logging.info(f"Active AI sessions: {len(ai_sessions)}")
            
            time.sleep(60)  # Check every minute

if __name__ == "__main__":
    coordinator = AICoordinator()
    coordinator.monitor_tasks()
```

### 5. Scripts de Conexión SSH

#### Conexión con Recuperación Automática
```bash
#!/bin/bash
# connect-ai-host.sh

HOST=$1
AI_TOOL=$2
TASK_CONFIG=$3

connect_with_retry() {
    local retries=0
    local max_retries=5
    
    while [ $retries -lt $max_retries ]; do
        echo "Connecting to $HOST (attempt $((retries + 1)))"
        
        ssh -o ConnectTimeout=30 -o ServerAliveInterval=60 $HOST << EOF
            # Verificar si tmux está instalado
            if ! command -v tmux &> /dev/null; then
                echo "Installing tmux..."
                sudo apt-get update && sudo apt-get install -y tmux
            fi
            
            # Crear workspace si no existe
            mkdir -p ~/ai-workspace/{sessions,logs,tasks,results,configs,scripts}
            
            # Restaurar sesiones tmux si existen
            if [ -f ~/.tmux/resurrect/last ]; then
                tmux run-shell ~/.tmux/plugins/tmux-resurrect/scripts/restore.sh
            fi
            
            # Ejecutar tarea específica
            if [ -n "$TASK_CONFIG" ]; then
                echo '$TASK_CONFIG' > ~/ai-workspace/tasks/current-task.json
                bash ~/ai-workspace/scripts/task-executor.sh ~/ai-workspace/tasks/current-task.json
            fi
            
            # Mantener conexión activa
            while true; do
                sleep 300  # Keep alive cada 5 minutos
                tmux list-sessions > /dev/null 2>&1 || break
            done
EOF
        
        local exit_code=$?
        if [ $exit_code -eq 0 ]; then
            echo "Connection to $HOST successful"
            return 0
        fi
        
        retries=$((retries + 1))
        echo "Connection failed, retrying in 30 seconds..."
        sleep 30
    done
    
    echo "Failed to connect to $HOST after $max_retries attempts"
    return 1
}

connect_with_retry
```

## Casos de Uso

### 1. Análisis de Código con Crush
```json
{
  "tool": "crush",
  "command": "analyze-project",
  "parameters": {
    "project_path": "/home/user/project",
    "analysis_type": "full",
    "output_format": "json"
  },
  "estimated_duration": 1800
}
```

### 2. Generación de Código con Blackbox
```json
{
  "tool": "blackbox",
  "command": "generate-api",
  "parameters": {
    "specification": "openapi-spec.yaml",
    "language": "python",
    "framework": "fastapi"
  },
  "estimated_duration": 900
}
```

### 3. Procesamiento con Qwen
```json
{
  "tool": "qwen",
  "command": "process-documents",
  "parameters": {
    "input_dir": "documents/",
    "task_type": "summarization",
    "batch_size": 10
  },
  "estimated_duration": 2400
}
```

### 4. Análisis Multimodal con Gemini
```json
{
  "tool": "gemini",
  "command": "analyze-media",
  "parameters": {
    "media_dir": "assets/",
    "analysis_types": ["text", "image", "video"],
    "output_format": "detailed_report"
  },
  "estimated_duration": 3600
}
```

## Recuperación ante Desconexiones

### Automatización de Reconexión
```bash
#!/bin/bash
# auto-reconnect.sh

HOSTS_FILE="~/ai-workspace/configs/hosts.txt"

while IFS= read -r host; do
    {
        while true; do
            if ! ssh -o ConnectTimeout=10 $host "tmux list-sessions" >/dev/null 2>&1; then
                echo "$(date): Connection to $host lost, attempting reconnection..."
                bash connect-ai-host.sh $host
            fi
            sleep 120  # Check every 2 minutes
        done
    } &
done < "$HOSTS_FILE"

wait
```

## Instalación y Configuración

### Script de Setup Inicial
```bash
#!/bin/bash
# setup-ai-protocol.sh

# Crear estructura de directorios
mkdir -p ~/ai-workspace/{sessions,logs,tasks,results,configs,scripts}

# Copiar scripts
cp *.sh ~/ai-workspace/scripts/
cp ai-coordinator.py ~/ai-workspace/scripts/
chmod +x ~/ai-workspace/scripts/*.sh

# Configurar tmux
cp tmux.conf ~/.tmux.conf
tmux source-file ~/.tmux.conf

# Instalar dependencias Python
pip3 install psutil tmux-python

echo "AI Protocol setup completed!"
echo "Usage: bash ~/ai-workspace/scripts/connect-ai-host.sh <host> <tool> <task-config>"
```

Este protocolo proporciona:
- **Persistencia**: Las sesiones continúan tras desconexiones
- **Monitoreo**: Seguimiento del estado de todas las herramientas
- **Recuperación**: Reconexión automática y restauración de sesiones
- **Coordinación**: Sistema centralizado para gestionar tareas
- **Flexibilidad**: Soporte para múltiples herramientas de IA
- **Logging**: Registro detallado de todas las operaciones