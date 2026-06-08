// TypeScript type definitions for the AI Command Center Dashboard

export interface Project {
  name: string;
  displayName: string;
  icon: string;
  status: ProjectStatus;
  lastUpdated: string;
  link?: string;
  path: string;
  summary?: ProjectSummary;
  activityLog: ActivityLogEntry[];
  todoList: TodoItem[];
  blockers: string[];
}

export interface ProjectSummary {
  lastStatus: string;
  lastUpdated: string;
}

export interface ActivityLogEntry {
  timestamp: string;
  level: 'DONE' | 'INFO' | 'WARNING' | 'ERROR';
  message: string;
}

export interface TodoItem {
  text: string;
  completed: boolean;
  children?: TodoItem[];
}

export type ProjectStatus =
  | '🟢 Active'
  | '🚧 In Progress'
  | '✅ Complete'
  | '❌ Failed'
  | '⚡ Testing'
  | '🆕 Registered'
  | string;

export interface DashboardData {
  projects: Project[];
  services: Service[];
  ideas: Idea[];
  agentosStatus: AgentOSStatus;
  lastSync: string;
}

export interface AgentOSStatus {
  generatedAt: string;
  roleCount: number;
  projectCount: number;
  specCount: number;
  proposedProjectCount: number;
  legacySpecCount: number;
  watchlist: string[];
  memorySystems: MemorySystem[];
  recommendations: string[];
}

export interface MemorySystem {
  name: string;
  kind: string;
  status: string;
  items: number;
  sizeBytes: number;
  notes: string[];
  path: string;
}

export interface Service {
  name: string;
  role: string;
  path: string;
  status: string;
}

export interface Idea {
  name: string;
  description: string;
  stage: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  command: string;
  steps: string[];
  turbo?: boolean;
  turboAll?: boolean;
}

export interface WorkflowExecution {
  workflowId: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startTime: string;
  endTime?: string;
  logs: string[];
  error?: string;
}

export interface User {
  username: string;
  passwordHash: string;
}

export interface AuthToken {
  username: string;
  exp: number;
}
