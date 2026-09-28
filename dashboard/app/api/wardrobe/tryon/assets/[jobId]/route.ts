import fs from 'node:fs';
import path from 'node:path';
import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

function authorized(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return false;
  const identity = verifyToken(token);
  return Boolean(identity?.username && isMilkcatAdmin(identity));
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> }
) {
  if (!authorized(request)) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }
  const { jobId } = await context.params;
  if (!/^[A-Za-z0-9._-]{1,220}$/.test(jobId)) {
    return NextResponse.json({ error: 'Invalid jobId' }, { status: 400 });
  }
  const file = path.join(
    AGENT_DATA_ROOT,
    'projects',
    'dressup-simulator',
    'render_assets',
    jobId + '.webp'
  );
  if (!fs.existsSync(file)) {
    return NextResponse.json({ error: 'Render asset not found' }, { status: 404 });
  }
  const data = fs.readFileSync(file);
  return new NextResponse(data, {
    status: 200,
    headers: {
      'Content-Type': 'image/webp',
      'Cache-Control': 'private, max-age=31536000, immutable',
    },
  });
}
