#!/bin/bash
# 🚀 AgentOS Reboot & Health Restore System
# Version: 1.1.0 (Oracle Edition)
# Description: Restores stable system state, restarts services, and repairs symlinks.

LOG_FILE="$HOME/agent-data/logs/maintenance.log"
BACKUP_DIR="$HOME/agent-data/backups/env"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
# High-resolution backup filename to prevent overwrites
BACKUP_FILE="$BACKUP_DIR/.env.backup_$(date +%Y%m%d_%H%M%S_%N)"

echo "[$TIMESTAMP] 🔄 INITIATING AGENT OS REBOOT PROTOCOL..." | tee -a $LOG_FILE

# 1. Environment Safety
echo "📦 Backing up .env and ensuring .gitignore safety..."
mkdir -p $BACKUP_DIR
cp $HOME/agentmanager/.env "$BACKUP_FILE"
echo "Backup created at: $BACKUP_FILE"
# Update .gitignore if needed
if ! grep -q ".env.backup_*" $HOME/agentmanager/.gitignore; then
    echo ".env.backup_*" >> $HOME/agentmanager/.gitignore
fi

# 2. Logic/Data Symlink Repair (Audit & Reconnect)
echo "🧬 Auditing Symlink Integrity (Logic <-> Data)..."
for p_dir in $HOME/agent-data/projects/*/; do
    p_name=$(basename $p_dir)
    logic_path="$HOME/${p_name}"
    
    if [ -d "$logic_path" ]; then
        # Check STATUS.md
        if [ ! -L "${logic_path}/STATUS.md" ] && [ -f "${logic_path}/STATUS.md" ]; then
            echo "⚠️ [VIOLATION] Found real STATUS.md in ${p_name}. Converting to symlink..."
            mv "${logic_path}/STATUS.md" "${p_dir}STATUS.md.backup"
            ln -s "${p_dir}STATUS.md" "${logic_path}/STATUS.md"
        fi
        
        # Check memory/ (Crucial for Zeus Writer stability)
        if [ ! -L "${logic_path}/memory" ] && [ -d "${logic_path}/memory" ]; then
            echo "⚠️ [VIOLATION] Found real memory/ dir in ${p_name}. Restoring symlink..."
            # Sync content to data layer first
            rsync -av "${logic_path}/memory/" "${p_dir}memory/"
            rm -rf "${logic_path}/memory"
            ln -s "${p_dir}memory" "${logic_path}/memory"
        fi
    fi
done

# 3. Service Resurrection (Systemd User Units)
echo "🤖 Restarting System Services (tg-commander, os-pulse)..."
systemctl --user daemon-reload
systemctl --user restart tg-commander.service os-pulse.service
echo "✅ Core services restarted via systemd."

# 4. Pulse & Global Metadata Sync
echo "📡 Broadcasting 'System Resurrection' Heartbeat..."
python3 $HOME/agentmanager/scripts/pulse.py --agent Architect --event system_reboot --message "Apocalypse Signal: Order restored. Truth level synced."
echo "📡 Refreshing System Dashboard and Status Hub..."
python3 $HOME/agentmanager/scripts/meditation/meditator.py

# 5. Summary & Pulse Update
echo "[$TIMESTAMP] ✅ AGENT OS REBOOT COMPLETE." | tee -a $LOG_FILE
sed -i "s/\*Last System Reboot: .*\*/*Last System Reboot: $TIMESTAMP*/" $HOME/agentmanager/README.md
echo "--------------------------------------------------------"
echo "System has been reconnected to the Data Layer truth center."
echo "Master README updated: $HOME/agentmanager/README.md"
