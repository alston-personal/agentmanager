import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { createPwaHandoff, completePwaHandoff, consumePwaHandoff } from '@/lib/auth/pwa-handoff';

export async function POST(request: NextRequest) {
  const action = new URL(request.url).searchParams.get('action') || 'start';

  if (action === 'start') {
    const record = createPwaHandoff();
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://studio.milkcat.org';
    const returnTo = '/dashboard/api/wardrobe/auth-handoff?handoff=' + encodeURIComponent(record.id);
    const signInUrl = siteUrl + '/dashboard/api/auth/signin/google?returnTo=' + encodeURIComponent(returnTo);
    return NextResponse.json({ handoffId: record.id, expiresAt: record.expiresAt, signInUrl }, { headers: { 'cache-control': 'no-store' } });
  }

  if (action === 'exchange') {
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

  return NextResponse.json({ error: 'unsupported action' }, { status: 400 });
}

export async function GET(request: NextRequest) {
  const handoff = new URL(request.url).searchParams.get('handoff') || '';
  const token = request.cookies.get('auth_token')?.value || '';
  if (!handoff || !token || !verifyToken(token)) {
    return new NextResponse('Login not completed. Return to Mio wardrobe and retry.', {
      status: 401,
      headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  try {
    completePwaHandoff(handoff, token);
  } catch {
    return new NextResponse('Login handoff expired. Return to Mio wardrobe and retry.', {
      status: 410,
      headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  return new NextResponse('登入完成。請回到主畫面的「澪的衣櫃」App。', {
    status: 200,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });
}
