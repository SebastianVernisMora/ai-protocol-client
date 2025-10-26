#!/bin/bash

# Install AI Server - Script para instalar el demonio en servidores SSH remotos
# Este script configura todo lo necesario para que las tareas de IA se ejecuten
# de forma persistente en el servidor remoto

set -e

echo "🚀 Instalando AI Server Daemon..."
echo "=================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Default values
WORKSPACE_DIR="$HOME/ai-workspace"
INSTALL_TOOLS=true
CREATE_SERVICE=true
AUTO_START=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --workspace)
            WORKSPACE_DIR="$2"
            shift 2
            ;;
        --no-tools)
            INSTALL_TOOLS=false
            shift
            ;;
        --no-service)
            CREATE_SERVICE=false
            shift
            ;;
        --auto-start)
            AUTO_START=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --workspace DIR     Set workspace directory (default: ~/ai-workspace)"
            echo "  --no-tools         Skip AI tools installation"
            echo "  --no-service       Skip systemd service creation"
            echo "  --auto-start       Start daemon automatically after install"
            echo "  -h, --help         Show this help"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_status "Instalando en: $WORKSPACE_DIR"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_error "No ejecutar como root (usa un usuario normal)"
    exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if [ -f /etc/debian_version ]; then
        DISTRO="debian"
    elif [ -f /etc/redhat-release ]; then
        DISTRO="redhat"
    else
        DISTRO="unknown"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    DISTRO="macos"
else
    print_error "Sistema operativo no soportado: $OSTYPE"
    exit 1
fi

print_status "Sistema detectado: $DISTRO"

# Install system dependencies
print_status "Instalando dependencias del sistema..."

install_system_deps() {
    case $DISTRO in
        "debian")
            sudo apt-get update
            sudo apt-get install -y \
                python3 python3-pip python3-venv python3-dev \
                tmux screen \
                htop \
                curl wget \
                git \
                jq \
                build-essential \
                libssl-dev libffi-dev
            ;;
        "redhat")
            sudo yum update -y
            sudo yum install -y \
                python3 python3-pip python3-devel \
                tmux screen \
                htop \
                curl wget \
                git \
                jq \
                gcc gcc-c++ make \
                openssl-devel libffi-devel
            ;;
        "macos")
            if ! command -v brew &> /dev/null; then
                print_status "Instalando Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            brew install python3 tmux htop curl wget git jq
            ;;
        *)
            print_warning "Distribución no reconocida, instalación manual necesaria"
            ;;
    esac
}

install_system_deps
print_success "Dependencias del sistema instaladas"

# Create workspace structure
print_status "Creando estructura de workspace..."
mkdir -p "$WORKSPACE_DIR"/{scripts,logs,tasks,results,configs,pid,sessions}
print_success "Estructura creada en $WORKSPACE_DIR"

# Install Python dependencies
print_status "Instalando dependencias Python..."
pip3 install --user psutil paramiko

print_success "Dependencias Python instaladas"

# Copy daemon script
print_status "Instalando AI Server Daemon..."

# Check if ai-server-daemon.py exists in current directory
if [ -f "./ai-server-daemon.py" ]; then
    cp "./ai-server-daemon.py" "$WORKSPACE_DIR/scripts/"
elif [ -f "$HOME/ai-server-daemon.py" ]; then
    cp "$HOME/ai-server-daemon.py" "$WORKSPACE_DIR/scripts/"
else
    print_error "ai-server-daemon.py no encontrado"
    print_error "Asegúrate de que el archivo esté en el directorio actual o en $HOME"
    exit 1
fi

chmod +x "$WORKSPACE_DIR/scripts/ai-server-daemon.py"
print_success "AI Server Daemon instalado"

# Create daemon configuration
print_status "Creando configuración del daemon..."
cat > "$WORKSPACE_DIR/configs/daemon.json" << EOF
{
    "max_concurrent_tasks": 4,
    "task_timeout": 3600,
    "cleanup_interval": 300,
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
            "env_setup": ["export GEMINI_API_KEY=\\$GEMINI_KEY"],
            "working_dir": "~/projects",
            "timeout": 1200
        }
    }
}
EOF

print_success "Configuración creada"

# Setup tmux configuration
print_status "Configurando tmux..."
cat >> ~/.tmux.conf << 'EOF'

# AI Server tmux configuration
set -g default-terminal "screen-256color"
set -g history-limit 50000
set -g base-index 1
setw -g pane-base-index 1

# Session persistence
set -g @plugin 'tmux-plugins/tmux-resurrect'
set -g @plugin 'tmux-plugins/tmux-continuum'
set -g @continuum-restore 'on'

# AI task session naming
bind-key A new-session -d -s ai-management

# Logging for AI sessions
set -g @resurrect-capture-pane-contents 'on'
set -g @continuum-save-interval '5'

# Status bar for AI tasks
set -g status-right '#[fg=green]AI Tasks: #(tmux list-sessions | grep "ai-task" | wc -l) #[fg=yellow]%Y-%m-%d %H:%M'

EOF

print_success "tmux configurado"

# Install AI tools if requested
if [ "$INSTALL_TOOLS" = true ]; then
    print_status "Instalando herramientas de IA..."
    
    # Create installation script
    cat > "$WORKSPACE_DIR/scripts/install-ai-tools.sh" << 'EOF'
#!/bin/bash

echo "🤖 Instalando herramientas de IA..."

# Blackbox CLI
install_blackbox() {
    echo "📦 Instalando Blackbox CLI..."
    if command -v npm &> /dev/null; then
        npm install -g @blackbox-ai/cli
    else
        # Alternative installation
        curl -sSL https://github.com/useblackbox/cli/releases/latest/download/blackbox-linux -o ~/.local/bin/blackbox-cli
        chmod +x ~/.local/bin/blackbox-cli
    fi
    echo "✅ Blackbox CLI instalado"
}

# Qwen
install_qwen() {
    echo "🧠 Instalando Qwen..."
    python3 -m venv ~/qwen-env
    source ~/qwen-env/bin/activate
    pip install transformers torch qwen-cli
    echo "✅ Qwen instalado"
}

# Gemini CLI wrapper
install_gemini() {
    echo "💎 Instalando Gemini CLI..."
    pip3 install --user google-generativeai
    
    # Create wrapper script
    mkdir -p ~/.local/bin
    cat > ~/.local/bin/gemini-cli << 'GEMINI_EOF'
#!/usr/bin/env python3
import sys
import google.generativeai as genai
import os
import json

def main():
    if not os.environ.get('GEMINI_API_KEY'):
        print("Error: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    model = genai.GenerativeModel('gemini-pro')
    
    if len(sys.argv) < 2:
        print("Usage: gemini-cli <prompt>", file=sys.stderr)
        sys.exit(1)
    
    # Support for config file
    if sys.argv[1] == '--config' and len(sys.argv) > 2:
        with open(sys.argv[2], 'r') as f:
            config = json.load(f)
        prompt = config.get('prompt', '')
    else:
        prompt = ' '.join(sys.argv[1:])
    
    try:
        response = model.generate_content(prompt)
        print(response.text)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
GEMINI_EOF
    chmod +x ~/.local/bin/gemini-cli
    echo "✅ Gemini CLI instalado"
}

# Crush placeholder (will depend on actual installation method)
install_crush() {
    echo "🔧 Configurando Crush..."
    # Since Crush is likely already available in the environment
    # we just create a simple wrapper or alias
    if ! command -v crush &> /dev/null; then
        echo "⚠️  Crush no encontrado en PATH"
        echo "   Asegúrate de instalar Crush manualmente"
    else
        echo "✅ Crush encontrado en PATH"
    fi
}

# Install all tools
install_blackbox
install_qwen  
install_gemini
install_crush

# Add ~/.local/bin to PATH if not already there
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    echo "📝 Agregado ~/.local/bin al PATH"
fi

echo "🎉 Instalación de herramientas completada"
echo ""
echo "🔑 Configuración de API Keys:"
echo "  - Para Gemini: export GEMINI_API_KEY='tu-api-key'"
echo "  - Para Blackbox: blackbox-cli auth"
echo ""
echo "📚 Reinicia tu shell o ejecuta: source ~/.bashrc"
EOF

    chmod +x "$WORKSPACE_DIR/scripts/install-ai-tools.sh"
    bash "$WORKSPACE_DIR/scripts/install-ai-tools.sh"
    print_success "Herramientas de IA configuradas"
fi

# Create systemd service if requested
if [ "$CREATE_SERVICE" = true ] && command -v systemctl &> /dev/null; then
    print_status "Creando servicio systemd..."
    
    sudo tee /etc/systemd/system/ai-server-daemon.service > /dev/null << EOF
[Unit]
Description=AI Server Daemon
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORKSPACE_DIR
ExecStart=/usr/bin/python3 $WORKSPACE_DIR/scripts/ai-server-daemon.py start --workspace $WORKSPACE_DIR
ExecStop=/usr/bin/python3 $WORKSPACE_DIR/scripts/ai-server-daemon.py stop --workspace $WORKSPACE_DIR
Restart=always
RestartSec=10
StandardOutput=append:$WORKSPACE_DIR/logs/daemon-service.log
StandardError=append:$WORKSPACE_DIR/logs/daemon-service.log

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    print_success "Servicio systemd creado"
    
    if [ "$AUTO_START" = true ]; then
        print_status "Habilitando inicio automático..."
        sudo systemctl enable ai-server-daemon
        sudo systemctl start ai-server-daemon
        print_success "Servicio iniciado y habilitado"
    else
        print_status "Para habilitar inicio automático:"
        echo "  sudo systemctl enable ai-server-daemon"
        echo "  sudo systemctl start ai-server-daemon"
    fi
fi

# Create management scripts
print_status "Creando scripts de gestión..."

# Start script
cat > "$WORKSPACE_DIR/scripts/start-daemon.sh" << EOF
#!/bin/bash
cd "$WORKSPACE_DIR"
python3 scripts/ai-server-daemon.py start --workspace "$WORKSPACE_DIR"
EOF

# Stop script  
cat > "$WORKSPACE_DIR/scripts/stop-daemon.sh" << EOF
#!/bin/bash
cd "$WORKSPACE_DIR"
python3 scripts/ai-server-daemon.py stop --workspace "$WORKSPACE_DIR"
EOF

# Status script
cat > "$WORKSPACE_DIR/scripts/status-daemon.sh" << EOF
#!/bin/bash
cd "$WORKSPACE_DIR"
python3 scripts/ai-server-daemon.py status --workspace "$WORKSPACE_DIR"
EOF

chmod +x "$WORKSPACE_DIR/scripts"/*.sh
print_success "Scripts de gestión creados"

# Create README
print_status "Creando documentación..."
cat > "$WORKSPACE_DIR/README.md" << 'EOF'
# AI Server Daemon

Demonio que permite ejecutar tareas de IA de forma persistente en servidores SSH remotos.

## Características

- ✅ **Persistencia total**: Las tareas continúan aunque se pierda la conexión SSH
- 🔄 **Ejecución en background**: Usa tmux para sesiones persistentes
- 📊 **Monitoreo**: Estado en tiempo real de tareas y recursos
- 🚀 **Múltiples herramientas**: Soporte para Crush, Blackbox, Qwen, Gemini
- ⚡ **Gestión de cola**: Sistema de prioridades y concurrencia
- 📝 **Logs detallados**: Registro completo de todas las operaciones

## Uso Básico

### Iniciar el daemon
```bash
./scripts/start-daemon.sh
```

### Verificar estado
```bash
./scripts/status-daemon.sh
```

### Crear tarea desde remoto
```bash
# Desde tu máquina local
python3 ai-client.py create --server servidor1 --tool crush --command "analyze-project" --params '{"path": "/ruta/proyecto"}'
```

### Ver tareas en ejecución
```bash
python3 scripts/ai-server-daemon.py status
```

### Ver logs de una tarea
```bash
cat logs/task-ID.log
```

## Estructura de Archivos

```
~/ai-workspace/
├── scripts/
│   ├── ai-server-daemon.py     # Daemon principal
│   ├── start-daemon.sh         # Iniciar daemon
│   ├── stop-daemon.sh          # Detener daemon
│   └── status-daemon.sh        # Ver estado
├── tasks/                      # Tareas (JSON)
├── logs/                       # Logs del sistema y tareas
├── results/                    # Resultados de tareas
├── configs/                    # Configuraciones
├── pid/                        # Archivos de proceso
└── sessions/                   # Sesiones tmux
```

## Configuración

Edita `configs/daemon.json` para personalizar:

- Número máximo de tareas concurrentes
- Timeouts de tareas
- Configuración de herramientas IA
- Intervalos de monitoreo

## Herramientas AI Soportadas

### Crush
```bash
python3 ai-server-daemon.py create-task --tool crush --command-name "analyze-codebase" --params '{"path": "/proyecto"}'
```

### Blackbox
```bash
python3 ai-server-daemon.py create-task --tool blackbox --command-name "generate-code" --params '{"language": "python", "description": "API REST"}'
```

### Qwen
```bash
python3 ai-server-daemon.py create-task --tool qwen --command-name "process-text" --params '{"input": "documento.txt"}'
```

### Gemini (requiere GEMINI_API_KEY)
```bash
export GEMINI_API_KEY="tu-api-key"
python3 ai-server-daemon.py create-task --tool gemini --command-name "analyze-image" --params '{"image": "imagen.jpg"}'
```

## Gestión del Servicio

### Con systemd (si está instalado)
```bash
sudo systemctl start ai-server-daemon
sudo systemctl stop ai-server-daemon
sudo systemctl status ai-server-daemon
sudo systemctl enable ai-server-daemon  # Inicio automático
```

### Manual
```bash
./scripts/start-daemon.sh
./scripts/stop-daemon.sh
./scripts/status-daemon.sh
```

## Monitoreo

### Ver todas las sesiones tmux activas
```bash
tmux list-sessions
```

### Conectarse a una sesión específica
```bash
tmux attach-session -t ai-task-ID
```

### Ver logs en tiempo real
```bash
tail -f logs/daemon.log
tail -f logs/task-ID.log
```

## Solución de Problemas

### El daemon no inicia
- Verificar que Python 3 esté instalado
- Comprobar permisos en el workspace
- Revisar logs: `cat logs/daemon.log`

### Las tareas no se ejecutan
- Verificar que tmux esté instalado
- Comprobar que las herramientas IA estén disponibles
- Revisar configuración en `configs/daemon.json`

### Conectividad SSH
- Verificar que el puerto SSH esté abierto
- Comprobar claves SSH
- Revisar permisos de red/firewall

## API del Daemon

El daemon acepta los siguientes comandos:

- `start`: Iniciar daemon
- `stop`: Detener daemon  
- `status`: Ver estado actual
- `create-task`: Crear nueva tarea

Ejemplo de creación de tarea:
```bash
python3 ai-server-daemon.py create-task \
  --tool crush \
  --command-name "analyze-project" \
  --params '{"path": "/ruta/proyecto", "depth": "full"}' \
  --priority high
```
EOF

print_success "Documentación creada"

# Create test script
cat > "$WORKSPACE_DIR/scripts/test-installation.sh" << 'EOF'
#!/bin/bash

echo "🧪 Probando instalación del AI Server Daemon..."
echo "=============================================="

cd ~/ai-workspace

# Test daemon start
echo "1. Probando inicio del daemon..."
python3 scripts/ai-server-daemon.py start &
DAEMON_PID=$!
sleep 3

# Test status
echo "2. Probando estado del daemon..."
python3 scripts/ai-server-daemon.py status

# Test task creation
echo "3. Probando creación de tarea..."
python3 scripts/ai-server-daemon.py create-task \
  --tool crush \
  --command-name "test-command" \
  --params '{"test": "true"}' \
  --priority medium

# Test tmux sessions
echo "4. Verificando sesiones tmux..."
tmux list-sessions | grep ai- || echo "No hay sesiones AI activas"

# Stop daemon
echo "5. Deteniendo daemon de prueba..."
python3 scripts/ai-server-daemon.py stop

echo ""
echo "✅ Pruebas completadas"
echo "Si no hay errores, la instalación fue exitosa"
EOF

chmod +x "$WORKSPACE_DIR/scripts/test-installation.sh"

# Final summary
print_success "¡Instalación completada!"
echo ""
echo "🎉 AI Server Daemon instalado exitosamente"
echo "=========================================="
echo ""
echo "📍 Ubicación: $WORKSPACE_DIR"
echo ""
echo "🚀 Para iniciar el daemon:"
echo "   cd $WORKSPACE_DIR"
echo "   ./scripts/start-daemon.sh"
echo ""
if [ "$CREATE_SERVICE" = true ] && command -v systemctl &> /dev/null; then
    echo "🔧 O usando systemd:"
    echo "   sudo systemctl start ai-server-daemon"
    echo ""
fi
echo "📊 Para verificar estado:"
echo "   ./scripts/status-daemon.sh"
echo ""
echo "🧪 Para probar la instalación:"
echo "   ./scripts/test-installation.sh"
echo ""
echo "📚 Documentación completa: $WORKSPACE_DIR/README.md"
echo ""
print_success "¡Listo para ejecutar tareas de IA persistentes! 🤖"

# Auto-start if requested
if [ "$AUTO_START" = true ] && [ "$CREATE_SERVICE" != true ]; then
    print_status "Iniciando daemon automáticamente..."
    cd "$WORKSPACE_DIR"
    nohup ./scripts/start-daemon.sh > logs/daemon-startup.log 2>&1 &
    sleep 2
    ./scripts/status-daemon.sh
fi