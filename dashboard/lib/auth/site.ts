import type { NextRequest } from 'next/server';

export type AuthSite = 'studio' | 'agentos';

const ORIGINS: Record<AuthSite, string> = {
  studio: 'https://studio.milkcat.org',
  agentos: 'https://agentos.milkcat.org',
};

/**
 * Site is a deployment boundary, not a user-selected redirect host.
 * An optional site= parameter may assert the expected site but cannot
 * override the hostname. Never use a supplied origin or Host in redirects.
 */
export function resolveAuthSite(request: NextRequest): { site: AuthSite; origin: string } | null {
  const url = new URL(request.url);
  // The fixed-origin AgentOS Gateway forwards the trusted virtual Host to
  // Next running on 127.0.0.1:3040/3041. Next may internally construct
  // request.url from its Studio deployment origin; routing must use the
  // incoming virtual Host, NOT the deployment's canonical URL.
  // The Gateway rejects non-AgentOS hosts before forwarding.
  const hostname = (request.headers.get('host') || url.hostname)
    .toLowerCase().replace(/:\\d+$/, '');
  const site: AuthSite | null =
    hostname === 'agentos.milkcat.org' ? 'agentos' :
    hostname === 'studio.milkcat.org' ? 'studio' :
    hostname === 'localhost' || hostname === '127.0.0.1' ? 'studio' : null;
  if (!site) return null;
  const asserted = url.searchParams.get('site');
  if (asserted !== null && asserted !== site) return null;
  return { site, origin: ORIGINS[site] };
}

export function safeLocalReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\') ||
      /[\r\n]/.test(value)) return '/';
  return value;
}
