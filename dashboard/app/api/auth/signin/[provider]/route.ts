import { NextRequest, NextResponse } from 'next/server';
import { getProvider } from '@/lib/auth/providers';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  try {
    const { searchParams } = new URL(request.url);
    const { provider } = await params;
    const adapter = getProvider(provider);

    if (!adapter) {
      return NextResponse.json({ error: `Unsupported auth provider: ${provider}` }, { status: 400 });
    }

    const providerKey = provider.toUpperCase();
    const clientId = process.env[`${providerKey}_CLIENT_ID`];
    const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://studio.milkcat.org';
    const redirectUri = `${siteUrl}/dashboard/api/auth/callback/${provider.toLowerCase()}`;

    if (!clientId) {
      return NextResponse.json({ error: `OAuth Client ID not configured for ${provider}` }, { status: 500 });
    }

    // LINE (and some other providers) require a `state` param for CSRF protection
    const state = Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    const authorizeUrl = adapter.getAuthorizeUrl(clientId, redirectUri, state);
    const returnTo = searchParams.get('returnTo') || '/';
    const safeReturnTo = returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/';
    const response = NextResponse.redirect(authorizeUrl);
    response.cookies.set({ name: 'oauth_return_to', value: encodeURIComponent(safeReturnTo), httpOnly: true, secure: true, domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 600 });
    return response;
  } catch (error) {
    console.error('Sign-in redirect error:', error);
    return NextResponse.json({ error: 'Failed to redirect to sign-in' }, { status: 500 });
  }
}
