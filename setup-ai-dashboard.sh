#!/bin/bash

# Setup AI Dashboard - Instalador completo del sistema de monitoreo
# Autor: Sistema AI Protocol
# Fecha: $(date +%Y-%m-%d)

set -e  # Exit on any error

echo "🚀 Iniciando instalación del AI Dashboard..."
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_error "Este script no debe ejecutarse como root"
    exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    if [ -f /etc/debian_version ]; then
        DISTRO="debian"
    elif [ -f /etc/redhat-release ]; then
        DISTRO="redhat"
    else
        DISTRO="unknown"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    print_error "Sistema operativo no soportado: $OSTYPE"
    exit 1
fi

print_status "Detectado: $OS ($DISTRO)"

# Set workspace directory
WORKSPACE_DIR="$HOME/ai-workspace"
DASHBOARD_DIR="$HOME/ai-dashboard"

# Create directories
print_status "Creando estructura de directorios..."
mkdir -p "$WORKSPACE_DIR"/{sessions,logs,tasks,results,configs,scripts}
mkdir -p "$DASHBOARD_DIR"
mkdir -p ~/.ssh

print_success "Directorios creados"

# Install system dependencies
print_status "Instalando dependencias del sistema..."

install_system_deps() {
    case $OS in
        "linux")
            case $DISTRO in
                "debian")
                    sudo apt-get update
                    sudo apt-get install -y \
                        python3 python3-pip python3-venv \
                        tmux screen \
                        openssh-client \
                        curl wget \
                        git \
                        htop \
                        jq \
                        nodejs npm
                    ;;
                "redhat")
                    sudo yum update -y
                    sudo yum install -y \
                        python3 python3-pip \
                        tmux screen \
                        openssh-clients \
                        curl wget \
                        git \
                        htop \
                        jq \
                        nodejs npm
                    ;;
                *)
                    print_warning "Distribución no reconocida, instalación manual necesaria"
                    ;;
            esac
            ;;
        "macos")
            if ! command -v brew &> /dev/null; then
                print_status "Instalando Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            
            brew install python3 tmux openssh curl wget git htop jq node
            ;;
    esac
}

install_system_deps
print_success "Dependencias del sistema instaladas"

# Setup Python environment
print_status "Configurando entorno Python..."
cd "$DASHBOARD_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install \
    flask \
    flask-cors \
    websockets \
    paramiko \
    psutil \
    requests \
    asyncio

print_success "Entorno Python configurado"

# Copy dashboard files
print_status "Copiando archivos del dashboard..."

# Copy the HTML dashboard
if [ -f "$HOME/ai-monitoring-dashboard.html" ]; then
    cp "$HOME/ai-monitoring-dashboard.html" "$DASHBOARD_DIR/"
    print_success "Dashboard HTML copiado"
else
    print_warning "Archivo ai-monitoring-dashboard.html no encontrado"
fi

# Copy the Python backend
if [ -f "$HOME/ai-dashboard-backend.py" ]; then
    cp "$HOME/ai-dashboard-backend.py" "$DASHBOARD_DIR/"
    chmod +x "$DASHBOARD_DIR/ai-dashboard-backend.py"
    print_success "Backend Python copiado"
else
    print_warning "Archivo ai-dashboard-backend.py no encontrado"
fi

# Copy the protocol documentation
if [ -f "$HOME/ai-hosting-protocol.md" ]; then
    cp "$HOME/ai-hosting-protocol.md" "$DASHBOARD_DIR/"
    print_success "Documentación del protocolo copiada"
fi

# Setup tmux configuration
print_status "Configurando tmux..."
cat > ~/.tmux.conf << 'EOF'
# AI Protocol tmux configuration
set -g default-terminal "screen-256color"
set -g history-limit 10000
set -g base-index 1
setw -g pane-base-index 1

# Auto-rename windows
setw -g automatic-rename on
set -g renumber-windows on

# Mouse support
set -g mouse on

# Status bar
set -g status-bg colour234
set -g status-fg white
set -g status-left '#[fg=green]#H '
set -g status-right '#[fg=yellow]%Y-%m-%d %H:%M'

# Pane borders
set -g pane-border-style fg=colour238
set -g pane-active-border-style fg=colour154

# Session persistence (if tmux-resurrect is available)
run-shell "tmux list-plugins | grep -q resurrect && tmux run-shell '~/.tmux/plugins/tmux-resurrect/resurrect.tmux'"

# Key bindings
bind-key r source-file ~/.tmux.conf \; display-message "Config reloaded!"
bind-key | split-window -h
bind-key - split-window -v

# AI session shortcuts
bind-key C new-session -d -s crush
bind-key B new-session -d -s blackbox  
bind-key Q new-session -d -s qwen
bind-key G new-session -d -s gemini
EOF

print_success "tmux configurado"

# Create configuration file
print_status "Creando configuración inicial..."
cat > "$WORKSPACE_DIR/configs/dashboard.json" << EOF
{
    "refresh_interval": 30,
    "ssh_hosts": [
        {
            "id": "local",
            "name": "Local Machine",
            "host": "localhost",
            "port": 22,
            "username": "$USER",
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
            "env_setup": "export GEMINI_API_KEY=\\$GEMINI_KEY"
        }
    },
    "dashboard": {
        "host": "0.0.0.0",
        "port": 5000,
        "websocket_port": 8765
    }
}
EOF

print_success "Configuración inicial creada"

# Create startup scripts
print_status "Creando scripts de inicio..."

# Dashboard startup script
cat > "$DASHBOARD_DIR/start-dashboard.sh" << 'EOF'
#!/bin/bash

# Start AI Dashboard
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Iniciando AI Dashboard..."

# Activate Python environment
source venv/bin/activate

# Start the backend
python3 ai-dashboard-backend.py
EOF

chmod +x "$DASHBOARD_DIR/start-dashboard.sh"

# AI tools installer script
cat > "$DASHBOARD_DIR/install-ai-tools.sh" << 'EOF'
#!/bin/bash

# Install AI Tools Script
echo "🤖 Instalando herramientas de IA..."

install_crush() {
    echo "Instalando Crush..."
    # Add Crush installation commands here
    echo "Crush installation placeholder"
}

install_blackbox() {
    echo "Instalando Blackbox CLI..."
    if command -v npm &> /dev/null; then
        npm install -g @blackbox-ai/cli
    else
        echo "npm no encontrado, instalando manualmente..."
        curl -sSL https://github.com/Nutlope/blackbox-cli/releases/latest/download/blackbox-linux -o /usr/local/bin/blackbox-cli
        chmod +x /usr/local/bin/blackbox-cli
    fi
}

install_qwen() {
    echo "Instalando Qwen..."
    # Create virtual environment for Qwen
    python3 -m venv ~/qwen-env
    source ~/qwen-env/bin/activate
    pip install qwen-cli transformers torch
}

install_gemini() {
    echo "Instalando Gemini CLI..."
    pip3 install google-generativeai
    # Create wrapper script
    cat > /usr/local/bin/gemini-cli << 'GEMINI_EOF'
#!/usr/bin/env python3
import sys
import google.generativeai as genai
import os

def main():
    if not os.environ.get('GEMINI_API_KEY'):
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)
    
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    model = genai.GenerativeModel('gemini-pro')
    
    if len(sys.argv) < 2:
        print("Usage: gemini-cli <prompt>")
        sys.exit(1)
    
    prompt = ' '.join(sys.argv[1:])
    response = model.generate_content(prompt)
    print(response.text)

if __name__ == "__main__":
    main()
GEMINI_EOF
    chmod +x /usr/local/bin/gemini-cli
}

# Install tools
install_blackbox
install_qwen
install_gemini

echo "✅ Instalación de herramientas completada"
echo "Nota: Configura las API keys necesarias antes de usar las herramientas"
EOF

chmod +x "$DASHBOARD_DIR/install-ai-tools.sh"

# System service (systemd) for auto-start
if command -v systemctl &> /dev/null; then
    print_status "Configurando servicio systemd..."
    
    sudo tee /etc/systemd/system/ai-dashboard.service > /dev/null << EOF
[Unit]
Description=AI Protocol Dashboard
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$DASHBOARD_DIR
ExecStart=$DASHBOARD_DIR/start-dashboard.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    
    print_success "Servicio systemd configurado"
    print_status "Para habilitar inicio automático: sudo systemctl enable ai-dashboard"
fi

# Create desktop shortcut (Linux only)
if [[ "$OS" == "linux" ]] && [ -d "$HOME/Desktop" ]; then
    print_status "Creando acceso directo en el escritorio..."
    
    cat > "$HOME/Desktop/AI Dashboard.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AI Dashboard
Comment=AI Protocol Monitoring Dashboard
Exec=bash -c "cd $DASHBOARD_DIR && ./start-dashboard.sh"
Icon=utilities-system-monitor
Terminal=true
Categories=Development;System;
EOF

    chmod +x "$HOME/Desktop/AI Dashboard.desktop"
    print_success "Acceso directo creado"
fi

# Generate SSH key if not exists
if [ ! -f ~/.ssh/id_rsa ]; then
    print_status "Generando clave SSH..."
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
    print_success "Clave SSH generada"
    print_warning "Recuerda copiar la clave pública a los servidores remotos:"
    echo "ssh-copy-id usuario@servidor"
fi

# Create usage guide
print_status "Creando guía de uso..."
cat > "$DASHBOARD_DIR/README.md" << 'EOF'
# AI Dashboard - Guía de Uso

## Inicio Rápido

1. **Iniciar el Dashboard:**
   ```bash
   cd ~/ai-dashboard
   ./start-dashboard.sh
   ```

2. **Acceder al Dashboard:**
   - Abrir navegador en: http://localhost:5000
   - WebSocket en: ws://localhost:8765

## Configuración

### Agregar Servidores SSH
Edita `~/ai-workspace/configs/dashboard.json`:

```json
{
  "ssh_hosts": [
    {
      "id": "server1",
      "name": "Servidor Producción",
      "host": "192.168.1.100",
      "port": 22,
      "username": "ai-user",
      "key_file": "~/.ssh/id_rsa"
    }
  ]
}
```

### Instalar Herramientas AI
```bash
./install-ai-tools.sh
```

### Configurar API Keys
```bash
# Gemini
export GEMINI_API_KEY="tu-api-key"

# Blackbox (si aplica)
blackbox-cli auth
```

## Comandos Útiles

### Gestión de Sesiones tmux
```bash
# Listar sesiones
tmux list-sessions

# Conectar a sesión
tmux attach-session -t session-name

# Matar sesión
tmux kill-session -t session-name
```

### Monitoreo Manual
```bash
# Ver logs
tail -f ~/ai-workspace/logs/monitor.log

# Estado de hosts
python3 -c "
import sys; sys.path.append('$DASHBOARD_DIR')
from ai_dashboard_backend import AITaskMonitor
monitor = AITaskMonitor()
monitor.update_host_status()
print(monitor.hosts)
"
```

## Estructura de Archivos
```
~/ai-workspace/
├── sessions/    # Sesiones tmux activas
├── logs/        # Logs de tareas y sistema
├── tasks/       # Definiciones de tareas
├── results/     # Resultados de ejecución  
├── configs/     # Configuraciones
└── scripts/     # Scripts auxiliares

~/ai-dashboard/
├── venv/                        # Entorno Python
├── ai-monitoring-dashboard.html # Frontend
├── ai-dashboard-backend.py      # Backend
├── start-dashboard.sh           # Script de inicio
└── install-ai-tools.sh         # Instalador de herramientas
```

## Solución de Problemas

### Dashboard no inicia
- Verificar que el puerto 5000 esté libre
- Comprobar logs: `~/ai-workspace/logs/monitor.log`
- Verificar entorno Python: `source ~/ai-dashboard/venv/bin/activate`

### Conexión SSH falla
- Verificar conectividad: `ssh usuario@host`
- Comprobar clave SSH: `ssh-add ~/.ssh/id_rsa`
- Revisar configuración en `dashboard.json`

### Tareas no se ejecutan
- Verificar que tmux esté instalado en el servidor remoto
- Comprobar que las herramientas AI estén disponibles
- Revisar logs de la tarea específica
EOF

print_success "Guía de uso creada"

# Final steps
print_status "Instalación completada!"
echo ""
echo "🎉 AI Dashboard instalado exitosamente!"
echo "================================================"
echo ""
echo "📍 Ubicaciones importantes:"
echo "   Dashboard: $DASHBOARD_DIR"
echo "   Workspace: $WORKSPACE_DIR"
echo ""
echo "🚀 Para iniciar el dashboard:"
echo "   cd $DASHBOARD_DIR"
echo "   ./start-dashboard.sh"
echo ""
echo "🌐 Acceso web: http://localhost:5000"
echo ""
echo "📚 Documentación: $DASHBOARD_DIR/README.md"
echo ""

if [[ "$OS" == "linux" ]] && command -v systemctl &> /dev/null; then
    echo "⚙️  Para habilitar inicio automático:"
    echo "   sudo systemctl enable ai-dashboard"
    echo "   sudo systemctl start ai-dashboard"
    echo ""
fi

echo "🔧 Próximos pasos:"
echo "   1. Configurar servidores SSH en: $WORKSPACE_DIR/configs/dashboard.json"
echo "   2. Instalar herramientas AI: $DASHBOARD_DIR/install-ai-tools.sh"
echo "   3. Configurar API keys según sea necesario"
echo "   4. Iniciar el dashboard y acceder via web"
echo ""

print_success "¡Listo para monitorear tareas de IA! 🤖"