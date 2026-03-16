import path from 'path';

const DEFAULT_DATA_ROOT = '/home/ubuntu/agent-data';

export const AGENT_DATA_ROOT = process.env.AGENT_DATA_ROOT || DEFAULT_DATA_ROOT;
export const DATA_PROJECTS_DIR = path.join(AGENT_DATA_ROOT, 'projects');
export const DATA_DASHBOARD_PATH = path.join(AGENT_DATA_ROOT, 'DASHBOARD.md');
