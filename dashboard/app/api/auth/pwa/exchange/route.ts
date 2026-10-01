import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { consumePwaHandoff } from '@/lib/auth/pwa-handoff';

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const handoffId = typeof body?.handoffId === 'string' ? body.handoffId : '';
  const record = handoffId ? consumePwaHandoff(handoffId) : null;
  if (!record?.authToken || !verifyToken(record.authToken)) {
    return NextResponse.json({ ready: false }, { status: 404, headers: { 'cache-control': 'no-store' } });
  }

  const response = NextResponse.json({ ready: true }, { headers: { 'cache-control': 'no-store' } });
  response.cookies.set({
    name: 'auth_token',
    value: record.authToken,
    httpOnly: true,
    secure: true,
    domain: '.milkcat.org',
    path: '/',
    sameSite: 'lax',
    maxAge: 86400,
  });
  return response;
}
