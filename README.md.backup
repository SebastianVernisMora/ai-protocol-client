# 🤖 Cliente AI Protocol - Sistema de IA Distribuida con Persistencia SSH

Sistema completo para ejecutar tareas de IA (Crush, Blackbox, Qwen, Gemini) en servidores SSH remotos con **persistencia total** ante desconexiones.

## 📁 Contenido del Directorio

```
cliente/
├── ai-client.py                    # 💻 Cliente principal (ejecutar desde local)
├── ai-server-daemon.py             # 🖥️ Daemon para servidores SSH
├── install-ai-server.sh            # ⚙️ Instalador automático para servidores
├── ai-monitoring-dashboard.html    # 🌐 Dashboard web de monitoreo
├── ai-dashboard-backend.py         # 🔧 Backend del dashboard
├── setup-ai-dashboard.sh           # 📊 Setup del dashboard web
├── ai-hosting-protocol.md          # 📚 Documentación técnica completa
├── quick-start-guide.md            # 🚀 Guía de inicio rápido
└── README.md                       # 📖 Este archivo
```

## 🎯 ¿Qué hace este sistema?

**PROBLEMA RESUELTO**: Ejecutar tareas de IA pesadas en servidores remotos que continúen ejecutándose aunque se corte la conexión SSH.

**SOLUCIÓN**: 
1. El daemon se ejecuta en cada servidor SSH
2. Las tareas se ejecutan en sesiones tmux persistentes  
3. Puedes desconectarte y las tareas siguen corriendo
4. Reconectas cuando quieras para ver progreso/resultados

## 🚀 Instalación Rápida

### Paso 1: Hacer ejecutables los scripts
```bash
cd /home/sebastianvernis/cliente
chmod +x *.py *.sh
```

### Paso 2: Instalar en servidor SSH remoto
```bash
# Copiar archivos necesarios al servidor
scp ai-server-daemon.py install-ai-server.sh usuario@tu-servidor:~/

# Conectar e instalar
ssh usuario@tu-servidor
./install-ai-server.sh --auto-start
```

### Paso 3: Configurar cliente local
```bash
# Configurar tu servidor
python3 ai-client.py config --add-server server1 "Mi Servidor" IP_SERVIDOR usuario ~/.ssh/id_rsa

# Verificar conexión
python3 ai-client.py status --server server1
```

## 💡 Uso Básico

### Crear tarea de IA (ejemplos)
```bash
# Análisis con Crush
python3 ai-client.py create \
  --server server1 \
  --tool crush \
  --command "analyze-project" \
  --params '{"path": "/home/usuario/proyecto"}'

# Generación con Blackbox  
python3 ai-client.py create \
  --server server1 \
  --tool blackbox \
  --command "generate-api" \
  --params '{"language": "python", "framework": "fastapi"}'

# Procesamiento con Qwen
python3 ai-client.py create \
  --server server1 \
  --tool qwen \
  --command "process-documents" \
  --params '{"input_dir": "~/docs"}'

# Análisis con Gemini
python3 ai-client.py create \
  --server server1 \
  --tool gemini \
  --command "analyze-code" \
  --params '{"file": "main.py"}'
```

### Monitorear tareas
```bash
# Ver estado del servidor
python3 ai-client.py status --server server1

# Listar tareas
python3 ai-client.py list --server server1

# Ver logs de tarea específica
python3 ai-client.py logs --server server1 TASK_ID

# Terminar tarea si es necesario
python3 ai-client.py kill --server server1 TASK_ID
```

## 🌐 Dashboard Web (Opcional)

Si quieres una interfaz web para monitorear:

```bash
# Instalar dashboard
./setup-ai-dashboard.sh

# Iniciar dashboard
cd ~/ai-dashboard
./start-dashboard.sh

# Acceder: http://localhost:5000
```

## 📋 Comandos Principales

### Cliente Local (`ai-client.py`)
- `create` - Crear nueva tarea
- `status` - Ver estado del servidor
- `list` - Listar tareas
- `logs` - Ver logs de tarea
- `kill` - Terminar tarea
- `servers` - Listar servidores configurados
- `config` - Gestionar configuración

### Daemon Servidor (`ai-server-daemon.py`)
- `start` - Iniciar daemon
- `stop` - Detener daemon
- `status` - Ver estado
- `create-task` - Crear tarea (uso interno)

## 🔧 Configuración Avanzada

### Múltiples servidores
```bash
# Agregar más servidores
python3 ai-client.py config --add-server server2 "Servidor Dev" dev.ejemplo.com dev-user ~/.ssh/id_rsa
python3 ai-client.py config --add-server server3 "Cloud Server" cloud.ejemplo.com cloud-user ~/.ssh/id_rsa

# Ver todos los servidores
python3 ai-client.py servers
```

### Configurar herramientas AI
En cada servidor, editar `~/ai-workspace/configs/daemon.json` para personalizar:
- Timeouts de tareas
- Número máximo de tareas concurrentes
- Configuración específica de cada herramienta
- Directorios de trabajo

### APIs requeridas
```bash
# En el servidor, configurar Gemini
echo 'export GEMINI_API_KEY="tu-api-key"' >> ~/.bashrc

# Configurar Blackbox
blackbox-cli auth
```

## 🎪 Ejemplo de Flujo Completo

```bash
# 1. Enviar tarea pesada
python3 ai-client.py create --server server1 --tool crush --command "analyze-large-codebase" --params '{"path": "/proyecto-grande"}'
# Output: ✅ Task created successfully: task-20241025-143022-abc123

# 2. Cerrar laptop / perder conexión
# (La tarea sigue corriendo en el servidor)

# 3. Horas después, verificar progreso
python3 ai-client.py status --server server1
python3 ai-client.py logs --server server1 task-20241025-143022-abc123

# 4. Ver resultado final
python3 ai-client.py list --server server1 --status completed
```

## 🔍 Verificación y Debugging

### En el servidor SSH
```bash
# Ver daemon corriendo
ps aux | grep ai-server-daemon

# Ver sesiones tmux activas
tmux list-sessions

# Ver logs del sistema
tail -f ~/ai-workspace/logs/daemon.log

# Conectar a sesión específica de tarea
tmux attach-session -t ai-task-TASK_ID
```

### Desde cliente local
```bash
# Test de conexión
ssh usuario@servidor "cd ~/ai-workspace && ./scripts/status-daemon.sh"

# Verificar archivos de configuración
python3 ai-client.py config
```

## 🚨 Solución de Problemas

### El servidor no responde
```bash
# Reiniciar daemon en servidor
ssh usuario@servidor "cd ~/ai-workspace && ./scripts/stop-daemon.sh && ./scripts/start-daemon.sh"
```

### Tarea se colgó
```bash
# Terminar tarea específica
python3 ai-client.py kill --server server1 TASK_ID

# O directamente en servidor
ssh usuario@servidor "tmux kill-session -t ai-task-TASK_ID"
```

### Problema de conexión SSH
```bash
# Verificar conectividad
ssh -v usuario@servidor

# Verificar claves SSH
ssh-add -l
```

## 📊 Arquitectura del Sistema

```
[Tu Laptop] --SSH--> [Servidor Remoto]
     |                       |
ai-client.py              ai-server-daemon.py
     |                       |
     |                   [tmux sessions]
     |                   task-001: crush
     |                   task-002: blackbox  
     |                   task-003: qwen
     +---[logs/status]---+
```

## 🎉 Beneficios

✅ **Persistencia Total**: Tareas nunca se pierden por desconexiones  
✅ **Múltiples Herramientas**: Crush, Blackbox, Qwen, Gemini  
✅ **Escalabilidad**: Múltiples servidores simultáneos  
✅ **Monitoreo**: Estado y logs en tiempo real  
✅ **Facilidad**: Instalación y uso simples  
✅ **Robustez**: Manejo de errores y recuperación automática  

---

**¡Tu sistema de IA distribuida está listo para usar! 🚀🤖**

Lee `quick-start-guide.md` para ejemplos detallados o `ai-hosting-protocol.md` para documentación técnica completa.