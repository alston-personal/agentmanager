'use client';

import { useEffect, useState } from 'react';
import { PriceCard } from '@/components/PriceCard';
import { LayoutDashboard, Wallet, PieChart, History, RefreshCw, TrendingUp, TrendingDown, Settings as SettingsIcon } from 'lucide-react';
import { PortfolioPieChart } from '@/components/PortfolioPieChart';
import { formatCurrency, getMarketFromSymbol } from '@/lib/utils';
import Link from 'next/link';
import { useSettings } from '@/context/SettingsContext';
import { BankAccounts } from '@/components/BankAccounts';

const TRACKED_SYMBOLS = ['AAPL', '2330.TW', '9984.T', 'BTC/USDT', 'ETH/USDT'];

export default function Home() {
  const { colorScheme } = useSettings();
  const [quotes, setQuotes] = useState<any>({});
  // ... skipping to render part, wait, I'll do a larger block to be safe
  const [portfolio, setPortfolio] = useState<any[]>([]);
  const [bankAccounts, setBankAccounts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterType, setFilterType] = useState('ALL');
  const [selectedSymbol, setSelectedSymbol] = useState('ALL');

  async function fetchData() {
    try {
      setRefreshing(true);
      const [priceRes, portfolioRes, bankAccountsRes] = await Promise.all([
        fetch(`/api/prices?symbols=${TRACKED_SYMBOLS.join(',')}`),
        fetch('/api/portfolio'),
        fetch('/api/bank-accounts')
      ]);

      const priceData = priceRes.ok ? await priceRes.json() : {};
      const portfolioData = portfolioRes.ok ? await portfolioRes.json() : [];
      const bankAccountsData = bankAccountsRes.ok ? await bankAccountsRes.json() : [];

      setQuotes(priceData);
      setPortfolio(portfolioData);
      setBankAccounts(bankAccountsData);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setQuotes({});
      setPortfolio([]);
      setBankAccounts([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  const basePortfolioArray = Array.isArray(portfolio) ? portfolio : [];
  const allSymbols = Array.from(new Set(basePortfolioArray.map(item => item.symbol)));

  const portfolioArray = basePortfolioArray.filter(item => {
    const market = getMarketFromSymbol(item.symbol, item.assetType);
    const matchesFilterType =
      filterType === 'ALL' ||
      (filterType === 'STOCK' && item.assetType === 'STOCK') ||
      (filterType === 'CRYPTO' && item.assetType === 'CRYPTO') ||
      (filterType === 'US' && market === 'US' && item.assetType === 'STOCK') ||
      (filterType === 'TW' && market === 'TW' && item.assetType === 'STOCK') ||
      (filterType === 'JP' && market === 'JP' && item.assetType === 'STOCK');

    const matchesSymbol = selectedSymbol === 'ALL' || item.symbol === selectedSymbol;
    return matchesFilterType && matchesSymbol;
  });
  const totalValue = portfolioArray.reduce((acc, curr) => acc + (curr.currentValueUSD || curr.currentValue || 0), 0);
  const totalGainLoss = portfolioArray.reduce((acc, curr) => acc + (curr.unrealizedGainLoss || 0), 0);
  // Note: totalGainLoss still mixed, but let's prioritize value for now. 
  // Ideally we also normalize gainloss.

  return (
    <div className="flex min-h-screen">
      <aside className="w-64 border-r border-white/5 bg-black/20 flex flex-col p-6 gap-8 hidden md:flex">
        <div className="flex items-center gap-3 px-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20">
            A
          </div>
          <span className="font-bold text-xl tracking-tight">AssetMaster</span>
        </div>

        <nav className="flex flex-col gap-2">
          <NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" active />
          <Link href="/ledger"><NavItem icon={<Wallet size={20} />} label="My Ledger" /></Link>
          <Link href="/settings"><NavItem icon={<SettingsIcon size={20} />} label="Settings" /></Link>
        </nav>
      </aside>

      <main className="flex-1 p-6 md:p-10 overflow-y-auto">
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-6">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Market Overview</h1>
            <p className="text-muted-foreground">Real-time status of your favorite stocks.</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex p-1 bg-white/5 border border-white/10 rounded-xl">
                {['ALL', 'US', 'TW', 'JP', 'CRYPTO'].map((t) => (
                  <button
                    key={t}
                    onClick={() => { setFilterType(t); setSelectedSymbol('ALL'); }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${filterType === t ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'text-muted-foreground hover:text-white'}`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <select
                className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-xs font-medium text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
              >
                <option value="ALL">All Assets</option>
                {allSymbols.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <button
              onClick={fetchData}
              disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-all active:scale-95 disabled:opacity-50"
            >
              <RefreshCw size={18} className={refreshing ? "animate-spin" : ""} />
              <span className="text-sm font-medium">Refresh</span>
            </button>
          </div>
        </header>

        {/* Portfolio Snapshots */}
        <section className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10">
          <div className="glass p-8 rounded-3xl border-l-4 border-blue-500">
            <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Total Asset Value</span>
            <div className="text-4xl font-black mt-2">{formatCurrency(totalValue)}</div>
          </div>
          <div className={`glass p-8 rounded-3xl border-l-4 ${totalGainLoss >= 0
            ? (colorScheme === 'TW' ? 'border-rose-500' : 'border-emerald-500')
            : (colorScheme === 'TW' ? 'border-emerald-500' : 'border-rose-500')
            }`}>
            <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Total Unrealized P/L</span>
            <div className={`text-4xl font-black mt-2 flex items-center gap-2 ${totalGainLoss >= 0
              ? (colorScheme === 'TW' ? 'text-rose-400' : 'text-emerald-400')
              : (colorScheme === 'TW' ? 'text-emerald-400' : 'text-rose-400')
              }`}>
              {totalGainLoss >= 0 ? <TrendingUp size={32} /> : <TrendingDown size={32} />}
              {formatCurrency(totalGainLoss)}
            </div>
          </div>
        </section>

        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
          {loading ? (
            Array(5).fill(0).map((_, i) => <PriceCard key={i} symbol="" price={0} currency="" loading />)
          ) : (
            TRACKED_SYMBOLS.map(symbol => {
              const q = quotes[symbol];
              if (!q) return null;
              return (
                <PriceCard
                  key={symbol}
                  symbol={symbol}
                  name={q.name}
                  price={q.price}
                  change={q.change}
                  changePercent={q.changePercent}
                  currency={q.currency}
                />
              );
            })
          )}
        </section>

        <section className="mt-12 grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 glass p-8 rounded-3xl min-h-[400px] flex flex-col">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <PieChart size={20} className="text-blue-500" />
              Allocation
            </h2>
            <div className="flex-1">
              <PortfolioPieChart data={portfolioArray} />
            </div>
          </div>

          <div className="lg:col-span-2 glass p-8 rounded-3xl min-h-[400px]">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <History size={20} className="text-purple-500" />
              Holdings Performance
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-muted-foreground text-xs uppercase border-b border-white/10">
                    <th className="pb-4 font-semibold">Symbol</th>
                    <th className="pb-4 font-semibold text-right">Qty</th>
                    <th className="pb-4 font-semibold text-right">Avg Cost</th>
                    <th className="pb-4 font-semibold text-right">Market Price</th>
                    <th className="pb-4 font-semibold text-right">Gain/Loss</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {portfolioArray.length === 0 ? (
                    <tr><td colSpan={5} className="py-20 text-center text-muted-foreground italic">No holdings yet. Add transactions in the Ledger.</td></tr>
                  ) : (
                    portfolioArray.map((p: any) => (
                      <tr key={p.symbol} className="text-sm">
                        <td className="py-4 font-bold text-white uppercase">{p.symbol}</td>
                        <td className="py-4 text-right text-white/70">{p.totalQuantity}</td>
                        <td className="py-4 text-right text-white/70">{formatCurrency(p.averageCost, p.currency)}</td>
                        <td className="py-4 text-right text-white/70">{formatCurrency(p.currentPrice, p.currency)}</td>
                        <td className={`py-4 text-right font-bold ${p.unrealizedGainLoss >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {formatCurrency(p.unrealizedGainLoss, p.currency)}
                          <div className="text-[10px]">{p.unrealizedGainLossPercentage.toFixed(2)}%</div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Bank Accounts Section */}
        <section className="mt-12">
          <BankAccounts accounts={bankAccounts} onRefresh={fetchData} />
        </section>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active = false }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <button className={`
      flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all
      ${active ? 'bg-blue-600/10 text-blue-500 shadow-sm border border-blue-500/20' : 'text-muted-foreground hover:bg-white/5 hover:text-white'}
    `}>
      {icon}
      {label}
    </button>
  );
}
