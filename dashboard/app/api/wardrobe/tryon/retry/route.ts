import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { createTryOnJob, readJob } from '@/lib/tryon-jobs';

function getAdmin(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  const identity = verifyToken(token);
  if (!identity || !identity.username || !isMilkcatAdmin(identity)) return null;
  return identity;
}

export async function POST(request: NextRequest) {
  if (!getAdmin(request)) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }

  try {
    const body = await request.json();
    const oldJob = readJob(String(body?.jobId || ''));
    if (!oldJob) return NextResponse.json({ error: 'Try-on job not found' }, { status: 404 });

    const job = createTryOnJob({
      characterId: oldJob.characterId,
      selectedLayers: oldJob.input.selectedLayers,
      baseBodyAsset: oldJob.input.baseBodyAsset,
    });

    return NextResponse.json({
      success: true,
      retriedFrom: oldJob.jobId,
      jobId: job.jobId,
      status: job.status,
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Failed to retry try-on job',
    }, { status: 400 });
  }
}
