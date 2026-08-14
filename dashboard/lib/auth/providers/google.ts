import { OAuthProviderAdapter, OAuthProfile } from './index';

export const googleAdapter: OAuthProviderAdapter = {
  getAuthorizeUrl(clientId: string, redirectUri: string, state?: string): string {
    const params = new URLSearchParams({ client_id: clientId, redirect_uri: redirectUri, response_type: 'code', scope: 'openid email profile', access_type: 'online' });
    if (state) params.set('state', state);
    return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  },

  async exchangeCode(clientId: string, clientSecret: string, code: string, redirectUri: string): Promise<string> {
    const res = await fetch('https://oauth2.googleapis.com/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ client_id: clientId, client_secret: clientSecret, code, redirect_uri: redirectUri, grant_type: 'authorization_code' }).toString() });
    const data = await res.json();
    if (!res.ok || !data.access_token) throw new Error(data.error_description || 'Google OAuth failed, no access token returned');
    return data.access_token;
  },

  async getUserProfile(accessToken: string): Promise<OAuthProfile> {
    const res = await fetch('https://openidconnect.googleapis.com/v1/userinfo', { headers: { Authorization: `Bearer ${accessToken}` } });
    const data = await res.json();
    if (!res.ok || !data.sub) throw new Error(data.error_description || 'Failed to fetch user profile from Google');
    return { username: data.email || `google_${data.sub}`, subject: String(data.sub), avatarUrl: data.picture, provider: 'google' };
  },
};
