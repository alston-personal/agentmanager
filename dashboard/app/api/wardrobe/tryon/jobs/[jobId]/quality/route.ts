import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { setTryOnQuality } from '@/lib/tryon-jobs';

function getAdmin(request: NextRequest) {
  const candidates = request.cookies.getAll('auth_token').map((row) => row.value).filter(Boolean);
  for (const token of candidates) {
    const identity = verifyToken(token);
    if (identity?.username && isMilkcatAdmin(identity)) return identity;
  }
  return null;
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> }
) {
  const admin = getAdmin(request);
  if (!admin) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }

  try {
    const { jobId } = await context.params;
    const body = await request.json();
    if (typeof body?.accepted !== 'boolean') {
      return NextResponse.json({ error: 'accepted must be boolean' }, { status: 400 });
    }
    const issues = Array.isArray(body?.issues)
      ? body.issues.map((value: unknown) => String(value))
      : [];

    const job = setTryOnQuality({
      jobId,
      accepted: body.accepted,
      issues,
      reviewer: String(admin.username || ''),
    });

    return NextResponse.json({
      success: true,
      jobId: job.jobId,
      accepted: job.output.quality?.accepted === true,
      checkedAt: job.output.quality?.checkedAt || null,
      cacheReusable: job.output.quality?.accepted === true,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to review try-on quality';
    const status = message === 'Try-on job not found' ? 404 : 400;
    return NextResponse.json({ error: message }, { status });
  }
}
