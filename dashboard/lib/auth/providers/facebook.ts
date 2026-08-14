import { OAuthProviderAdapter, OAuthProfile } from './index';

export const facebookAdapter: OAuthProviderAdapter = {
  getAuthorizeUrl(clientId: string, redirectUri: string, state?: string): string {
    const stateParam = state ? `&state=${state}` : '';
    return `https://www.facebook.com/v18.0/dialog/oauth?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=public_profile${stateParam}`;
  },

  async exchangeCode(clientId: string, clientSecret: string, code: string, redirectUri: string): Promise<string> {
    const tokenUrl = `https://graph.facebook.com/v18.0/oauth/access_token?client_id=${clientId}&client_secret=${clientSecret}&redirect_uri=${encodeURIComponent(redirectUri)}&code=${code}`;
    const res = await fetch(tokenUrl);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error?.message || 'Failed to exchange code for token on Facebook');
    }

    const data = await res.json();
    if (!data.access_token) {
      throw new Error('Facebook OAuth failed, no access token returned');
    }

    return data.access_token;
  },

  async getUserProfile(accessToken: string): Promise<OAuthProfile> {
    const profileUrl = `https://graph.facebook.com/me?fields=id,name,picture&access_token=${accessToken}`;
    const res = await fetch(profileUrl);

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error?.message || 'Failed to fetch user profile from Facebook');
    }

    const data = await res.json();
    // Facebook returns display name in data.name
    return {
      username: data.name || `fb_${data.id}`,
      subject: String(data.id),
      avatarUrl: data.picture?.data?.url,
      provider: 'facebook',
    };
  },
};
