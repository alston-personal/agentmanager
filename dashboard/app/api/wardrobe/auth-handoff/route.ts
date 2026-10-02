import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { createPwaHandoff, completePwaHandoff, readPwaHandoff, consumePwaHandoff } from '@/lib/auth/pwa-handoff';

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
    const record = handoffId ? readPwaHandoff(handoffId) : null;
    if (!record?.authToken || record.status !== 'ready' || !verifyToken(record.authToken)) {
      return NextResponse.json({ ready: false }, { status: 404, headers: { 'cache-control': 'no-store' } });
    }
    const response = NextResponse.json(
      { ready: true, cookieScope: 'host-only', legacyCookieCleared: true },
      { headers: { 'cache-control': 'no-store' } }
    );
    // iOS Home Screen web apps can keep a cookie jar separate from Safari.
    // Set a host-only cookie on studio.milkcat.org and keep the handoff
    // available until the PWA proves /auth/session can read it.
    response.cookies.set({
      name: 'auth_token',
      value: '',
      httpOnly: true,
      secure: true,
      domain: '.milkcat.org',
      path: '/',
      sameSite: 'lax',
      maxAge: 0,
    });
    response.cookies.set({
      name: 'auth_token',
      value: record.authToken,
      httpOnly: true,
      secure: true,
      path: '/',
      sameSite: 'lax',
      maxAge: 86400,
    });
    return response;
  }

  if (action === 'ack') {
    const body = await request.json().catch(() => ({}));
    const handoffId = typeof body?.handoffId === 'string' ? body.handoffId : '';
    const tokens = request.cookies.getAll('auth_token').map((cookie) => cookie.value).filter(Boolean);
    const token = tokens.find((candidate) => candidate === (handoffId ? readPwaHandoff(handoffId)?.authToken : '')) || '';
    const record = handoffId ? readPwaHandoff(handoffId) : null;
    if (!record?.authToken || !token || token !== record.authToken || !verifyToken(token)) {
      return NextResponse.json({ acknowledged: false }, { status: 409, headers: { 'cache-control': 'no-store' } });
    }
    consumePwaHandoff(handoffId);
    return NextResponse.json({ acknowledged: true }, { headers: { 'cache-control': 'no-store' } });
  }

  return NextResponse.json({ error: 'unsupported action' }, { status: 400 });
}

export async function GET(request: NextRequest) {
  const handoff = new URL(request.url).searchParams.get('handoff') || '';
  const token = request.cookies.getAll('auth_token').map((cookie) => cookie.value).find((candidate) => Boolean(verifyToken(candidate))) || '';
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
  const wardrobeUrl = 'https://studio.milkcat.org/personas/mio/wardrobe/?authHandoff=completed';
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <title>登入完成｜澪的衣櫃</title>
  <style>
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f7f4ef;color:#241f1a;display:grid;min-height:100vh;place-items:center}
    main{max-width:420px;padding:32px 24px;text-align:center}
    h1{font-size:28px;margin:0 0 12px}
    p{line-height:1.7;color:#5b5147}
    a{display:block;margin-top:22px;padding:14px 18px;border-radius:14px;background:#241f1a;color:white;text-decoration:none;font-weight:700}
    small{display:block;margin-top:14px;color:#84786d;line-height:1.5}
  </style>
</head>
<body>
  <main>
    <h1>登入完成</h1>
    <p>正在返回「澪的衣櫃」。如果這個登入頁沒有自動關閉，請按下面的按鈕返回。</p>
    <a href="${wardrobeUrl}">返回澪的衣櫃</a>
    <small>如果你是從 iPhone 主畫面的「澪的衣櫃」開啟登入，建議直接切回原本的 App；它會自動完成登入交換。</small>
  </main>
  <script>
    setTimeout(function () {
      try { window.close(); } catch (_) {}
    }, 250);
  </script>
</body>
</html>`;
  return new NextResponse(html, {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' },
  });
}
