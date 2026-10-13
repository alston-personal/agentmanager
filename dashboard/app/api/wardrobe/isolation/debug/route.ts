import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const ROOT = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator', 'isolation_candidates');
const ID = /^[A-Za-z0-9._-]{1,160}$/;
const SHA = /^[a-f0-9]{64}$/;
const MAX_GARMENTS = 250;
const MAX_VERSIONS = 20;
function hasVerifiedFile(dir: string, filename: string, expected: unknown): boolean {
  if (typeof expected !== 'string' || !SHA.test(expected)) return false;
  try {
    const file = path.join(dir, filename);
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 15_000_000) return false;
    const bytes = fs.readFileSync(file);
    return crypto.createHash('sha256').update(bytes).digest('hex') === expected;
  } catch { return false; }
}

function isAdmin(request: NextRequest): boolean {
  return request.cookies.getAll('auth_token').some(({value}) => {
    const identity = verifyToken(value);
    return Boolean(identity?.username && isMilkcatAdmin(identity));
  });
}
function subdirs(dir: string): string[] {
  try {
    if (fs.lstatSync(dir).isSymbolicLink()) return [];
    return fs.readdirSync(dir, {withFileTypes:true})
      .filter(e => e.isDirectory() && !e.isSymbolicLink())
      .map(e => e.name);
  } catch { return []; }
}
export async function GET(request: NextRequest) {
  if (!isAdmin(request)) {
    return NextResponse.json({error:'Admin authentication required'}, {status:401,headers:{'Cache-Control':'no-store'}});
  }
  const garments = subdirs(ROOT).filter(id => ID.test(id)).sort().slice(0,MAX_GARMENTS);
  const records: Array<Record<string,unknown>> = [];
  for (const garmentId of garments) {
    const revisions = subdirs(path.join(ROOT,garmentId)).filter(x => SHA.test(x)).sort().slice(0,MAX_VERSIONS);
    for (const sourceSha of revisions) {
      try {
        const file = path.join(ROOT,garmentId,sourceSha,'candidate-receipt.json');
        const stat = fs.lstatSync(file);
        if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 200_000) continue;
        const receipt = JSON.parse(fs.readFileSync(file,'utf8'));
        if (receipt.garmentId !== garmentId || receipt.sourceAssetSha256 !== sourceSha) continue;
        records.push({
          garmentId,sourceSha,state:receipt.state,extractorOutcome:receipt.extractorOutcome,
          approved:receipt.approved === true,
          hasCandidate:hasVerifiedFile(path.join(ROOT,garmentId,sourceSha),'garment.png',receipt.isolatedAssetSha256),
          hasMask:hasVerifiedFile(path.join(ROOT,garmentId,sourceSha),'garment.mask.png',receipt.maskSha256),
          reviewState:receipt.review?.state || 'unknown',
        });
      } catch { /* Corrupt candidates are not advertised. */ }
    }
  }
  return NextResponse.json({schema:'agentos.wardrobe-debug-manifest/v1',records},
    {headers:{'Cache-Control':'private, no-store'}});
}
