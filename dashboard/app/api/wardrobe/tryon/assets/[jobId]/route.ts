import fs from 'node:fs';
import path from 'node:path';
import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

function authorized(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return false;
  const identity = verifyToken(token);
  return Boolean(identity?.username);
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ jobId: string }> }
) {
  if (!authorized(request)) {
    return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
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
  const contentType =
    data.subarray(0, 4).toString('ascii') === 'RIFF' && data.subarray(8, 12).toString('ascii') === 'WEBP'
      ? 'image/webp'
      : data.subarray(0, 8).equals(Buffer.from([0x89,0x50,0x4e,0x47,0x0d,0x0a,0x1a,0x0a]))
        ? 'image/png'
        : data[0] === 0xff && data[1] === 0xd8
          ? 'image/jpeg'
          : 'application/octet-stream';
  return new NextResponse(data, {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Cache-Control': 'private, max-age=31536000, immutable',
    },
  });
}
