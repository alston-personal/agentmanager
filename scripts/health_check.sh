#!/bin/bash

# 🧟 AgentOS Health Check & Zombie Prevention Script
# Version: 1.0.0
# Description: Checks for logic/data mismatches, broken symlinks, and oversized files.

LOG_FILE="/home/ubuntu/agentmanager/maintenance.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo "[$TIMESTAMP] 🔍 Starting Health Check..." >> $LOG_FILE

# 1. Check for real directories in workspace/ (should be symlinks)
echo "Checking for misplaced logic repos in workspace/..."
MISPLACED=$(ls -F /home/ubuntu/agentmanager/workspace/ | grep -v "/$" | grep -v "@$")
REAL_DIRS=$(ls -F /home/ubuntu/agentmanager/workspace/ | grep "/$")

if [ ! -z "$REAL_DIRS" ]; then
    echo "⚠️ WARNING: Found real directories in workspace/ which should be symlinks:" >> $LOG_FILE
    echo "$REAL_DIRS" >> $LOG_FILE
fi

# 2. Check for broken symlinks
BROKEN=$(find /home/ubuntu/agentmanager -xtype l)
if [ ! -z "$BROKEN" ]; then
    echo "🚨 ERROR: Found broken symlinks:" >> $LOG_FILE
    echo "$BROKEN" >> $LOG_FILE
fi

# 3. Check for oversized folders (Watcher Protection)
# Check node_modules outside of dashboard/ (if any)
LARGE_REPOS=$(du -sh /home/ubuntu/agentmanager/* | grep 'G' | grep -v 'dashboard')
if [ ! -z "$LARGE_REPOS" ]; then
    echo "📊 INFO: Large repositories detected (possible VSCode lag risk):" >> $LOG_FILE
    echo "$LARGE_REPOS" >> $LOG_FILE
fi

echo "[$TIMESTAMP] ✅ Health Check Complete." >> $LOG_FILE
echo "Maintenance complete."
