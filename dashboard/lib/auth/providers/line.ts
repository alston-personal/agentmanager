import { OAuthProviderAdapter, OAuthProfile } from './index';

export const lineAdapter: OAuthProviderAdapter = {
  getAuthorizeUrl(clientId: string, redirectUri: string, state?: string): string {
    const stateParam = state ? `&state=${state}` : '';
    // LINE OAuth v2.1 requires response_type=code
    return `https://access.line.me/oauth2/v2.1/authorize?response_type=code&client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=profile${stateParam}`;
  },

  async exchangeCode(clientId: string, clientSecret: string, code: string, redirectUri: string): Promise<string> {
    const params = new URLSearchParams();
    params.append('grant_type', 'authorization_code');
    params.append('code', code);
    params.append('redirect_uri', redirectUri);
    params.append('client_id', clientId);
    params.append('client_secret', clientSecret);

    const res = await fetch('https://api.line.me/oauth2/v2.1/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error_description || 'Failed to exchange code for token on LINE');
    }

    const data = await res.json();
    if (!data.access_token) {
      throw new Error('LINE OAuth failed, no access token returned');
    }

    return data.access_token;
  },

  async getUserProfile(accessToken: string): Promise<OAuthProfile> {
    const res = await fetch('https://api.line.me/v2/profile', {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || 'Failed to fetch user profile from LINE');
    }

    const data = await res.json();
    return {
      username: data.displayName || `line_${data.userId}`,
      subject: String(data.userId),
      avatarUrl: data.pictureUrl,
      provider: 'line',
    };
  },
};
