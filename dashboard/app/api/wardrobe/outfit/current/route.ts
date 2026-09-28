import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { DEFAULT_CHARACTER_ID, readCurrentOutfit } from '@/lib/tryon-jobs';

function authorized(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) return false;
  const identity = verifyToken(token);
  return Boolean(identity?.username && isMilkcatAdmin(identity));
}

export async function GET(request: NextRequest) {
  if (!authorized(request)) {
    return NextResponse.json({ error: 'Admin authentication required' }, { status: 401 });
  }
  const characterId = request.nextUrl.searchParams.get('characterId')?.trim() || DEFAULT_CHARACTER_ID;
  if (characterId !== DEFAULT_CHARACTER_ID) {
    return NextResponse.json({ error: 'MVP supports Mio only' }, { status: 400 });
  }
  const outfit = readCurrentOutfit(characterId);
  return NextResponse.json(outfit || {
    schema: 'milkcat.outfit-simulator/v3',
    characterId,
    items: [],
    tryOn: null,
  });
}
