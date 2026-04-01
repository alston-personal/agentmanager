module.exports = {
  apps : [{
    name: "tg-commander",
    script: "python3",
    args: "scripts/tg_bridge.py",
    cwd: "/home/ubuntu/agentmanager",
    autorestart: true,
    watch: false,
    max_memory_restart: "200M"
  },
  {
    name: "os-pulse",
    script: "python3",
    args: "scripts/pulse.py --agent Architect --task 'Heartbeat Monitor' --status active",
    cwd: "/home/ubuntu/agentmanager",
    autorestart: true,
    watch: false
  }]
};
