import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { getFengshuiAdminSummary } from '@/lib/fengshui-admin';

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card" style={{ padding: '1rem 1.25rem' }}>
      <div style={{ fontSize: '1.75rem', fontWeight: 800 }}>{value}</div>
      <div style={{ color: 'var(--color-text-secondary)', marginTop: '.25rem' }}>{label}</div>
    </div>
  );
}

export default async function AdminUsagePage() {
  const store = await cookies();
  const token = store.get('auth_token')?.value;
  const identity = token ? verifyToken(token) : null;

  if (!identity) {
    redirect('/dashboard/api/auth/signin/google?returnTo=/dashboard/admin/usage');
  }
  if (!isMilkcatAdmin(identity)) {
    return (
      <main style={{ minHeight: '100vh', padding: '3rem 1.25rem' }}>
        <div className="container">
          <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>需要管理者權限</h1>
          <p style={{ marginTop: '.75rem', color: 'var(--color-text-secondary)' }}>
            目前登入身份：{identity.username}。此頁由 AgentOS Auth 的 server-side RBAC 保護。
          </p>
        </div>
      </main>
    );
  }

  let summary: Awaited<ReturnType<typeof getFengshuiAdminSummary>> | null = null;
  let error = '';
  try {
    summary = await getFengshuiAdminSummary(30);
  } catch (err) {
    error = err instanceof Error ? err.message : 'usage_unavailable';
  }

  const analytics = (summary?.analytics || {}) as Record<string, any>;
  const feedback = (summary?.feedback || {}) as Record<string, any>;

  return (
    <main style={{ minHeight: '100vh', padding: '2.5rem 1.25rem' }}>
      <div className="container">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <p style={{ color: 'var(--color-text-muted)', letterSpacing: '.12em', textTransform: 'uppercase' }}>Milkcat World · Admin</p>
            <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 900, marginTop: '.25rem' }}>Usage Dashboard</h1>
            <p style={{ color: 'var(--color-text-secondary)', marginTop: '.5rem' }}>
              登入：{identity.username} · {identity.provider || 'unknown'} · admin
            </p>
          </div>
          <div style={{ display: 'flex', gap: '.5rem' }}>
            <a className="btn btn-primary" href="/world/">回 Milkcat World</a>
            <a className="btn btn-primary" href="/dashboard/api/auth/logout?returnTo=/world/">登出</a>
          </div>
        </div>

        {error ? (
          <div className="card" style={{ marginTop: '2rem', padding: '1rem 1.25rem' }}>
            <strong>宅向統計目前無法讀取</strong>
            <div style={{ color: 'var(--color-text-secondary)', marginTop: '.35rem' }}>{error}</div>
          </div>
        ) : (
          <>
            <section style={{ marginTop: '2rem' }}>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginBottom: '1rem' }}>宅向風水 · 最近 30 天</h2>
              <div className="grid grid-cols-4">
                <Stat label="事件總數" value={analytics.total_events ?? 0} />
                <Stat label="錯誤回報" value={feedback.total ?? 0} />
                <Stat label="統計天數" value={analytics.window_days ?? 30} />
                <Stat label="身份模式" value="匿名優先" />
              </div>
            </section>

            <section className="grid grid-cols-2" style={{ marginTop: '1.5rem', gap: '1rem' }}>
              <div className="card" style={{ padding: '1.25rem' }}>
                <h3 style={{ fontWeight: 800, marginBottom: '.75rem' }}>功能使用</h3>
                <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: 'var(--color-text-secondary)' }}>
                  {JSON.stringify(analytics.by_event || {}, null, 2)}
                </pre>
              </div>
              <div className="card" style={{ padding: '1.25rem' }}>
                <h3 style={{ fontWeight: 800, marginBottom: '.75rem' }}>錯誤回報類型</h3>
                <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', color: 'var(--color-text-secondary)' }}>
                  {JSON.stringify(feedback.by_category || {}, null, 2)}
                </pre>
              </div>
            </section>

            <section className="card" style={{ marginTop: '1.5rem', padding: '1.25rem' }}>
              <h3 style={{ fontWeight: 800, marginBottom: '.75rem' }}>隱私狀態</h3>
              <p style={{ color: 'var(--color-text-secondary)' }}>
                目前宅向 analytics 不保存 IP、User-Agent、referrer URL、cookie ID 或永久 visitor ID。
                登入後才會逐步加入可信的 user-level 使用統計。
              </p>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
