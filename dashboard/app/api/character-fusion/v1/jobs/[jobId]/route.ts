import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { readCharacterFusionJob } from '@/lib/character-fusion-jobs';

function username(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  return verifyToken(token)?.username || null;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> }
) {
  const user = username(request);
  if (!user) return NextResponse.json({ error: 'Login required' }, { status: 401 });

  const { jobId } = await context.params;
  const job = readCharacterFusionJob(jobId);
  if (!job) return NextResponse.json({ error: 'Job not found' }, { status: 404 });
  if (job.requestedBy !== user) return NextResponse.json({ error: 'Forbidden' }, { status: 403 });

  return NextResponse.json({
    ...job,
    input: {
      personAsset: Boolean(job.input.personAsset),
      mainVisualAsset: Boolean(job.input.mainVisualAsset),
    },
  });
}
