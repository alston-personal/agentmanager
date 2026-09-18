type Summary = Record<string, unknown>;

const DEFAULT_BASE = 'http://127.0.0.1:8868/fengshui';

async function fetchSummary(path: string): Promise<Summary> {
  const token = String(process.env.FENGSHUI_ANALYTICS_TOKEN || '');
  if (!token) throw new Error('fengshui_analytics_token_missing');

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
