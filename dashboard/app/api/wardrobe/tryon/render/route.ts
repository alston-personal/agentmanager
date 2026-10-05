import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import {
  DEFAULT_CHARACTER_ID,
  createTryOnJob,
  findAcceptedCachedJob,
  makeOutfitSignature,
  normalizeSelectedLayers,
} from '@/lib/tryon-jobs';

function getAuthenticatedUser(request: NextRequest) {
  const tokens = request.cookies.getAll('auth_token').map((cookie) => cookie.value).filter(Boolean);
  for (const token of tokens) {
    const identity = verifyToken(token);
    if (identity?.username) return identity;
  }
  return null;
}

export async function POST(request: NextRequest) {
  const user = getAuthenticatedUser(request);
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 });

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

    const baseBodyAsset =
      typeof body?.baseBodyAsset === 'string' && body.baseBodyAsset.trim()
        ? body.baseBodyAsset.trim()
        : undefined;

    const signature = makeOutfitSignature({
      characterId,
      selectedLayers,
      baseBodyAsset,
    });
    const cached = findAcceptedCachedJob(signature);
    if (cached) {
      return NextResponse.json({
        success: true,
        cacheHit: true,
        outfitSignature: signature,
        jobId: cached.jobId,
        status: cached.status,
        requestedAt: cached.requestedAt,
        asset: cached.output.asset,
        previewAsset: cached.output.previewAsset,
      }, { status: 200 });
    }

    const job = createTryOnJob({
      characterId,
      selectedLayers,
      baseBodyAsset,
    });

    return NextResponse.json({
      success: true,
      cacheHit: false,
      outfitSignature: job.outfitIr.signature,
      jobId: job.jobId,
      status: job.status,
      requestedAt: job.requestedAt,
    }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create try-on job';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
