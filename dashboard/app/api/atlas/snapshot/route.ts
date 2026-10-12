import { NextRequest, NextResponse } from 'next/server';
import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const headers = { 'Cache-Control': 'private, no-store', 'X-Robots-Tag': 'noindex, nofollow' };
const ledgerPath = path.join(AGENT_DATA_ROOT, 'governance', 'work-items.json');
const safeText = (v: unknown, n = 160) => typeof v === 'string' ? v.slice(0, n) : null;
const safeSource = (v: unknown) =>
  typeof v === 'string' && /^https:\/\/github\.com\/alston-personal\/[a-zA-Z0-9_.-]+\/issues\/[0-9]+$/.test(v) ? v : null;

export async function GET(request: NextRequest) {
  // The shared auth module permits a development fallback; private Atlas must fail closed.
  if (!process.env.JWT_SECRET || process.env.JWT_SECRET === 'your-secret-key-change-in-production') {
    return NextResponse.json({ error: 'atlas_auth_not_configured' }, { status: 503, headers });
  }
  const tokens = request.cookies.getAll('auth_token').map(c => c.value);
  const identity = tokens.map(t => verifyToken(t)).find(x => x?.username);
  if (!identity) return NextResponse.json({ error: 'authentication_required' }, { status: 401, headers });
  if (!isMilkcatAdmin(identity)) return NextResponse.json({ error: 'atlas_access_denied' }, { status: 403, headers });
  try {
    const metadata = statSync(ledgerPath);
    if (!metadata.isFile() || metadata.size > 10_000_000) throw new Error('ledger_not_regular_or_too_large');
    const ledger = JSON.parse(readFileSync(ledgerPath, 'utf8'));
    if (ledger.schema !== 'agentos.work-completion/v1' || !ledger.items || Array.isArray(ledger.items) || typeof ledger.items !== 'object') throw new Error('invalid_ledger_schema');

    const work_items = Object.entries(ledger.items).slice(-200).map(([id, v]) => {
      const item = v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {};
      const verification = item.verification && typeof item.verification === 'object' ? item.verification as Record<string, unknown> : {};
      const terminalVerified = item.status === 'done' && verification.status === 'passed' && Array.isArray(item.evidence) && item.evidence.length > 0;
      const status = terminalVerified ? 'completed'
        : item.status === 'blocked' || item.status === 'waiting_external' ? 'blocked'
        : item.status === 'accepted' ? 'queued' : 'unknown';
      return {
        work_item_id: safeText(item.work_id) || safeText(id),
        title: safeText(item.title),
        status,
        owner_employee_id: safeText(item.owner),
        node_id: null,
        executor_id: null,
        next_action: safeText(item.next_action),
        blocker_code: status === 'blocked' ? 'work_item_blocked' : null,
        last_checkpoint_at: null,
        receipt_url: terminalVerified ? safeSource(item.source) : null,
      };
    });
    return NextResponse.json({
      projects: [],
      edges: [],
      portfolio: {
        schema: 'agentos.mission-control-ledger-view/v0.1',
        observed_at: metadata.mtime.toISOString(),
        work_items,
        supervisor_status: 'unknown',
        node_status: 'unknown',
        completeness: 'ledger_only',
      },
    }, { headers });
  } catch {
    return NextResponse.json({ error: 'atlas_source_unavailable' }, { status: 503, headers });
  }
}
