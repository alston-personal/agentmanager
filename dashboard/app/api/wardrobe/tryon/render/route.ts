import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import {
  DEFAULT_CHARACTER_ID,
  createTryOnJob,
  normalizeSelectedLayers,
} from '@/lib/tryon-jobs';

function getAdmin(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  const identity = verifyToken(token);
  if (!identity || !identity.username || !isMilkcatAdmin(identity)) return null;
  return identity;
}

export async function POST(request: NextRequest) {
  const admin = getAdmin(request);
  if (!admin) return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });

  try {
    const body = await request.json();
    const characterId =
      typeof body?.characterId === 'string' && body.characterId.trim()
        ? body.characterId.trim()
        : DEFAULT_CHARACTER_ID;

    if (characterId !== DEFAULT_CHARACTER_ID) {
      return NextResponse.json({ error: 'MVP supports Mio only' }, { status: 400 });
    }
    if (body?.view && body.view !== 'front') {
      return NextResponse.json({ error: 'MVP supports front view only' }, { status: 400 });
    }
    if (body?.pose && body.pose !== 'neutral_standing') {
      return NextResponse.json({ error: 'MVP supports neutral_standing only' }, { status: 400 });
    }

    const selectedLayers = normalizeSelectedLayers(body?.selectedLayers);
    if (!Object.keys(selectedLayers).length) {
      return NextResponse.json({ error: 'Select at least one garment' }, { status: 400 });
    }

    const job = createTryOnJob({
      characterId,
      selectedLayers,
      baseBodyAsset:
        typeof body?.baseBodyAsset === 'string' && body.baseBodyAsset.trim()
          ? body.baseBodyAsset.trim()
          : undefined,
    });

    return NextResponse.json({
      success: true,
      jobId: job.jobId,
      status: job.status,
      requestedAt: job.requestedAt,
    }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create try-on job';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
