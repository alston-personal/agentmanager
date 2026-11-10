import { NextRequest, NextResponse } from 'next/server';
import { getProvider } from '@/lib/auth/providers';
import { createOAuthState } from '@/lib/auth/oauth-state';
import { resolveAuthSite, safeLocalReturnTo } from '@/lib/auth/site';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ provider: string }> }
) {
  try {
    const resolved = resolveAuthSite(request);
    if (!resolved) return NextResponse.json({ error: 'Unsupported or mismatched auth site' }, { status: 400 });

    const { searchParams } = new URL(request.url);
    const { provider } = await params;
    const lowerProvider = provider.toLowerCase();
    const adapter = getProvider(lowerProvider);
    if (!adapter) {
      return NextResponse.json({ error: `Unsupported auth provider: ${provider}` }, { status: 400 });
    }

    const clientId = process.env[`${lowerProvider.toUpperCase()}_CLIENT_ID`];
    if (!clientId) {
      return NextResponse.json({ error: `OAuth Client ID not configured for ${provider}` }, { status: 500 });
    }

    const redirectUri = `${resolved.origin}/dashboard/api/auth/callback/${lowerProvider}`;
    const safeReturnTo = safeLocalReturnTo(searchParams.get('returnTo'));
    const oauthState = createOAuthState(safeReturnTo, resolved.site);
    const authorizeUrl = adapter.getAuthorizeUrl(clientId, redirectUri, oauthState.state);
    return NextResponse.redirect(authorizeUrl);
  } catch (error) {
    console.error('Sign-in redirect error:', error);
    return NextResponse.json({ error: 'Failed to redirect to sign-in' }, { status: 500 });
  }
}
