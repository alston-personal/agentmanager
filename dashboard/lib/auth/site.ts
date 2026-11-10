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
  const hostname = url.hostname.toLowerCase();
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
