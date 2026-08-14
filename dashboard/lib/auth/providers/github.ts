import { OAuthProviderAdapter, OAuthProfile } from './index';

export const githubAdapter: OAuthProviderAdapter = {
  getAuthorizeUrl(clientId: string, redirectUri: string, state?: string): string {
    const stateParam = state ? `&state=${state}` : '';
    return `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=read:user${stateParam}`;
  },

  async exchangeCode(clientId: string, clientSecret: string, code: string, redirectUri: string): Promise<string> {
    const res = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        code,
        redirect_uri: redirectUri,
      }),
    });

    if (!res.ok) {
      throw new Error('Failed to exchange code for token on GitHub');
    }

    const data = await res.json();
    if (!data.access_token) {
      throw new Error(data.error_description || 'GitHub OAuth failed, no token returned');
    }

    return data.access_token;
  },

  async getUserProfile(accessToken: string): Promise<OAuthProfile> {
    const res = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `token ${accessToken}`,
        'User-Agent': 'agentmanager-dashboard',
      },
    });

    if (!res.ok) {
      throw new Error('Failed to fetch user profile from GitHub');
    }

    const data = await res.json();
    return {
      username: data.login,
      subject: String(data.id),
      avatarUrl: data.avatar_url,
      provider: 'github',
    };
  },
};
