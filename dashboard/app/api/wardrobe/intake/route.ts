import { NextRequest, NextResponse } from 'next/server';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const INTAKE_DIR = path.join(
  AGENT_DATA_ROOT,
  'projects',
  'dressup-simulator',
  'intake'
);

const MIO_CHARACTER_ID = 'sunlake-milkcat-ai-001';
const MAX_URL_LENGTH = 2048;
const MAX_NOTE_LENGTH = 500;

type IntakeRecord = {
  schema: 'agentos.wardrobe-link-intake/v1';
  intakeId: string;
  characterId: string;
  submittedAt: string;
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
  state: 'pending_metadata';
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

function safeReadRecords(): IntakeRecord[] {
  try {
    if (!fs.existsSync(INTAKE_DIR)) return [];
    return fs.readdirSync(INTAKE_DIR)
      .filter((name) => name.endsWith('.json'))
      .map((name) => {
        try {
          return JSON.parse(
            fs.readFileSync(path.join(INTAKE_DIR, name), 'utf8')
          ) as IntakeRecord;
        } catch {
          return null;
        }
      })
      .filter((item): item is IntakeRecord => Boolean(item))
      .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt));
  } catch (error) {
    console.error('Failed to read wardrobe intake records:', error);
    return [];
  }
}

export async function GET(request: NextRequest) {
  const admin = getAdmin(request);
  if (!admin) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }

  const records = safeReadRecords()
    .filter((record) => record.characterId === MIO_CHARACTER_ID)
    .slice(0, 50);

  return NextResponse.json({
    characterId: MIO_CHARACTER_ID,
    records,
  });
}

export async function POST(request: NextRequest) {
  const admin = getAdmin(request);
  if (!admin) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }

  try {
    const body = await request.json();
    const sourceUrl = normalizeSourceUrl(body?.url);
    if (!sourceUrl) {
      return NextResponse.json(
        { error: '請貼上有效的 http/https 商品連結' },
        { status: 400 }
      );
    }

    const characterId =
      typeof body?.characterId === 'string' ? body.characterId.trim() : MIO_CHARACTER_ID;
    if (characterId !== MIO_CHARACTER_ID) {
      return NextResponse.json(
        { error: 'This endpoint currently accepts Mio wardrobe intake only' },
        { status: 400 }
      );
    }

    const note =
      typeof body?.note === 'string' && body.note.trim()
        ? body.note.trim().slice(0, MAX_NOTE_LENGTH)
        : null;

    fs.mkdirSync(INTAKE_DIR, { recursive: true, mode: 0o700 });

    const duplicate = safeReadRecords().find(
      (record) =>
        record.characterId === MIO_CHARACTER_ID &&
        record.source.url === sourceUrl.toString() &&
        record.state === 'pending_metadata'
    );

    if (duplicate) {
      return NextResponse.json({
        success: true,
        duplicate: true,
        record: duplicate,
      });
    }

    const now = new Date().toISOString();
    const intakeId = `mio-link-${now.replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`;
    const record: IntakeRecord = {
      schema: 'agentos.wardrobe-link-intake/v1',
      intakeId,
      characterId: MIO_CHARACTER_ID,
      submittedAt: now,
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
    };

    const destination = path.join(INTAKE_DIR, `${intakeId}.json`);
    const temporary = `${destination}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify(record, null, 2) + '\n', {
      encoding: 'utf8',
      mode: 0o600,
    });
    fs.renameSync(temporary, destination);

    return NextResponse.json({ success: true, duplicate: false, record }, { status: 201 });
  } catch (error) {
    console.error('Wardrobe intake failed:', error);
    return NextResponse.json(
      { error: 'Failed to save wardrobe intake link' },
      { status: 500 }
    );
  }
}
