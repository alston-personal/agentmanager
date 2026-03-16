import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';
import { Project, ActivityLogEntry, TodoItem, ProjectSummary } from './types';
import { DATA_DASHBOARD_PATH, DATA_PROJECTS_DIR } from './data-root';

const PROJECTS_DIR = DATA_PROJECTS_DIR;
const DASHBOARD_PATH = DATA_DASHBOARD_PATH;

/**
 * Parse STATUS.md file and extract project information
 */
export function parseStatusFile(projectName: string): Partial<Project> | null {
  const statusPath = path.join(PROJECTS_DIR, projectName, 'STATUS.md');

  if (!fs.existsSync(statusPath)) {
    return null;
  }

  const content = fs.readFileSync(statusPath, 'utf-8');

  // Parse summary table
  const summary = parseSummaryTable(content);

  // Parse activity log
  const activityLog = parseActivityLog(content);

  // Parse todo list
  const todoList = parseTodoList(content);

  // Parse blockers
  const blockers = parseBlockers(content);

  return {
    name: projectName,
    summary,
    activityLog,
    todoList,
    blockers,
  };
}

/**
 * Parse the summary table from STATUS.md
 */
function parseSummaryTable(content: string): ProjectSummary | undefined {
  const summaryMatch = content.match(/## 📍 Summary\s*\n\|[^\n]+\n\|[^\n]+\n\|[^|]+\|\s*([^|]+)\s*\|\s*\n\|[^|]+\|\s*([^|]+)\s*\|/);

  if (summaryMatch) {
    return {
      lastStatus: summaryMatch[1].trim(),
      lastUpdated: summaryMatch[2].trim(),
    };
  }

  return undefined;
}

/**
 * Parse activity log entries
 */
function parseActivityLog(content: string): ActivityLogEntry[] {
  const logSection = content.match(/<!-- LOG_START -->([\s\S]*?)<!-- LOG_END -->/);

  if (!logSection) {
    return [];
  }

  const entries: ActivityLogEntry[] = [];
  const lines = logSection[1].split('\n');

  for (const line of lines) {
    const match = line.match(/- `([^`]+)` (✅|ℹ️|⚠️|❌) \*\*([^*]+)\*\*: (.+)/);

    if (match) {
      const [, timestamp, emoji, levelText, message] = match;

      let level: ActivityLogEntry['level'] = 'INFO';
      if (levelText === 'DONE') level = 'DONE';
      else if (levelText === 'WARNING') level = 'WARNING';
      else if (levelText === 'ERROR') level = 'ERROR';

      entries.push({
        timestamp,
        level,
        message,
      });
    }
  }

  return entries;
}

/**
 * Parse todo list items
 */
function parseTodoList(content: string): TodoItem[] {
  const todoSection = content.match(/## 📅 Todo List\s*\n([\s\S]*?)(?=\n##|$)/);

  if (!todoSection) {
    return [];
  }

  const items: TodoItem[] = [];
  const lines = todoSection[1].split('\n');

  for (const line of lines) {
    const match = line.match(/^(\s*)- \[([ xX])\] (.+)$/);

    if (match) {
      const [, indent, check, text] = match;
      const completed = check.toLowerCase() === 'x';

      items.push({
        text: text.trim(),
        completed,
      });
    }
  }

  return items;
}

/**
 * Parse blockers section
 */
function parseBlockers(content: string): string[] {
  const blockersSection = content.match(/## 🛑 Blockers & Issues\s*\n([\s\S]*?)(?=\n##|$)/);

  if (!blockersSection) {
    return [];
  }

  const blockers: string[] = [];
  const lines = blockersSection[1].split('\n');

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed && trimmed !== '- None yet.' && trimmed !== '- None currently.') {
      blockers.push(trimmed.replace(/^- /, ''));
    }
  }

  return blockers;
}

/**
 * Parse DASHBOARD.md to get project list
 */
export function parseDashboard(): { projects: any[], services: any[], ideas: any[] } {
  if (!fs.existsSync(DASHBOARD_PATH)) {
    return { projects: [], services: [], ideas: [] };
  }

  const content = fs.readFileSync(DASHBOARD_PATH, 'utf-8');

  const projects = parseProjectsTable(content);
  const services = parseServicesTable(content);
  const ideas = parseIdeasTable(content);

  return { projects, services, ideas };
}

/**
 * Parse projects table from DASHBOARD.md
 */
function parseProjectsTable(content: string): any[] {
  const projectsSection = content.match(/## 🔥 Active Projects & Resources\s*\n\|[^\n]+\n\|[^\n]+\n([\s\S]*?)(?=\n##|$)/);

  if (!projectsSection) {
    return [];
  }

  const projects: any[] = [];
  const lines = projectsSection[1].split('\n');

  for (const line of lines) {
    const match = line.match(/\|\s*([^|]+)\s*\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|/);

    if (match) {
      const [, icon, name, link, status] = match;

      projects.push({
        icon: icon.trim(),
        name: name.trim(),
        link: link.trim(),
        status: status.trim(),
      });
    }
  }

  return projects;
}

/**
 * Parse services table from DASHBOARD.md
 */
function parseServicesTable(content: string): any[] {
  const servicesSection = content.match(/## ⚙️ 系統服務[^\n]*\n\|[^\n]+\n\|[^\n]+\n([\s\S]*?)(?=\n##|$)/);

  if (!servicesSection) {
    return [];
  }

  const services: any[] = [];
  const lines = servicesSection[1].split('\n');

  for (const line of lines) {
    const match = line.match(/\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|/);

    if (match) {
      const [, name, role, path, status] = match;

      services.push({
        name: name.trim(),
        role: role.trim(),
        path: path.trim(),
        status: status.trim(),
      });
    }
  }

  return services;
}

/**
 * Parse ideas table from DASHBOARD.md
 */
function parseIdeasTable(content: string): any[] {
  const ideasSection = content.match(/## [^#]+ 專案孵化器[^\n]*\n\|[^\n]+\n\|[^\n]+\n([\s\S]*?)(?=\n##|$)/);

  if (!ideasSection) {
    return [];
  }

  const ideas: any[] = [];
  const lines = ideasSection[1].split('\n');

  for (const line of lines) {
    const match = line.match(/\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|/);

    if (match) {
      const [, name, description, stage] = match;

      ideas.push({
        name: name.trim(),
        description: description.trim(),
        stage: stage.trim(),
      });
    }
  }

  return ideas;
}

/**
 * Get all projects by combining DASHBOARD.md and STATUS.md files
 */
export function getAllProjects(): Project[] {
  const { projects: dashboardProjects } = parseDashboard();
  const projects: Project[] = [];

  // Get all project directories
  if (fs.existsSync(PROJECTS_DIR)) {
    const dirs = fs.readdirSync(PROJECTS_DIR, { withFileTypes: true });

    for (const dir of dirs) {
      if (dir.isDirectory()) {
        const projectName = dir.name;
        const statusData = parseStatusFile(projectName);

        if (statusData) {
          // Find matching dashboard entry
          const dashboardEntry = dashboardProjects.find(
            p => p.name === projectName || p.name.replace(/-/g, '_') === projectName
          );

          projects.push({
            name: projectName,
            displayName: dashboardEntry?.name || projectName,
            icon: dashboardEntry?.icon || '📦',
            status: statusData.summary?.lastStatus || '🆕 Registered',
            lastUpdated: statusData.summary?.lastUpdated || 'Unknown',
            link: dashboardEntry?.link,
            path: `/projects/${projectName}`,
            summary: statusData.summary,
            activityLog: statusData.activityLog || [],
            todoList: statusData.todoList || [],
            blockers: statusData.blockers || [],
          });
        }
      }
    }
  }

  return projects;
}
