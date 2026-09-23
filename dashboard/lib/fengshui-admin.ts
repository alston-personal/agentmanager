import { readFileSync, lstatSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

type Summary = Record<string, unknown>;

/** Oracle-only, private companion to the Fengshui systemd EnvironmentFile. */
function analyticsToken(): string {
  const configured = String(process.env.FENGSHUI_ANALYTICS_TOKEN || '').trim();
  if (configured) return configured;
  const file = join(homedir(), '.config', 'milkcat', 'fengshui-analytics-token');
  try {
    const stat = lstatSync(file);
    const uid = process.getuid?.();
    if (!stat.isFile() || stat.isSymbolicLink() || uid === undefined ||
        stat.uid !== uid || (stat.mode & 0o077) !== 0) {
      throw new Error('fengshui_analytics_token_file_insecure');
    }
    const token = readFileSync(file, 'utf8').trim();
    if (token.length < 32) throw new Error('fengshui_analytics_token_file_invalid');
    return token;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('fengshui_analytics_token_file_')) {
      throw error;
    }
    throw new Error('fengshui_analytics_token_missing');
  }
}

const DEFAULT_BASE = 'http://127.0.0.1:8868/fengshui';

async function fetchSummary(path: string): Promise<Summary> {
  const token = analyticsToken();

  const base = String(process.env.FENGSHUI_INTERNAL_BASE_URL || DEFAULT_BASE).replace(/\/$/, '');
  const response = await fetch(`${base}${path}`, {
    headers: { 'x-analytics-token': token },
    cache: 'no-store',
  });

  if (!response.ok) throw new Error(`fengshui_admin_fetch_failed:${response.status}`);
  return response.json();
}

export async function getFengshuiAdminSummary(days = 30) {
  const safeDays = Math.max(1, Math.min(365, Math.trunc(days || 30)));
  const [analytics, feedback] = await Promise.all([
    fetchSummary(`/api/analytics/summary?days=${safeDays}`),
    fetchSummary(`/api/feedback/summary?days=${safeDays}`),
  ]);
  return { window_days: safeDays, analytics, feedback };
}
