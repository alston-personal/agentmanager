import { NextRequest, NextResponse } from 'next/server';
import fs from 'node:fs';
import path from 'node:path';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
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
    const root = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator');
    const assetPath = path.join(root, 'render_assets', jobId + '.webp');
    if (!fs.existsSync(assetPath) || fs.statSync(assetPath).size <= 1000) {
      return NextResponse.json({ error: 'Rendered image is missing; cannot approve a placeholder' }, { status: 409 });
    }
    const quality = {
      accepted,
      checkedAt: new Date().toISOString(),
      checks: [{ code: 'admin_visual_review', passed: accepted }],
      issues: review.issues as string[],
    };
    // Persist cache eligibility first. A failed cache-write must not leave the
    // job reporting an accepted result while the worker rejects its cache.
    const cacheKey = job.output.cacheKey;
    if (typeof cacheKey === 'string' && /^[0-9a-f]{64}$/.test(cacheKey)) {
      const dir = path.join(root, 'render_cache');
      const cacheAsset = path.join(dir, cacheKey + '.webp');
      if (fs.existsSync(cacheAsset) && fs.statSync(cacheAsset).size > 1000) {
        const sidecar = path.join(dir, cacheKey + '.json');
        const temporary = sidecar + '.' + process.pid + '.' + Date.now() + '.tmp';
        const receipt = {
          schema: 'agentos.tryon-cache-review/v1',
          cacheKey,
          qualityAccepted: accepted,
          reviewedAt: quality.checkedAt,
          reviewJobId: jobId,
          issues: review.issues,
        };
        try {
          fs.writeFileSync(temporary, JSON.stringify(receipt) + '\n', { mode: 0o600 });
          fs.renameSync(temporary, sidecar);
        } finally {
          try { fs.unlinkSync(temporary); } catch { /* already renamed or missing */ }
        }
      }
    }
    job.output = { ...job.output, quality };
    writeJob(job);
    return NextResponse.json({ ok: true, jobId, quality: job.output.quality });
  } catch {
    return NextResponse.json({ error: 'Invalid review or job ID' }, { status: 400 });
  }
}
