# AI Command Center Dashboard

## Environment Variables

Create a `.env.local` file in the dashboard directory:

```env
# GitHub API (optional - for future GitHub integration)
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=alstonhuang/AI_Command_Center

# Authentication
JWT_SECRET=your-secret-key-change-in-production
ADMIN_USERNAME=admin
# Leave empty to use default password 'admin' for development
# For production, generate hash with: node -e "const bcrypt = require('bcryptjs'); bcrypt.hash('your-password', 10).then(console.log)"
ADMIN_PASSWORD_HASH=
```

## Default Credentials

- Username: `admin`
- Password: `admin`

## Development

```bash
cd /home/ubuntu/agentmanager/dashboard
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Features

- 📊 **Dashboard**: View all projects with status, progress, and stats
- 🔍 **Search & Filter**: Find projects by name or status
- 📈 **Charts**: Visualize project distribution
- 📝 **Project Details**: View activity logs, todos, and blockers
- ⚡ **Workflows**: Execute automation workflows (requires authentication)
- 🔐 **Authentication**: Secure workflow execution with JWT

## Production Deployment

1. Set strong `JWT_SECRET`
2. Generate password hash and set `ADMIN_PASSWORD_HASH`
3. Build: `npm run build`
4. Start: `npm start`
