import { githubAdapter } from './github';
import { facebookAdapter } from './facebook';
import { lineAdapter } from './line';
import { googleAdapter } from './google';

export interface OAuthProfile {
  username: string;
  subject: string;
  avatarUrl?: string;
  provider: string;
}

export interface OAuthProviderAdapter {
  getAuthorizeUrl(clientId: string, redirectUri: string, state?: string): string;
  exchangeCode(clientId: string, clientSecret: string, code: string, redirectUri: string): Promise<string>;
  getUserProfile(accessToken: string): Promise<OAuthProfile>;
}

export const providers: Record<string, OAuthProviderAdapter> = {
  github: githubAdapter,
  facebook: facebookAdapter,
  line: lineAdapter,
  google: googleAdapter,
};

export function getProvider(name: string): OAuthProviderAdapter | null {
  return providers[name.toLowerCase()] || null;
}
