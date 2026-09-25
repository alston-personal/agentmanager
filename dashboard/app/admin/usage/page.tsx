import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { getFengshuiAdminSummary } from '@/lib/fengshui-admin';
import { getTarotAdminSummary } from '@/lib/tarot-admin';

type Counts = Record<string, number>;
function countMap(value: unknown): Counts {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter(([, n]) => typeof n === 'number' && Number.isFinite(n))) as Counts;
}
function quantity(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function spreadDrawModeMap(value: unknown): Record<string, Counts> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const result: Record<string, Counts> = {};
  for (const [spread, modes] of Object.entries(value)) {
    result[spread] = countMap(modes);
  }
  return result;
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="card" style={{ padding: '1.2rem', minWidth: 0 }}>
      <div style={{ color: 'var(--color-text-secondary)', fontSize: '.9rem' }}>{label}</div>
      <div style={{ fontSize: 'clamp(1.5rem, 3vw, 2rem)', fontWeight: 800, marginTop: '.35rem' }}>{value}</div>
      <p style={{ color: 'var(--color-text-muted)', fontSize: '.8rem', marginTop: '.2rem' }}>{detail}</p>
    </div>
  );
}
function SpreadDrawModeTable({ data }: { data: Record<string, Counts> }) {
  const rows = Object.entries(data)
    .map(([spread, modes]) => ({
      spread,
      manual: quantity(modes.manual),
      auto: quantity(modes.auto),
      unknown: quantity(modes.unknown),
    }))
    .map((row) => ({ ...row, total: row.manual + row.auto + row.unknown }))
    .sort((a, b) => b.total - a.total || a.spread.localeCompare(b.spread));

  return (
    <div className="card" style={{ padding: '1.2rem', overflowX: 'auto' }}>
      <h3 style={{ fontWeight: 750 }}>各牌陣：手動選牌 vs 自動抽牌</h3>
      <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', margin: '.35rem 0 1rem' }}>
        同一個牌陣分開計算選牌方式；可用來觀察哪些牌陣更偏好自己選牌。
      </p>
      {rows.length === 0 ? <p style={{ color: 'var(--color-text-secondary)' }}>目前還沒有可比較的占卜紀錄</p> :
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 520 }}>
          <thead><tr style={{ textAlign: 'left', color: 'var(--color-text-secondary)', fontSize: '.82rem' }}>
            <th style={{ padding: '.45rem' }}>牌陣</th>
            <th style={{ padding: '.45rem', textAlign: 'right' }}>手動選牌</th>
            <th style={{ padding: '.45rem', textAlign: 'right' }}>自動抽牌</th>
            <th style={{ padding: '.45rem', textAlign: 'right' }}>其他／舊紀錄</th>
            <th style={{ padding: '.45rem', textAlign: 'right' }}>合計</th>
          </tr></thead>
          <tbody>
            {rows.map((row) => <tr key={row.spread} style={{ borderTop: '1px solid rgba(148,163,184,.14)' }}>
              <td style={{ padding: '.6rem .45rem' }}>{SPREAD_LABELS[row.spread] || row.spread}</td>
              <td style={{ padding: '.6rem .45rem', textAlign: 'right' }}><strong>{row.manual.toLocaleString('zh-TW')}</strong></td>
              <td style={{ padding: '.6rem .45rem', textAlign: 'right' }}><strong>{row.auto.toLocaleString('zh-TW')}</strong></td>
              <td style={{ padding: '.6rem .45rem', textAlign: 'right', color: 'var(--color-text-muted)' }}>{row.unknown.toLocaleString('zh-TW')}</td>
              <td style={{ padding: '.6rem .45rem', textAlign: 'right' }}>{row.total.toLocaleString('zh-TW')}</td>
            </tr>)}
          </tbody>
        </table>}
    </div>
  );
}

function Breakdown({ title, data, labels }: { title: string; data: Counts; labels: Record<string, string> }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, value]) => value));
  return (
    <div className="card" style={{ padding: '1.2rem' }}>
      <h3 style={{ fontWeight: 750, marginBottom: '.8rem' }}>{title}</h3>
      {rows.length === 0 ? <p style={{ color: 'var(--color-text-secondary)' }}>這段期間尚無此類事件紀錄</p> : rows.map(([key, value]) => (
        <div key={key} style={{ marginBottom: '.85rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', fontSize: '.9rem' }}>
            <span>{labels[key] || key.replaceAll('_', ' ')}</span><strong>{value.toLocaleString('zh-TW')} 次</strong>
          </div>
          <div style={{ background: 'rgba(148,163,184,.15)', height: 7, borderRadius: 5, marginTop: '.35rem', overflow: 'hidden' }}>
            <div style={{ width: (value / max * 100) + '%', height: '100%', borderRadius: 5, background: '#818cf8' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

const EVENT_LABELS: Record<string, string> = {
  page_view: '開啟宅向頁面', property_selected: '選擇房屋', listing_import_started: '開始匯入房源',
  listing_import_succeeded: '房源匯入成功', listing_import_failed: '房源匯入失敗',
  image_uploaded: '上傳圖片', workspace_opened: '開啟分析工作區', view_3d_opened: '開啟 3D 檢視',
};
const FEEDBACK_LABELS: Record<string, string> = {
  north_missing: '找不到北向', north_incorrect: '北向判斷錯誤', other: '其他問題',
};
const SOURCE_LABELS: Record<string, string> = {
  direct: '直接進入', threads: 'Threads', line: 'LINE', share: '分享連結', search: '搜尋', other: '其他／未識別',
};
const CATEGORY_LABELS: Record<string, string> = {
  love_relationship: '感情與關係', career_study: '工作與學業', money: '財務', decision: '選擇與決策',
  self_growth: '自我成長', general: '一般指引', other: '其他',
};
const SPREAD_LABELS: Record<string, string> = {
  single: '單張指引', clarifier: '補充牌', three_card: '時間流三牌',
  situation_advice: '現況・阻礙・建議', decision: '選擇分析',
  relationship: '關係五牌', career: '職涯五牌', path: '道路五牌', celtic_cross: '凱爾特十字',
};

export default async function AdminUsagePage({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const store = await cookies();
  const token = store.get('auth_token')?.value;
  const identity = token ? verifyToken(token) : null;
  if (!identity) redirect('/api/auth/signin/google?returnTo=/dashboard/admin/usage');
  if (!isMilkcatAdmin(identity)) {
    return <main style={{ padding: '3rem 1.25rem' }} className="container"><h1>需要管理者權限</h1><p>目前登入身份：{identity.username}。</p></main>;
  }
  const requested = Number((await searchParams).days || 30);
  const days = [7, 30, 90].includes(requested) ? requested : 30;
  const [fengshuiResult, tarotResult] = await Promise.allSettled([getFengshuiAdminSummary(days), getTarotAdminSummary(days)]);
  const fengshui = fengshuiResult.status === 'fulfilled' ? fengshuiResult.value : null;
  const tarot = tarotResult.status === 'fulfilled' ? tarotResult.value : null;
  const fengError = fengshuiResult.status === 'rejected' ? '宅向資料目前無法讀取，請檢查內部統計連線。' : '';
  const tarotError = tarotResult.status === 'rejected' ? '石虎塔羅統計尚未完成連線或目前無法讀取；不代表占卜次數為零。' : '';
  const fengAnalytics = fengshui?.analytics as Record<string, unknown> | undefined;
  const fengFeedback = fengshui?.feedback as Record<string, unknown> | undefined;
  const events = countMap(fengAnalytics?.by_event);
  const feedback = countMap(fengFeedback?.by_category);
  const byDate = countMap(fengAnalytics?.by_date);
  const dateRows = Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b)).slice(-14);
  const dateMax = Math.max(1, ...dateRows.map(([, n]) => n));
  const tarotDrawModes = countMap(tarot?.by_draw_mode);
  const tarotSpreadDrawModes = spreadDrawModeMap(tarot?.by_spread_draw_mode);
  return (
    <main style={{ minHeight: '100vh', padding: '2.5rem 1rem 4rem' }}>
      <div className="container" style={{ maxWidth: 1200 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
          <div><p style={{ color: 'var(--color-text-muted)', fontSize: '.8rem', letterSpacing: '.1em' }}>MILKCAT WORLD · ADMIN</p>
            <h1 style={{ fontSize: 'clamp(1.6rem, 4vw, 2.2rem)', fontWeight: 800 }}>服務使用概況</h1>
            <p style={{ color: 'var(--color-text-secondary)' }}>管理者：{identity.username} · {identity.provider || 'unknown'}</p>
          </div>
          <a className="btn btn-secondary" href="/world/">返回 Milkcat World</a>
        </div>
        <nav aria-label="統計期間" style={{ display: 'flex', gap: '.6rem', marginTop: '1.8rem', flexWrap: 'wrap' }}>
          {[7, 30, 90].map((d) => <a key={d} className="btn btn-secondary" aria-current={days === d ? 'page' : undefined}
            style={{ border: days === d ? '1px solid #818cf8' : '1px solid rgba(255,255,255,.1)' }}
            href={'/dashboard/admin/usage?days=' + d}>最近 {d} 天</a>)}
        </nav>

        <section aria-labelledby="fengshui-heading" style={{ marginTop: '2rem' }}>
          <h2 id="fengshui-heading" style={{ fontSize: '1.45rem', fontWeight: 800 }}>宅向風水</h2>
          <p style={{ color: 'var(--color-text-secondary)', margin: '.4rem 0 1.2rem' }}>以下是功能事件的發生次數，不是使用者人數，也不是同一批使用者的轉換漏斗。</p>
          {fengError ? <div className="card">{fengError}</div> : <>
            <div className="grid grid-cols-4">
              <Metric label="頁面開啟" value={quantity(events.page_view).toLocaleString('zh-TW')} detail="頁面瀏覽事件；非獨立訪客" />
              <Metric label="開啟分析工作區" value={quantity(events.workspace_opened).toLocaleString('zh-TW')} detail="工作區開啟事件" />
              <Metric label="房源匯入成功" value={quantity(events.listing_import_succeeded).toLocaleString('zh-TW')} detail="系統回報的成功事件" />
              <Metric label="房源匯入失敗" value={quantity(events.listing_import_failed).toLocaleString('zh-TW')} detail="需要檢查的失敗事件" />
            </div>
            <div className="card" style={{ marginTop: '1rem', padding: '1rem 1.2rem' }}>
              <h3 style={{ fontWeight: 750 }}>需要注意的問題</h3>
              <p style={{ marginTop: '.5rem' }}>匯入失敗：<strong>{quantity(events.listing_import_failed)} 次</strong>；北向判斷錯誤回報：<strong>{quantity(feedback.north_incorrect)} 筆</strong>。
                {' '}目前僅記錄事件，不提供失敗原因、影響人數或同次匯入的關聯，因此暫不顯示成功率／轉換率。</p>
              <p style={{ marginTop: '.4rem', color: 'var(--color-text-secondary)', fontSize: '.85rem' }}>資料完整性提示：開始匯入 {quantity(events.listing_import_started)} 次；成功與失敗事件合計 {quantity(events.listing_import_succeeded) + quantity(events.listing_import_failed)} 次。這些事件不一定能一一配對，不能推算完成率。</p>
            </div>
            <div className="grid grid-cols-2" style={{ marginTop: '1rem' }}>
              <Breakdown title="功能使用次數" data={events} labels={EVENT_LABELS} />
              <Breakdown title="錯誤回報類型" data={feedback} labels={FEEDBACK_LABELS} />
            </div>
            <div className="card" style={{ marginTop: '1rem' }}>
              <h3 style={{ fontWeight: 750 }}>近期事件趨勢（最近有紀錄的 14 天）</h3>
              <p style={{ color: 'var(--color-text-secondary)', fontSize: '.85rem', marginBottom: '.9rem' }}>每日事件總次數；沒有紀錄的日期不會列出。</p>
              {dateRows.length === 0 ? <p>沒有可用的每日事件資料</p> :
                <div style={{ display: 'flex', alignItems: 'end', gap: '.4rem', minHeight: 105, overflowX: 'auto' }}>
                  {dateRows.map(([date, n]) => <div key={date} title={date + '：' + n + ' 次事件'} style={{ flex: 1, minWidth: 25, textAlign: 'center' }}>
                    <div style={{ height: 72, display: 'flex', alignItems: 'end', justifyContent: 'center' }}>
                      <div style={{ width: '65%', height: Math.max(3, n / dateMax * 72) + 'px', background: '#818cf8', borderRadius: '4px 4px 0 0' }} />
                    </div><div style={{ fontSize: '.7rem', color: 'var(--color-text-secondary)' }}>{date.slice(5)}</div>
                  </div>)}
                </div>}
            </div>
            <p style={{ color: 'var(--color-text-muted)', fontSize: '.85rem', marginTop: '.8rem' }}>全部紀錄共 {quantity(fengAnalytics?.total_events).toLocaleString('zh-TW')} 次事件、{quantity(fengFeedback?.total)} 筆錯誤回報；兩者計數單位不同，不相加為使用人數。</p>
          </>}
        </section>

        <section aria-labelledby="tarot-heading" style={{ marginTop: '2.5rem' }}>
          <h2 id="tarot-heading" style={{ fontSize: '1.45rem', fontWeight: 800 }}>石虎塔羅 · 占卜統計</h2>
          <p style={{ color: 'var(--color-text-secondary)', margin: '.4rem 0 1.2rem' }}>每筆成功記錄的占卜為 1 次；不等於獨立占卜者，也不包含純瀏覽牌廊。</p>
          {tarotError ? <div className="card" role="status" style={{ padding: '1.2rem' }}>
            <strong>尚無法讀取占卜統計</strong><p style={{ marginTop: '.35rem', color: 'var(--color-text-secondary)' }}>{tarotError}</p>
          </div> : <>
            <div className="grid grid-cols-4">
              <Metric label="已記錄占卜" value={quantity(tarot?.total_readings).toLocaleString('zh-TW')} detail="占卜紀錄次數，不是人數" />
              <Metric label="手動選牌" value={quantity(tarotDrawModes.manual).toLocaleString('zh-TW')} detail="使用者自行選擇牌背位置" />
              <Metric label="自動抽牌" value={quantity(tarotDrawModes.auto).toLocaleString('zh-TW')} detail="由系統自動完成抽牌" />
              <Metric label="來自 Threads" value={quantity(countMap(tarot?.by_source).threads).toLocaleString('zh-TW')} detail="來源標記為 Threads 的占卜" />
            </div>
            <div style={{ marginTop: '1rem' }}>
              <SpreadDrawModeTable data={tarotSpreadDrawModes} />
            </div>
            <div className="grid grid-cols-2" style={{ marginTop: '1rem' }}>
              <Breakdown title="占卜從哪裡進來" data={countMap(tarot?.by_source)} labels={SOURCE_LABELS} />
              <Breakdown title="大家問什麼類型的問題" data={countMap(tarot?.by_category)} labels={CATEGORY_LABELS} />
              <Breakdown title="使用的牌陣（總次數）" data={countMap(tarot?.by_spread)} labels={SPREAD_LABELS} />
              <Breakdown title="選牌方式（總次數）" data={tarotDrawModes} labels={{ manual: '手動選牌', auto: '自動抽牌', unknown: '其他／舊紀錄' }} />
              <Breakdown title="使用的牌組" data={countMap(tarot?.by_deck)} labels={{ leopardcat: '石虎塔羅' }} />
            </div>
            <p style={{ color: 'var(--color-text-muted)', fontSize: '.85rem', marginTop: '.8rem' }}>只呈現匿名彙總；不顯示原始提問、占卜回答、帳號或訪客識別資訊。</p>
          </>}
        </section>
        <p className="card" style={{ marginTop: '2.5rem', color: 'var(--color-text-secondary)', fontSize: '.9rem' }}>
          <strong>數據怎麼看：</strong>宅向是動作事件，石虎塔羅是占卜紀錄；這兩種數字不能相加當作「總使用人數」。
          目前不收集可供去重的永久訪客識別，也不應由原始事件硬算獨立訪客或轉換率。
        </p>
      </div>
    </main>
  );
}
