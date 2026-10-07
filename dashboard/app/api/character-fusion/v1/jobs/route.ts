import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import {
  createCharacterFusionJob,
  launchCharacterFusionWorker,
} from '@/lib/character-fusion-jobs';

function identity(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return null;
  return verifyToken(token);
}

export async function POST(request: NextRequest) {
  const user = identity(request);
  if (!user?.username) {
    return NextResponse.json({ error: 'Login required' }, { status: 401 });
  }

  try {
    const form = await request.formData();
    const person = form.get('person');
    const mainVisual = form.get('mainVisual');
    const preset = String(form.get('preset') || 'water-drop');

    if (!(person instanceof File)) {
      return NextResponse.json({ error: 'person image is required' }, { status: 400 });
    }
    if (mainVisual !== null && !(mainVisual instanceof File)) {
      return NextResponse.json({ error: 'mainVisual must be an image file' }, { status: 400 });
    }

    const job = await createCharacterFusionJob({
      requestedBy: user.username,
      preset,
      person,
      mainVisual: mainVisual instanceof File ? mainVisual : null,
    });
    launchCharacterFusionWorker(job.jobId);

    return NextResponse.json({
      success: true,
      jobId: job.jobId,
      status: job.status,
      requestedAt: job.requestedAt,
    }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create character fusion job';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
