import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { readJob, writeJob } from '@/lib/tryon-jobs';

function authorized(request: NextRequest): boolean {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return false;
  const identity = verifyToken(token);
  return Boolean(identity?.username && isMilkcatAdmin(identity));
}

const ALLOWED_ISSUES = new Set(['garment_or_stray_object', 'body_deformation']);

export async function POST(
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
    if (job.status !== 'ready' || !job.output?.asset) {
      return NextResponse.json({ error: 'Only rendered candidates may be reviewed' }, { status: 409 });
    }
    const body: unknown = await request.json();
    if (!body || typeof body !== 'object' || Array.isArray(body)) {
      return NextResponse.json({ error: 'Invalid review payload' }, { status: 400 });
    }
    const review = body as Record<string, unknown>;
    if (typeof review.accepted !== 'boolean' || !Array.isArray(review.issues)
        || !review.issues.every((item) => typeof item === 'string' && ALLOWED_ISSUES.has(item))) {
      return NextResponse.json({ error: 'Invalid review decision or issues' }, { status: 400 });
    }
    const accepted = review.accepted;
    if ((accepted && review.issues.length > 0) || (!accepted && review.issues.length === 0)) {
      return NextResponse.json({ error: 'Review decision and issues disagree' }, { status: 400 });
    }
    const selected = Object.keys(job.input?.selectedLayers || {});
    const rendered = new Set(job.output.renderedLayers || []);
    const pending = job.output.pendingLayers || [];
    if (accepted && (!selected.length || pending.length || selected.some((layer) => !rendered.has(layer)))) {
      return NextResponse.json({ error: 'Incomplete render cannot be approved' }, { status: 409 });
    }
    job.output = {
      ...job.output,
      quality: {
        accepted,
        checkedAt: new Date().toISOString(),
        checks: [{ code: 'admin_visual_review', passed: accepted }],
        issues: review.issues as string[],
      },
    };
    writeJob(job);
    return NextResponse.json({ ok: true, jobId, quality: job.output.quality });
  } catch {
    return NextResponse.json({ error: 'Invalid review or job ID' }, { status: 400 });
  }
}
