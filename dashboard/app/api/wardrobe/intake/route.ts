import { NextRequest, NextResponse } from 'next/server';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
import { resolveRetailProduct, writeCanonicalGarment, type IntakeState, type ResolvedProduct } from '@/lib/wardrobe-ingest';

const INTAKE_DIR = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator', 'intake');
const DEFAULT_CHARACTER_ID = 'sunlake-milkcat-ai-001';
const CHARACTER_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;
const MAX_URL_LENGTH = 2048;
const MAX_NOTE_LENGTH = 500;
const MAX_RETRY_BATCH = 8;

type IntakeRecord = {
  schema: 'agentos.wardrobe-link-intake/v2';
  intakeId: string;
  characterId: string;
  submittedAt: string;
  updatedAt: string;
  submittedBy: {
    username: string;
    provider?: string;
    subject?: string;
  };
  source: {
    url: string;
    hostname: string;
  };
  note: string | null;
  state: IntakeState;
  product: ResolvedProduct | null;
  error: string | null;
};

function getAdmin(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  const identity = verifyToken(token);
  if (!identity || !identity.username || !isMilkcatAdmin(identity)) return null;
  return identity;
}

function normalizeSourceUrl(raw: unknown): URL | null {
  if (typeof raw !== 'string') return null;
  const value = raw.trim();
  if (!value || value.length > MAX_URL_LENGTH) return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null;
    if (!parsed.hostname) return null;
    parsed.hash = '';
    return parsed;
  } catch {
    return null;
  }
}

function recordPath(intakeId: string) {
  return path.join(INTAKE_DIR, intakeId + '.json');
}

function writeRecord(record: IntakeRecord) {
  fs.mkdirSync(INTAKE_DIR, { recursive: true, mode: 0o700 });
  const destination = recordPath(record.intakeId);
  const temporary = destination + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(record, null, 2) + '\n', {
    encoding: 'utf8',
    mode: 0o600,
  });
  fs.renameSync(temporary, destination);
}

function safeReadRecords(): IntakeRecord[] {
  try {
    if (!fs.existsSync(INTAKE_DIR)) return [];
    return fs.readdirSync(INTAKE_DIR)
      .filter((name) => name.endsWith('.json'))
      .map((name) => {
        try {
          const parsed = JSON.parse(fs.readFileSync(path.join(INTAKE_DIR, name), 'utf8')) as Partial<IntakeRecord>;
          return {
            schema: 'agentos.wardrobe-link-intake/v2',
            intakeId: String(parsed.intakeId || ''),
            characterId: String(parsed.characterId || ''),
            submittedAt: String(parsed.submittedAt || ''),
            updatedAt: String(parsed.updatedAt || parsed.submittedAt || ''),
            submittedBy: parsed.submittedBy || { username: 'unknown' },
            source: parsed.source || { url: '', hostname: '' },
            note: parsed.note || null,
            state: (parsed.state || 'pending_metadata') as IntakeState,
            product: parsed.product || null,
            error: parsed.error || null,
          } satisfies IntakeRecord;
        } catch {
          return null;
        }
      })
      .filter((item): item is IntakeRecord => Boolean(item?.intakeId))
      .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
  } catch (error) {
    console.error('Failed to read wardrobe intake records:', error);
    return [];
  }
}

async function processRecord(record: IntakeRecord) {
  const sourceUrl = normalizeSourceUrl(record.source.url);
  if (!sourceUrl) {
    record.state = 'needs_review';
    record.error = 'invalid_source_url';
    record.updatedAt = new Date().toISOString();
    writeRecord(record);
    return record;
  }

  record.updatedAt = new Date().toISOString();
  record.state = 'fetching';
  record.error = null;
  writeRecord(record);

  try {
    const product = await resolveRetailProduct(sourceUrl, record.characterId);
    writeCanonicalGarment(
      AGENT_DATA_ROOT,
      record.characterId,
      product,
      sourceUrl.toString(),
      record.intakeId,
      record.note
    );
    record.product = product;
    record.state = 'ready_for_tryon';
    record.updatedAt = new Date().toISOString();
    writeRecord(record);
  } catch (error) {
    record.state = 'needs_review';
    record.error = (error instanceof Error ? error.message : 'metadata_fetch_failed').slice(0, 180);
    record.updatedAt = new Date().toISOString();
    writeRecord(record);
  }
  return record;
}

export async function GET(request: NextRequest) {
  const admin = getAdmin(request);
  if (!admin) return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });

  const characterId = request.nextUrl.searchParams.get('characterId')?.trim() || DEFAULT_CHARACTER_ID;
  if (!CHARACTER_ID_RE.test(characterId)) {
    return NextResponse.json({ error: 'Invalid characterId' }, { status: 400 });
  }

  let records = safeReadRecords().filter((record) => record.characterId === characterId).slice(0, 50);

  // Upgrade legacy intake records automatically on the owner's next wardrobe visit.
  // Keep the batch intentionally small so GET remains responsive.
  const legacyPending = records.filter((record) => record.state === 'pending_metadata').slice(0, 2);
  if (legacyPending.length) {
    for (const record of legacyPending) {
      await processRecord(record);
    }
    records = safeReadRecords().filter((record) => record.characterId === characterId).slice(0, 50);
  }

  return NextResponse.json({
    characterId,
    records,
    autoRetried: legacyPending.length,
  });
}

export async function POST(request: NextRequest) {
  const admin = getAdmin(request);
  if (!admin) return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });

  try {
    const body = await request.json();
    const action = typeof body?.action === 'string' ? body.action : 'ingest';

    if (action === 'retry' || action === 'retry_pending') {
      const characterId =
        typeof body?.characterId === 'string' && body.characterId.trim()
          ? body.characterId.trim()
          : DEFAULT_CHARACTER_ID;
      if (!CHARACTER_ID_RE.test(characterId)) {
        return NextResponse.json({ error: 'Invalid characterId' }, { status: 400 });
      }

      const all = safeReadRecords().filter((record) => record.characterId === characterId);
      const targets = action === 'retry'
        ? all.filter((record) => record.intakeId === body?.intakeId)
        : all.filter((record) => record.state === 'pending_metadata' || record.state === 'needs_review').slice(0, MAX_RETRY_BATCH);

      if (!targets.length) {
        return NextResponse.json({ success: true, retried: 0, records: [] });
      }

      const processed: IntakeRecord[] = [];
      for (const record of targets) {
        processed.push(await processRecord(record));
      }
      return NextResponse.json({
        success: true,
        retried: processed.length,
        ready: processed.filter((record) => record.state === 'ready_for_tryon').length,
        needsReview: processed.filter((record) => record.state === 'needs_review').length,
        records: processed,
      });
    }

    const sourceUrl = normalizeSourceUrl(body?.url);
    if (!sourceUrl) {
      return NextResponse.json({ error: '請貼上有效的 http/https 商品連結' }, { status: 400 });
    }

    const characterId =
      typeof body?.characterId === 'string' && body.characterId.trim()
        ? body.characterId.trim()
        : DEFAULT_CHARACTER_ID;
    if (!CHARACTER_ID_RE.test(characterId)) {
      return NextResponse.json({ error: 'Invalid characterId' }, { status: 400 });
    }

    const note =
      typeof body?.note === 'string' && body.note.trim()
        ? body.note.trim().slice(0, MAX_NOTE_LENGTH)
        : null;

    const existing = safeReadRecords().find(
      (record) => record.characterId === characterId && record.source.url === sourceUrl.toString()
    );
    if (existing && existing.state === 'ready_for_tryon') {
      return NextResponse.json({ success: true, duplicate: true, ingested: true, record: existing });
    }

    const now = new Date().toISOString();
    const safePrefix = characterId === DEFAULT_CHARACTER_ID ? 'mio' : characterId;
    const record: IntakeRecord = existing || {
      schema: 'agentos.wardrobe-link-intake/v2',
      intakeId: safePrefix + '-link-' + now.replace(/[:.]/g, '-') + '-' + randomUUID().slice(0, 8),
      characterId,
      submittedAt: now,
      updatedAt: now,
      submittedBy: {
        username: admin.username,
        provider: admin.provider,
        subject: admin.subject,
      },
      source: {
        url: sourceUrl.toString(),
        hostname: sourceUrl.hostname.toLowerCase(),
      },
      note,
      state: 'pending_metadata',
      product: null,
      error: null,
    };
    if (note) record.note = note;

    const processed = await processRecord(record);
    return NextResponse.json({
      success: true,
      duplicate: Boolean(existing),
      ingested: processed.state === 'ready_for_tryon',
      record: processed,
    }, { status: existing ? 200 : processed.state === 'ready_for_tryon' ? 201 : 202 });
  } catch (error) {
    console.error('Wardrobe intake failed:', error);
    return NextResponse.json({ error: 'Failed to process wardrobe link' }, { status: 500 });
  }
}
