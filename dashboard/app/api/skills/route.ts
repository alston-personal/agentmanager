import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { Capability } from '@/lib/types';

const execFileAsync = promisify(execFile);
const PROJECT_ROOT = path.join(process.cwd(), '..');
const CAPABILITIES_FILE = path.join(PROJECT_ROOT, '.agent', 'CAPABILITIES.md');
const LCS_PROMOTION_SCRIPT = path.join(PROJECT_ROOT, 'scripts', 'core_services', 'lcs_synthesis.py');

export async function GET() {
  try {
    const content = await fs.readFile(CAPABILITIES_FILE, 'utf-8');
    const capabilities: Capability[] = [];
    
    // Simple markdown table parser
    const lines = content.split('\n');
    let insideTable = false;
    
    for (const line of lines) {
      if (line.trim().startsWith('| 功能名稱 |') || line.trim().startsWith('| Capability |')) {
        insideTable = true;
        continue;
      }
      
      if (insideTable && line.trim().startsWith('| :---')) {
        continue;
      }
      
      if (insideTable && line.trim() === '') {
        insideTable = false;
        continue;
      }
      
      if (insideTable && line.trim().startsWith('|')) {
        const parts = line.split('|').map(s => s.trim());
        if (parts.length >= 5) {
          // Extract plain text from markdown strong tags etc
          const name = parts[1].replace(/[*_]/g, '');
          const path = parts[2].replace(/[`]/g, '');
          const role = parts[3];
          const status = parts[4];
          const desc = parts[5];
          
          capabilities.push({
            name,
            path,
            role,
            status,
            description: desc
          });
        }
      }
    }
    
    return NextResponse.json({ capabilities });
  } catch (error) {
    console.error('Failed to read capabilities:', error);
    return NextResponse.json({ capabilities: [] });
  }
}

export async function POST(request: NextRequest) {
  try {
    const { sourcePath, skillName, description, role } = await request.json();

    if (!sourcePath || !skillName || !description || !role) {
      return NextResponse.json(
        { error: 'Missing required fields' },
        { status: 400 }
      );
    }

    const { stdout, stderr } = await execFileAsync(
      'python3',
      [LCS_PROMOTION_SCRIPT, sourcePath, skillName, description, role],
      {
        cwd: PROJECT_ROOT,
        timeout: 30000,
      }
    );

    const output = (stdout || stderr || '').trim();

    return NextResponse.json({
      status: 'success',
      message: output,
    });

  } catch (error: any) {
    console.error('Skill promotion failed:', error);
    return NextResponse.json(
      { error: error.message || 'Promotion failed' },
      { status: 500 }
    );
  }
}
