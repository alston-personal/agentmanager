import fs from 'node:fs';
import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { readCharacterFusionJob } from '@/lib/character-fusion-jobs';

function username(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  return verifyToken(token)?.username || null;
}

function contentType(data: Buffer) {
  if (data.subarray(0, 8).equals(Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]))) return 'image/png';
  if (data.subarray(0, 4).toString('ascii') === 'RIFF' && data.subarray(8, 12).toString('ascii') === 'WEBP') return 'image/webp';
  if (data[0] === 0xff && data[1] === 0xd8) return 'image/jpeg';
  return 'application/octet-stream';
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
  if (job.status !== 'ready' || !job.output.asset || !fs.existsSync(job.output.asset)) {
    return NextResponse.json({ error: 'Asset not ready' }, { status: 404 });
  }

  const data = fs.readFileSync(job.output.asset);
  return new NextResponse(data, {
    status: 200,
    headers: {
      'Content-Type': contentType(data),
      'Cache-Control': 'private, max-age=31536000, immutable',
    },
  });
}
