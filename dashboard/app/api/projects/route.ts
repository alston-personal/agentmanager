import { NextResponse } from 'next/server';
import { execFileSync } from 'child_process';
import path from 'path';
import fs from 'fs';
import { getAllProjects, parseDashboard } from '@/lib/markdown-parser';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

type ParsedMemorySystem = {
  name?: string;
  kind?: string;
  status?: string;
  item_count?: number;
  size_bytes?: number;
  notes?: string[];
  path?: string;
};

type ParsedAgentOSStatus = {
  roles?: unknown[];
  projects?: { status?: string }[];
  specs?: { notes?: string[] }[];
  recommendations?: string[];
  memory_systems?: ParsedMemorySystem[];
};

export async function GET() {
  try {
    const projects = getAllProjects();
    const { services, ideas } = parseDashboard();
    const agentosStatus = getAgentOSStatus();

    // Read likes
    let likes: Record<string, number> = {};
    try {
      const likesPath = path.join(AGENT_DATA_ROOT, 'likes.json');
      if (fs.existsSync(likesPath)) {
        likes = JSON.parse(fs.readFileSync(likesPath, 'utf-8'));
      }
    } catch (e) {
      console.error('Failed to read likes in projects api:', e);
    }

    const projectsWithLikes = projects.map(p => ({
      ...p,
      likes: likes[p.name] || 0,
    }));

    return NextResponse.json({
      projects: projectsWithLikes,
      services,
      ideas,
      agentosStatus,
      lastSync: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error fetching projects:', error);
    return NextResponse.json(
      { error: 'Failed to fetch projects' },
      { status: 500 }
    );
  }
}

function getAgentOSStatus() {
  try {
    const projectRoot = path.join(process.cwd(), '..');
    const scriptPath = path.join(projectRoot, 'scripts', 'agentos_status.py');
    const output = execFileSync('python3', [scriptPath, '--json'], {
      cwd: projectRoot,
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024,
    });
    const parsed = JSON.parse(output) as ParsedAgentOSStatus;
    return {
      generatedAt: new Date().toISOString(),
      roleCount: parsed?.roles?.length || 0,
      projectCount: parsed?.projects?.length || 0,
      specCount: parsed?.specs?.length || 0,
      proposedProjectCount: Array.isArray(parsed?.projects)
        ? parsed.projects.filter((p: { status?: string }) => String(p.status || '').includes('Proposed')).length
        : 0,
      legacySpecCount: Array.isArray(parsed?.specs)
        ? parsed.specs.filter((s: { notes?: string[] }) => Array.isArray(s.notes) && s.notes.some((note) => note.includes('owner missing') || note.includes('targets missing'))).length
        : 0,
      watchlist: Array.isArray(parsed?.recommendations) ? parsed.recommendations.slice(0, 4) : [],
      memorySystems: Array.isArray(parsed?.memory_systems)
        ? parsed.memory_systems.map((system) => ({
            name: system.name,
            kind: system.kind,
            status: system.status,
            items: system.item_count || 0,
            sizeBytes: system.size_bytes || 0,
            notes: Array.isArray(system.notes) ? system.notes : [],
            path: system.path,
          }))
        : [],
      recommendations: Array.isArray(parsed?.recommendations) ? parsed.recommendations : [],
    };
  } catch (error) {
    console.error('Error loading AgentOS status:', error);
    return {
      generatedAt: new Date().toISOString(),
      roleCount: 0,
      projectCount: 0,
      specCount: 0,
      proposedProjectCount: 0,
      legacySpecCount: 0,
      watchlist: ['AgentOS status unavailable'],
      memorySystems: [],
      recommendations: [],
    };
  }
}
