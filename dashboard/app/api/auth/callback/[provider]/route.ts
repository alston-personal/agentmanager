import { NextRequest, NextResponse } from 'next/server';
import { getProvider } from '@/lib/auth/providers';
import { generateToken } from '@/lib/auth';

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

    // 4. Set HttpOnly cookie and redirect back to root
    const returnToCookie = request.cookies.get('oauth_return_to')?.value;
    const returnTo = returnToCookie ? decodeURIComponent(returnToCookie) : '/';
    const response = NextResponse.redirect(new URL(returnTo.startsWith('/') && !returnTo.startsWith('//') ? returnTo : '/', siteUrl));
    
    response.cookies.set({
      name: 'auth_token',
      value: token,
      httpOnly: true,
      secure: true,
      domain: '.milkcat.org',
      path: '/',
      sameSite: 'lax',
      maxAge: 86400, // 24 hours
    });
    response.cookies.set({ name: 'oauth_return_to', value: '', httpOnly: true, secure: true, domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 0 });

    return response;
  } catch (error: any) {
    console.error(`OAuth callback error for ${provider}:`, error);
    return NextResponse.json({ error: error.message || 'Authentication failed' }, { status: 500 });
  }
}
