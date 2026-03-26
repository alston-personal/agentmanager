import os
import sys
import argparse
import subprocess
import shutil

def run_cmd(cmd, cwd=None, shell=True):
    print(f"🚀 Executing: {cmd}")
    result = subprocess.run(cmd, cwd=cwd, shell=shell, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        return False, result.stderr
    return True, result.stdout

class DeployCore:
    def __init__(self, project_name, domain, port=3000):
        self.project_name = project_name
        self.domain = domain
        self.port = port
        self.workspace_root = "/home/ubuntu/agentmanager/workspace"
        self.project_path = self._find_project_path()

    def _find_project_path(self):
        possible_path = os.path.join(self.workspace_root, self.project_name)
        if os.path.islink(possible_path):
            return os.readlink(possible_path)
        if os.path.exists(possible_path):
            return possible_path
        # Try direct home path
        direct_path = f"/home/ubuntu/{self.project_name}"
        if os.path.exists(direct_path):
            return direct_path
        raise FileNotFoundError(f"Could not find project: {self.project_name}")

    def detect_type(self):
        if os.path.exists(os.path.join(self.project_path, 'next.config.js')) or \
           os.path.exists(os.path.join(self.project_path, 'next.config.mjs')):
            return "Next.js"
        if os.path.exists(os.path.join(self.project_path, 'package.json')):
            return "Node.js"
        return "Unknown"

    def setup_pm2(self):
        print("⚙️ Setting up PM2...")
        ecosystem_content = f"""
module.exports = {{
  apps: [{{
    name: '{self.project_name}',
    script: 'npm',
    args: 'start',
    cwd: '{self.project_path}',
    instances: 1,
    autorestart: true,
    env: {{
      NODE_ENV: 'production',
      PORT: {self.port}
    }}
  }}]
}}
"""
        config_path = os.path.join(self.project_path, 'ecosystem.config.js')
        with open(config_path, 'w') as f:
            f.write(ecosystem_content)
        
        run_cmd(f"pm2 startOrReload {config_path} --update-env")
        run_cmd("pm2 save")

    def setup_nginx(self):
        print("🌐 Setting up Nginx...")
        nginx_content = f"""
server {{
    listen 80;
    server_name {self.domain};

    location / {{
        proxy_pass http://localhost:{self.port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
}}
"""
        avail_path = f"/etc/nginx/sites-available/{self.domain}"
        # We need sudo for this, assuming the script runs with enough privileges or agent can use sudo
        temp_path = f"/tmp/nginx_{self.domain}"
        with open(temp_path, 'w') as f:
            f.write(nginx_content)
        
        run_cmd(f"sudo mv {temp_path} {avail_path}")
        run_cmd(f"sudo ln -sf {avail_path} /etc/nginx/sites-enabled/")
        run_cmd("sudo nginx -t && sudo systemctl reload nginx")

    def run_build(self):
        print("🏗️ Running Build...")
        run_cmd("npm install --production", cwd=self.project_path)
        run_cmd("npm run build", cwd=self.project_path)

    def deploy(self):
        ptype = self.detect_type()
        print(f"📦 Detected project type: {ptype}")
        if ptype == "Unknown":
            print("⚠️ Unknown project type, proceeding with generic Node.js deployment.")
        
        self.run_build()
        self.setup_pm2()
        self.setup_nginx()
        print(f"✅ Deployment of {self.project_name} to {self.domain} completed!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    engine = DeployCore(args.project, args.domain, args.port)
    engine.deploy()
