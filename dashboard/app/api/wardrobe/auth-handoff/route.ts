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

    // The exchange runs inside the Home Screen app's cookie jar. Clear the
    // legacy parent-domain cookie and set only a host-scoped auth token here.
    // Keep the handoff until the PWA proves /auth/session can read the token.
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
    const record = handoffId ? readPwaHandoff(handoffId) : null;
    const tokens = request.cookies.getAll('auth_token').map((cookie) => cookie.value).filter(Boolean);
    const token = tokens.find((candidate) => candidate === record?.authToken) || '';

    if (!record?.authToken || !token || !verifyToken(token)) {
      return NextResponse.json({ acknowledged: false }, { status: 409, headers: { 'cache-control': 'no-store' } });
    }

    consumePwaHandoff(handoffId);
    return NextResponse.json({ acknowledged: true }, { headers: { 'cache-control': 'no-store' } });
  }

  return NextResponse.json({ error: 'unsupported action' }, { status: 400 });
}

export async function GET(request: NextRequest) {
  const handoff = new URL(request.url).searchParams.get('handoff') || '';
  const token = request.cookies
    .getAll('auth_token')
    .map((cookie) => cookie.value)
    .find((candidate) => Boolean(verifyToken(candidate))) || '';

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

  const safeHandoff = JSON.stringify(handoff);
  const html = `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>登入完成</title>
<style>
  body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;padding:calc(32px + env(safe-area-inset-top)) 24px 32px;background:#08111f;color:#eef6ff}
  main{max-width:560px;margin:0 auto}
  h1{font-size:24px;margin:0 0 12px}
  p{color:#b9c6d8;line-height:1.6}
  button{width:100%;margin-top:18px;padding:14px 16px;border:0;border-radius:14px;font-size:17px;font-weight:800;background:linear-gradient(90deg,#b8a8ff,#7cd9ef);color:#07111e}
</style>
</head>
<body>
<main>
  <h1>登入完成</h1>
  <p>正在回到主畫面的「澪的衣櫃」App，並接回剛才的試穿。</p>
  <button type="button" id="return">回到澪的衣櫃</button>
</main>
<script>
(() => {
  const payload = { type: 'milkcat-pwa-auth-ready', handoffId: ${safeHandoff} };
  try {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage(payload, window.location.origin);
    }
  } catch {}
  const close = () => {
    try { window.close(); } catch {}
  };
  document.getElementById('return')?.addEventListener('click', close);
  setTimeout(close, 350);
})();
</script>
</body>
</html>`;

  return new NextResponse(html, {
    status: 200,
    headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' },
  });
}
