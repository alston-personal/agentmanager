import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
import type { ResolvedProduct } from './wardrobe-ingest';
import { normalizeWardrobeLayer } from './wardrobe-layers.mjs';

export const ISOLATION_JOB_SCHEMA = 'agentos.wardrobe-isolation-job/v1' as const;
const ROOT = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator');
const JOB_DIR = path.join(ROOT, 'isolation_jobs');

export function enqueueIsolatedProduct(product: ResolvedProduct, garmentId: string) {
  if (!/^[A-Za-z0-9._-]{1,160}$/.test(garmentId)) throw new Error('invalid garmentId');
  if (!product.imageUrl || !product.imageUrl.startsWith('https://')) {
    throw new Error('product_image_unavailable_for_isolation');
  }
  const sourceFingerprint = createHash('sha256').update(product.imageUrl).digest('hex');
  const file = path.join(JOB_DIR, garmentId + '.json');
  if (fs.existsSync(file)) {
    try {
      const existing = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (existing.schema === ISOLATION_JOB_SCHEMA && existing.sourceFingerprint === sourceFingerprint) return existing;
    } catch { /* recover corrupt queue record */ }
  }
  const job = {
    schema: ISOLATION_JOB_SCHEMA,
    garmentId,
    sourceImageUrl: product.imageUrl,
    sourceFingerprint,
    targetLayer: normalizeWardrobeLayer(product.slot),
    productName: product.name,
    state: 'pending',
    isolatedImageUrl: null,
    maskUrl: null,
    productIR: null,
    approval: null,
    createdAt: new Date().toISOString(),
  };
  fs.mkdirSync(JOB_DIR, { recursive: true, mode: 0o700 });
  const temp = file + '.tmp';
  fs.writeFileSync(temp, JSON.stringify(job, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(temp, file);
  return job;
}
