module.exports = {
  apps : [{
    name: "tg-commander",
    script: "/home/ubuntu/agentmanager/.venv/bin/python3",
    args: "scripts/tg_bridge.py",
    cwd: "/home/ubuntu/agentmanager",
    autorestart: true,
    watch: false,
    max_memory_restart: "200M"
  }]
};
