import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { readJob } from '@/lib/tryon-jobs';

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

  try {
    const { jobId } = await context.params;
    const job = readJob(jobId);
    if (!job) return NextResponse.json({ error: 'Try-on job not found' }, { status: 404 });
    return NextResponse.json(job);
  } catch {
    return NextResponse.json({ error: 'Invalid jobId' }, { status: 400 });
  }
}
