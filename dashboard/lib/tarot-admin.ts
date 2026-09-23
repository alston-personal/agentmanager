import { readFileSync, lstatSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

type Summary = Record<string, unknown>;

function privateAnalyticsToken(): string {
  const configured = String(process.env.LEOPARDCAT_ANALYTICS_TOKEN || '').trim();
  if (configured) return configured;
  const file = join(homedir(), '.config', 'milkcat', 'leopardcat-analytics-token');
  try {
    const stat = lstatSync(file);
    const uid = process.getuid?.();
    if (!stat.isFile() || stat.isSymbolicLink() || uid === undefined ||
        stat.uid !== uid || (stat.mode & 0o077) !== 0) {
      throw new Error('tarot_analytics_token_file_insecure');
    }
    const token = readFileSync(file, 'utf8').trim();
    if (token.length < 32) throw new Error('tarot_analytics_token_file_invalid');
    return token;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('tarot_analytics_token_file_')) throw error;
    throw new Error('tarot_analytics_not_configured');
  }
}

export async function getTarotAdminSummary(days = 30): Promise<Summary> {
  const safeDays = Math.max(1, Math.min(365, Math.trunc(days || 30)));
  const token = privateAnalyticsToken();
  // Internal Oracle loopback by default. Never fetch this aggregate from the browser.
  const base = String(process.env.LEOPARDCAT_INTERNAL_BASE_URL || 'http://127.0.0.1:8088').replace(/\/$/, '');
  const response = await fetch(base + '/api/v1/analytics/summary?days=' + safeDays, {
    headers: { 'x-analytics-token': token },
    cache: 'no-store',
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error('tarot_analytics_fetch_failed:' + response.status);
  const payload: unknown = await response.json();
  if (!payload || typeof payload !== 'object' || Array.isArray(payload) ||
      typeof (payload as Summary).total_readings !== 'number') {
    throw new Error('tarot_analytics_response_invalid');
  }
  return payload as Summary;
}
