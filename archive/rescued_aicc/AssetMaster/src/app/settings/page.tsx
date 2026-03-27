'use client';

import { useState, useEffect } from 'react';
import { LayoutDashboard, Wallet, Settings as SettingsIcon, Plus, Trash2, Save, Loader2, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { useSettings } from '@/context/SettingsContext';

export default function SettingsPage() {
  const { colorScheme, setColorScheme } = useSettings();
  const [feeRules, setFeeRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // New Rule State
  const [newRule, setNewRule] = useState({
    market: 'US',
    assetType: 'STOCK',
    actionType: 'BUY',
    feeRate: 0,
    taxRate: 0,
    minFee: 0,
    description: '',
  });

  async function fetchFeeRules() {
    try {
      const res = await fetch('/api/settings/fee-rules');
      if (res.ok) {
        const data = await res.json();
        setFeeRules(data);
      }
    } catch (error) {
      console.error('Failed to fetch fee rules', error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchFeeRules();
  }, []);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch('/api/settings/fee-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRule),
      });
      if (res.ok) {
        fetchFeeRules();
        setNewRule({
          market: 'US',
          assetType: 'STOCK',
          actionType: 'BUY',
          feeRate: 0,
          taxRate: 0,
          minFee: 0,
          description: '',
        });
      }
    } catch (error) {
      console.error('Failed to create rule', error);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (id: string) => {
    if (!confirm('Delete this rule?')) return;
    try {
      await fetch(`/api/settings/fee-rules?id=${id}`, { method: 'DELETE' });
      fetchFeeRules();
    } catch (error) {
      console.error('Failed to delete rule', error);
    }
  };

  const handleResetDefaults = async () => {
    if (!confirm('This will restore all default market rules and settings. Continue?')) return;
    setSaving(true);
    try {
      await fetch('/api/settings/init', { method: 'POST' });
      fetchFeeRules();
      // Reload is often better to ensure context is refreshed if settings changed
      window.location.reload();
    } catch (error) {
      console.error('Failed to reset', error);
    } finally {
      setSaving(false);
    }
  };

  const systemRules = feeRules.filter(r => r.isSystem);
  const customRules = feeRules.filter(r => !r.isSystem);

  return (
    <div className="flex min-h-screen">
      <aside className="w-64 border-r border-white/5 bg-black/20 flex flex-col p-6 gap-8 hidden md:flex">
        <Link href="/" className="flex items-center gap-3 px-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20">
            A
          </div>
          <span className="font-bold text-xl tracking-tight">AssetMaster</span>
        </Link>
        <nav className="flex flex-col gap-2">
          <Link href="/"><NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" /></Link>
          <Link href="/ledger"><NavItem icon={<Wallet size={20} />} label="My Ledger" /></Link>
          <NavItem icon={<SettingsIcon size={20} />} label="Settings" active />
        </nav>
      </aside>

      <main className="flex-1 p-6 md:p-10 overflow-y-auto">
        <header className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">System Settings</h1>
          <p className="text-muted-foreground">Customize your experience and automated rules.</p>
        </header>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
          {/* Visual Settings */}
          <div className="glass p-8 rounded-3xl">
            <h2 className="text-xl font-bold text-white mb-6">Visual Preferences</h2>
            <div className="space-y-6">
              <div className="flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/10">
                <div>
                  <h3 className="font-semibold text-white">Color Strategy</h3>
                  <p className="text-xs text-muted-foreground">Choose market-standard color patterns.</p>
                </div>
                <select
                  className="bg-black/40 border border-white/10 rounded-xl px-4 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={colorScheme}
                  onChange={(e) => setColorScheme(e.target.value as any)}
                >
                  <option value="US">US (Green=Up, Red=Down)</option>
                  <option value="TW">TW (Red=Up, Green=Down)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Fee Rules Introduction */}
          <div className="glass p-8 rounded-3xl flex flex-col justify-between">
            <div>
              <h2 className="text-xl font-bold text-white mb-6">Fee & Tax Automation</h2>
              <p className="text-sm text-muted-foreground mb-4 leading-relaxed">
                Rules control automated transaction costs. <strong>Custom</strong> rules override <strong>Standard</strong> ones.
              </p>
              <div className="p-4 bg-blue-500/10 border border-blue-500/20 rounded-2xl mb-4">
                <p className="text-xs text-blue-400">
                  Tip: Market codes include <strong>US</strong>, <strong>TW</strong>, <strong>JPY</strong>, and <strong>CRYPTO</strong>.
                </p>
              </div>
            </div>
            <button
              onClick={handleResetDefaults}
              className="w-full py-3 bg-white/5 border border-white/10 rounded-xl text-xs font-bold text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center gap-2"
            >
              <RefreshCw size={14} />
              Restore Default Market Rules
            </button>
          </div>
        </section>

        {/* Custom Adjustment Rules */}
        <section className="mb-12">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-2 h-8 bg-blue-500 rounded-full" />
            <h2 className="text-2xl font-black text-white">Custom Adjustment Rules</h2>
          </div>

          <div className="glass rounded-3xl overflow-hidden mb-6">
            <div className="p-6 bg-white/5 border-b border-white/5">
              <form onSubmit={handleCreateRule} className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 items-end">
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Market</label>
                  <input className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white uppercase" value={newRule.market} onChange={e => setNewRule({ ...newRule, market: e.target.value })} placeholder="e.g. TW" required />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Asset</label>
                  <select className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" value={newRule.assetType} onChange={e => setNewRule({ ...newRule, assetType: e.target.value })}>
                    <option value="STOCK">Stock</option>
                    <option value="CRYPTO">Crypto</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Action</label>
                  <select className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" value={newRule.actionType} onChange={e => setNewRule({ ...newRule, actionType: e.target.value })}>
                    <option value="BUY">Buy</option>
                    <option value="SELL">Sell</option>
                    <option value="ANY">Any</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Fee (%)</label>
                  <input type="number" step="any" className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" value={newRule.feeRate} onChange={e => setNewRule({ ...newRule, feeRate: parseFloat(e.target.value) })} required />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Tax (%)</label>
                  <input type="number" step="any" className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" value={newRule.taxRate} onChange={e => setNewRule({ ...newRule, taxRate: parseFloat(e.target.value) })} required />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] uppercase font-bold text-muted-foreground">Min Fee</label>
                  <input type="number" step="any" className="w-full bg-black/20 border border-white/10 rounded-lg px-3 py-2 text-sm text-white" value={newRule.minFee} onChange={e => setNewRule({ ...newRule, minFee: parseFloat(e.target.value) })} required />
                </div>
                <button type="submit" disabled={saving} className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg py-2 px-4 text-sm font-bold transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2">
                  {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                  Add Rule
                </button>
              </form>
            </div>
            <RulesTable rules={customRules} onDelete={handleDeleteRule} />
          </div>
        </section>

        {/* Standard Market Rules */}
        <section>
          <div className="flex items-center gap-3 mb-6">
            <div className="w-2 h-8 bg-zinc-600 rounded-full" />
            <h2 className="text-2xl font-black text-white">Standard Market Rules (Read Only)</h2>
          </div>
          <div className="glass rounded-3xl overflow-hidden">
            <RulesTable rules={systemRules} />
          </div>
        </section>
      </main>
    </div>
  );
}

function RulesTable({ rules, onDelete }: { rules: any[], onDelete?: (id: string) => void }) {
  if (rules.length === 0) {
    return <div className="p-10 text-center text-muted-foreground text-sm">No rules in this category.</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="bg-white/5 text-muted-foreground uppercase text-[10px] tracking-widest font-bold">
            <th className="px-6 py-4">Market</th>
            <th className="px-6 py-4">Asset</th>
            <th className="px-6 py-4">Action</th>
            <th className="px-6 py-4">Fee %</th>
            <th className="px-6 py-4">Tax %</th>
            <th className="px-6 py-4">Min Fee</th>
            {onDelete && <th className="px-6 py-4 text-right">Actions</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {rules.map((rule) => (
            <tr key={rule.id} className="hover:bg-white/5 transition-colors">
              <td className="px-6 py-4 font-bold text-white uppercase">{rule.market}</td>
              <td className="px-6 py-4 text-white/70">{rule.assetType}</td>
              <td className="px-6 py-4">
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${rule.actionType === 'BUY' ? 'bg-blue-500/20 text-blue-400' : rule.actionType === 'SELL' ? 'bg-orange-500/20 text-orange-400' : 'bg-white/10 text-white/70'}`}>
                  {rule.actionType}
                </span>
              </td>
              <td className="px-6 py-4 text-white/70">{rule.feeRate}%</td>
              <td className="px-6 py-4 text-white/70">{rule.taxRate}%</td>
              <td className="px-6 py-4 text-white/70">{rule.minFee}</td>
              {onDelete && (
                <td className="px-6 py-4 text-right">
                  <button onClick={() => onDelete(rule.id)} className="p-1.5 hover:bg-rose-500/20 rounded-lg text-rose-400/50 hover:text-rose-400 transition-colors">
                    <Trash2 size={16} />
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NavItem({ icon, label, active = false }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <div className={`
      flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all cursor-pointer
      ${active ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-muted-foreground hover:bg-white/5 hover:text-white'}
    `}>
      {icon}
      {label}
    </div>
  );
}
