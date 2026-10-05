import { NextRequest, NextResponse } from 'next/server';
import { getProvider } from '@/lib/auth/providers';
import { generateToken } from '@/lib/auth';
import { completePwaHandoff } from '@/lib/auth/pwa-handoff';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');

  const { provider } = await params;
  const lowerProvider = provider.toLowerCase();
  const adapter = getProvider(lowerProvider);

  if (!adapter) {
    return NextResponse.json({ error: `Unsupported auth provider: ${provider}` }, { status: 400 });
  }

  if (!code) {
    return NextResponse.json({ error: 'Code parameter is missing' }, { status: 400 });
  }

  try {
    const providerKey = lowerProvider.toUpperCase();
    const clientId = process.env[`${providerKey}_CLIENT_ID`];
    const clientSecret = process.env[`${providerKey}_CLIENT_SECRET`];
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://studio.milkcat.org';
    const redirectUri = `${siteUrl}/dashboard/api/auth/callback/${lowerProvider}`;

    if (!clientId || !clientSecret) {
      return NextResponse.json({ error: `OAuth credentials not configured for ${provider}` }, { status: 500 });
    }

    // 1. Exchange temporary code for access token
    const accessToken = await adapter.exchangeCode(clientId, clientSecret, code, redirectUri);

    // 2. Fetch user profile
    const profile = await adapter.getUserProfile(accessToken);
    const username = profile.username;

    if (!username) {
      return NextResponse.json({ error: `Failed to retrieve username from ${provider}` }, { status: 400 });
    }

    // 3. Generate our JWT token
    const token = generateToken(username, { provider: profile.provider, subject: profile.subject, avatarUrl: profile.avatarUrl });

    // 4. Resolve the post-login target. For Mio Wardrobe PWA handoff,
    // complete the one-time handoff server-side while the freshly issued JWT
    // is still in memory. This avoids relying on Safari/WebKit committing an
    // auth cookie before a follow-up request reads it.
    const returnToCookie = request.cookies.get('oauth_return_to')?.value;
    const returnTo = returnToCookie ? decodeURIComponent(returnToCookie) : '/';
    const safeReturnTo = returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/';

    let directPwaHandoffCompleted = false;
    try {
      const parsedReturnTo = new URL(safeReturnTo, siteUrl);
      const siteOrigin = new URL(siteUrl).origin;
      const handoffId = parsedReturnTo.origin === siteOrigin
        && parsedReturnTo.pathname === '/dashboard/api/wardrobe/auth-handoff'
        ? parsedReturnTo.searchParams.get('handoff')
        : null;
      if (handoffId && /^[A-Za-z0-9_-]{32,128}$/.test(handoffId)) {
        completePwaHandoff(handoffId, token);
        directPwaHandoffCompleted = true;
      }
    } catch (handoffError) {
      console.error('Direct PWA auth handoff failed:', handoffError);
    }

    const redirectTarget = directPwaHandoffCompleted
      ? '/personas/mio/wardrobe/?authHandoff=completed'
      : safeReturnTo;
    const response = NextResponse.redirect(new URL(redirectTarget, siteUrl));
    
    // Remove the legacy parent-domain cookie so iOS/WebKit cannot keep two
    // same-name auth_token cookies with different scopes.
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
      value: token,
      httpOnly: true,
      secure: true,
      path: '/',
      sameSite: 'lax',
      maxAge: 86400, // 24 hours
    });
    response.cookies.set({ name: 'oauth_return_to', value: '', httpOnly: true, secure: true, domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 0 });
    response.cookies.set({ name: 'oauth_return_to', value: '', httpOnly: true, secure: true, path: '/', sameSite: 'lax', maxAge: 0 });

    return response;
  } catch (error: any) {
    console.error(`OAuth callback error for ${provider}:`, error);
    return NextResponse.json({ error: error.message || 'Authentication failed' }, { status: 500 });
  }
}
