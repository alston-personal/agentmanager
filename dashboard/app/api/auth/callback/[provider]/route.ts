import { NextRequest, NextResponse } from 'next/server';
import { getProvider } from '@/lib/auth/providers';
import { generateToken } from '@/lib/auth';
import { consumeOAuthState } from '@/lib/auth/oauth-state';
import { resolveAuthSite, safeLocalReturnTo } from '@/lib/auth/site';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  const resolved = resolveAuthSite(request);
  if (!resolved) return NextResponse.json({ error: 'Unsupported or mismatched auth site' }, { status: 400 });

  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const { provider } = await params;
  const lowerProvider = provider.toLowerCase();
  const adapter = getProvider(lowerProvider);

  if (!adapter) {
    return NextResponse.json({ error: `Unsupported auth provider: ${provider}` }, { status: 400 });
  }
  if (!code || !state) {
    return NextResponse.json({ error: 'Code or state parameter is missing' }, { status: 400 });
  }

  // Consume once *before* exchanging the code. An unknown or cross-site
  // state must never be allowed to establish a session.
  const record = consumeOAuthState(state);
  if (!record || (record.site || 'studio') !== resolved.site) {
    return NextResponse.json({ error: 'OAuth state invalid, expired, or site mismatch' }, { status: 400 });
  }

  try {
    const key = lowerProvider.toUpperCase();
    const clientId = process.env[`${key}_CLIENT_ID`];
    const clientSecret = process.env[`${key}_CLIENT_SECRET`];
    if (!clientId || !clientSecret) {
      return NextResponse.json({ error: `OAuth credentials not configured for ${provider}` }, { status: 500 });
    }

    const redirectUri = `${resolved.origin}/dashboard/api/auth/callback/${lowerProvider}`;
    const accessToken = await adapter.exchangeCode(clientId, clientSecret, code, redirectUri);
    const profile = await adapter.getUserProfile(accessToken);
    if (!profile.username) {
      return NextResponse.json({ error: `Failed to retrieve username from ${provider}` }, { status: 400 });
    }

    const token = generateToken(profile.username, {
      provider: profile.provider,
      subject: profile.subject,
      avatarUrl: profile.avatarUrl,
    });
    const response = NextResponse.redirect(new URL(safeLocalReturnTo(record.returnTo), resolved.origin));

    // Clear legacy parent-domain token and replace with a host-only session.
    // Studio and AgentOS must not share a browser cookie.
    response.cookies.set({
      name: 'auth_token', value: '', httpOnly: true, secure: true,
      domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 0,
    });
    response.cookies.set({
      name: 'auth_token', value: token, httpOnly: true, secure: true,
      path: '/', sameSite: 'lax', maxAge: 86400,
    });
    response.cookies.set({
      name: 'oauth_return_to', value: '', httpOnly: true, secure: true,
      domain: '.milkcat.org', path: '/', sameSite: 'lax', maxAge: 0,
    });
    return response;
  } catch (error) {
    console.error(`OAuth callback error for ${provider}:`, error);
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 });
  }
}
