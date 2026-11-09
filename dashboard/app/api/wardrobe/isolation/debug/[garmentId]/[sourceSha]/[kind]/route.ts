import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const ROOT = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator', 'isolation_candidates');
const ID = /^(?!\.{1,2}$)[A-Za-z0-9._-]{1,160}$/;
const SHA = /^[a-f0-9]{64}$/;
const KINDS = ['receipt', 'garment', 'mask'] as const;

function authenticated(request: NextRequest): boolean {
  return request.cookies.getAll('auth_token').some(({value}) => {
    const identity = verifyToken(value);
    return Boolean(identity?.username && isMilkcatAdmin(identity));
  });
}

export async function GET(request: NextRequest, context: {
  params: Promise<{ garmentId: string; sourceSha: string; kind: string }>
}) {
  if (!authenticated(request)) {
    return NextResponse.json({error:'Admin authentication required'}, {status:401,headers:{'Cache-Control':'no-store'}});
  }
  const {garmentId, sourceSha, kind} = await context.params;
  if (!ID.test(garmentId) || !SHA.test(sourceSha) || !KINDS.includes(kind as typeof KINDS[number])) {
    return NextResponse.json({error:'Invalid artifact selector'}, {status:400});
  }
  const dir = path.join(ROOT, garmentId, sourceSha);
  const receiptPath = path.join(dir, 'candidate-receipt.json');
  try {
    const receiptStats = fs.lstatSync(receiptPath);
    if (!receiptStats.isFile() || receiptStats.isSymbolicLink()) throw new Error('Invalid receipt');
    const receipt = JSON.parse(fs.readFileSync(receiptPath, 'utf8'));
    if (receipt.garmentId !== garmentId || receipt.sourceAssetSha256 !== sourceSha) throw new Error('Receipt mismatch');
    if (kind === 'receipt') {
      // Receipt includes local filesystem paths; never expose them as-is.
      const safe = {
        schema: receipt.schema, garmentId, sourceSha, state:receipt.state,
        extractorOutcome:receipt.extractorOutcome, extractor:receipt.extractor,
        approved:receipt.approved === true,
        productIR:receipt.productIR,
        review:receipt.review,
        isolatedAssetSha256:receipt.isolatedAssetSha256,
        maskSha256:receipt.maskSha256,
      };
      return NextResponse.json(safe, {headers:{'Cache-Control':'private, no-store'}});
    }
    const assetName = kind === 'garment' ? 'garment.png' : 'garment.mask.png';
    const asset = path.join(dir, assetName);
    const stat = fs.lstatSync(asset);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 15_000_000) throw new Error('Invalid asset');
    const bytes = fs.readFileSync(asset);
    const digest = crypto.createHash('sha256').update(bytes).digest('hex');
    const expected = kind === 'garment' ? receipt.isolatedAssetSha256 : receipt.maskSha256;
    if (!expected || digest !== expected) throw new Error('Artifact fingerprint mismatch');
    return new NextResponse(new Uint8Array(bytes), {headers:{
      'Content-Type':'image/png','Cache-Control':'private, no-store',
      'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"
    }});
  } catch {
    return NextResponse.json({error:'Candidate artifact unavailable or invalid'}, {status:404,headers:{'Cache-Control':'no-store'}});
  }
}
