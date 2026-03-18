import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { execFile } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execFileAsync = promisify(execFile);
const PROJECT_ROOT = path.join(process.cwd(), '..');
const WORKFLOW_RUNNER = path.join(PROJECT_ROOT, 'scripts', 'run_workflow.py');

export async function POST(request: NextRequest) {
  try {
    // Verify authentication
    const authHeader = request.headers.get('authorization');
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    const token = authHeader.substring(7);
    const user = verifyToken(token);

    if (!user) {
      return NextResponse.json(
        { error: 'Invalid token' },
        { status: 401 }
      );
    }

    const { workflowId, parameters } = await request.json();

    if (!workflowId) {
      return NextResponse.json(
        { error: 'Workflow ID is required' },
        { status: 400 }
      );
    }

    const normalizedWorkflow = workflowId.replace(/^workflow-/, '').replace(/^skill-[^-]+-/, '');
    const { stdout, stderr } = await execFileAsync(
      'python3',
      [WORKFLOW_RUNNER, normalizedWorkflow],
      {
        cwd: PROJECT_ROOT,
        timeout: 30000,
      }
    );

    const output = (stdout || stderr || '').trim();

    return NextResponse.json({
      status: 'completed',
      message: output || `Workflow /${normalizedWorkflow} completed`,
      workflowId,
      parameters,
      output,
      executedBy: user.username,
    });

  } catch (error) {
    console.error('Workflow execution error:', error);
    return NextResponse.json(
      { error: 'Workflow execution failed' },
      { status: 500 }
    );
  }
}
