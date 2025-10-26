# 🚀 Guía de Inicio Rápido - AI Protocol con Persistencia SSH

## ¿Qué es esto?

Un sistema que permite ejecutar tareas de IA (Crush, Blackbox, Qwen, Gemini) en servidores SSH remotos de forma **completamente persistente**. Si se corta la conexión, las tareas continúan ejecutándose en segundo plano.

## 🎯 Objetivo Principal

**PERSISTENCIA TOTAL**: Las tareas de IA se ejecutan en el servidor remoto usando `tmux` y continúan funcionando aunque perdamos la conexión SSH.

## 📦 Componentes del Sistema

### 1. **AI Server Daemon** (`ai-server-daemon.py`)
- Se instala y ejecuta en cada servidor SSH
- Gestiona una cola de tareas de IA
- Ejecuta tareas en sesiones tmux persistentes
- Monitorea progreso y estado

### 2. **AI Client** (`ai-client.py`)
- Se ejecuta en tu máquina local
- Envía tareas a servidores remotos
- Consulta estado y logs
- Gestiona múltiples servidores

### 3. **Instalador de Servidor** (`install-ai-server.sh`)
- Instala todo lo necesario en el servidor remoto
- Configura dependencias y servicios
- Instala herramientas de IA

## 🛠️ Instalación Rápida

### Paso 1: En tu máquina local
```bash
# Descargar archivos del sistema
# (ya los tienes en /home/sebastianvernis/)

# Hacer ejecutables
chmod +x ai-client.py install-ai-server.sh ai-server-daemon.py
```

### Paso 2: En cada servidor SSH remoto
```bash
# Copiar el instalador al servidor
scp install-ai-server.sh ai-server-daemon.py usuario@servidor:~/

# Conectar al servidor e instalar
ssh usuario@servidor
./install-ai-server.sh --auto-start
```

### Paso 3: Configurar cliente local
```bash
# Configurar servidores
python3 ai-client.py config --add-server server1 "Mi Servidor" 192.168.1.100 usuario ~/.ssh/id_rsa

# Listar servidores configurados
python3 ai-client.py servers
```

## 🚀 Uso Básico

### Crear una tarea de IA
```bash
# Ejemplo con Crush
python3 ai-client.py create \
  --server server1 \
  --tool crush \
  --command "analyze-project" \
  --params '{"path": "/home/usuario/mi-proyecto", "depth": "full"}' \
  --priority high

# Ejemplo con Blackbox
python3 ai-client.py create \
  --server server1 \
  --tool blackbox \
  --command "generate-api" \
  --params '{"language": "python", "framework": "fastapi", "description": "API para gestión de usuarios"}'

# Ejemplo con Qwen
python3 ai-client.py create \
  --server server1 \
  --tool qwen \
  --command "process-documents" \
  --params '{"input_dir": "~/documents", "task": "summarization"}'

# Ejemplo con Gemini (requiere API key)
python3 ai-client.py create \
  --server server1 \
  --tool gemini \
  --command "analyze-code" \
  --params '{"file": "src/main.py", "task": "optimization"}'
```

### Monitorear tareas
```bash
# Ver estado del servidor
python3 ai-client.py status --server server1

# Listar todas las tareas
python3 ai-client.py list --server server1

# Listar solo tareas en ejecución
python3 ai-client.py list --server server1 --status running

# Ver logs de una tarea específica
python3 ai-client.py logs --server server1 task-20241025-143022-abc123
```

### Gestionar tareas
```bash
# Terminar una tarea
python3 ai-client.py kill --server server1 task-20241025-143022-abc123
```

## 🔄 Flujo de Trabajo Típico

### 1. **Envío de Tarea**
```bash
# Desde tu laptop
python3 ai-client.py create --server server1 --tool crush --command "analyze-large-codebase" --params '{"path": "/proj"}'

# Output: ✅ Task created successfully: task-20241025-143022-abc123
```

### 2. **Desconexión (Internet se corta)**
```bash
# Tu conexión SSH se pierde, pero la tarea continúa en el servidor
# El daemon sigue ejecutando la tarea en tmux
```

### 3. **Reconexión y Verificación**
```bash
# Cuando recuperas conexión
python3 ai-client.py status --server server1

# Ver progreso de la tarea
python3 ai-client.py logs --server server1 task-20241025-143022-abc123
```

### 4. **Resultado**
```bash
# La tarea se completó aunque no estuvieras conectado
python3 ai-client.py list --server server1 --status completed
```

## 🎛️ Gestión Avanzada

### Múltiples servidores
```bash
# Agregar más servidores
python3 ai-client.py config --add-server server2 "Servidor Dev" dev.empresa.com dev-user ~/.ssh/id_rsa

# Distribuir tareas
python3 ai-client.py create --server server1 --tool crush --command "task1"
python3 ai-client.py create --server server2 --tool blackbox --command "task2"
```

### Configuración de herramientas
```bash
# En el servidor, editar configuración
ssh usuario@servidor
nano ~/ai-workspace/configs/daemon.json

# Ajustar timeouts, concurrencia, etc.
```

### Sesiones tmux directas
```bash
# Conectar directamente a la sesión de una tarea
ssh usuario@servidor
tmux list-sessions | grep ai-task
tmux attach-session -t ai-task-20241025-143022-abc123
```

## 📊 Monitoreo del Sistema

### Estado del daemon
```bash
# Desde el servidor
cd ~/ai-workspace
./scripts/status-daemon.sh

# Output:
# {
#   "daemon_pid": 12345,
#   "uptime": 3600,
#   "task_counts": {
#     "queued": 2,
#     "running": 3,
#     "completed": 15,
#     "failed": 1
#   },
#   "system": {
#     "cpu_percent": 45.2,
#     "memory_percent": 67.8
#   }
# }
```

### Logs del sistema
```bash
# En el servidor
tail -f ~/ai-workspace/logs/daemon.log

# Logs de tarea específica
tail -f ~/ai-workspace/logs/task-ID.log
```

## 🔧 Configuración Personalizada

### Configurar APIs
```bash
# En el servidor, para Gemini
echo 'export GEMINI_API_KEY="tu-api-key-aqui"' >> ~/.bashrc

# Para Blackbox
blackbox-cli auth
```

### Configurar herramientas
```bash
# Editar configuración del daemon
nano ~/ai-workspace/configs/daemon.json

# Personalizar comandos, timeouts, directorios de trabajo
```

## 🚨 Solución de Problemas

### El daemon no responde
```bash
# En el servidor
cd ~/ai-workspace
./scripts/stop-daemon.sh
./scripts/start-daemon.sh
```

### Tarea se colgó
```bash
# Desde cliente local
python3 ai-client.py kill --server server1 task-ID

# Desde servidor directamente
tmux kill-session -t ai-task-ID
```

### Verificar instalación
```bash
# En el servidor
cd ~/ai-workspace
./scripts/test-installation.sh
```

## 💡 Casos de Uso Reales

### 1. **Análisis de código masivo con Crush**
```bash
python3 ai-client.py create \
  --server server1 \
  --tool crush \
  --command "analyze-repository" \
  --params '{"repo": "https://github.com/large/project", "analysis": "full"}'

# La tarea toma 3 horas, pero puedes desconectarte sin problemas
```

### 2. **Generación de múltiples APIs con Blackbox**
```bash
# Queue multiple API generation tasks
for api in users products orders payments; do
  python3 ai-client.py create \
    --server server1 \
    --tool blackbox \
    --command "generate-api" \
    --params "{\"name\": \"$api\", \"language\": \"python\"}"
done
```

### 3. **Procesamiento de documentos con Qwen**
```bash
python3 ai-client.py create \
  --server server2 \
  --tool qwen \
  --command "batch-process" \
  --params '{"input_dir": "/data/documents", "output_dir": "/data/processed", "task": "translation"}' \
  --timeout 7200
```

## 🎉 Ventajas del Sistema

✅ **Persistencia Total**: Las tareas nunca se pierden por desconexiones
✅ **Escalabilidad**: Múltiples servidores, múltiples tareas concurrentes  
✅ **Monitoreo**: Estado en tiempo real de todas las operaciones
✅ **Flexibilidad**: Soporte para diferentes herramientas de IA
✅ **Facilidad**: Instalación automática y configuración simple
✅ **Robustez**: Manejo de errores, timeouts y recuperación automática

---

**¡Tu infraestructura de IA distribuida está lista! 🚀🤖**

Ahora puedes enviar tareas pesadas de IA a servidores remotos y desconectarte sin preocupaciones. Las tareas continuarán ejecutándose y podrás verificar su progreso cuando te vuelvas a conectar.