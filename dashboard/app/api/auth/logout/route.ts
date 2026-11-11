import { NextRequest, NextResponse } from 'next/server';
import { authCookieName, resolveAuthSite, safeLocalReturnTo } from '@/lib/auth/site';

export async function GET(request: NextRequest) {
  const resolved = resolveAuthSite(request);
  if (!resolved) return NextResponse.json({ error: 'Unsupported auth site' }, { status: 400 });

  const returnTo = safeLocalReturnTo(new URL(request.url).searchParams.get('returnTo'));
  const response = NextResponse.redirect(new URL(returnTo, resolved.origin));
  // Retire parent-domain legacy credentials, then clear this site's session.
  response.cookies.set({
    name: 'auth_token', value: '', httpOnly: true, secure: true,
    domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 0,
  });
  response.cookies.set({
    name: authCookieName(resolved.site), value: '', httpOnly: true, secure: true,
    path: '/', sameSite: 'lax', maxAge: 0,
  });
  return response;
}
