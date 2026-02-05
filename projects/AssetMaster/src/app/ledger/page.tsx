'use client';

import { useState, useEffect } from 'react';
import { LayoutDashboard, Wallet, Plus, Loader2, Settings as SettingsIcon } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';
import Link from 'next/link';
import { AddTransactionModal } from '@/components/AddTransactionModal';
import { EditTransactionModal } from '@/components/EditTransactionModal';

export default function LedgerPage() {
  const [transactions, setTransactions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [editingTransaction, setEditingTransaction] = useState<any>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('ALL');

  async function fetchLedger() {
    try {
      const res = await fetch('/api/ledger');
      const data = res.ok ? await res.json() : [];
      setTransactions(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to fetch ledger:', error);
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchLedger();
  }, []);

  const filteredTransactions = transactions.filter(t => {
    const matchesSearch = t.symbol.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterType === 'ALL' || t.assetType === filterType;
    return matchesSearch && matchesFilter;
  });

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
          <NavItem icon={<Wallet size={20} />} label="My Ledger" active />
          <Link href="/settings"><NavItem icon={<SettingsIcon size={20} />} label="Settings" /></Link>
        </nav>
      </aside>

      <main className="flex-1 p-6 md:p-10 overflow-y-auto">
        <header className="flex flex-col md:flex-row justify-between items-start md:items-center mb-10 gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Transaction Ledger</h1>
            <p className="text-muted-foreground">Manage your history of buys, sells, and dividends.</p>
          </div>
          <button
            onClick={() => setIsAdding(true)}
            className="flex items-center gap-2 px-6 py-3 bg-blue-600 rounded-xl hover:bg-blue-700 transition-all font-semibold shadow-lg shadow-blue-600/20 active:scale-95 text-white"
          >
            <Plus size={20} />
            <span>Add Transaction</span>
          </button>
        </header>

        <section className="flex flex-col md:flex-row gap-4 mb-6">
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="Search symbols..."
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <select
            className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="ALL">All Assets</option>
            <option value="STOCK">Stocks</option>
            <option value="CRYPTO">Crypto</option>
            <option value="CASH">Cash</option>
          </select>
        </section>

        <section className="glass rounded-3xl overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-white/5 text-muted-foreground text-sm uppercase tracking-wider">
                <th className="px-6 py-4 font-semibold">Date</th>
                <th className="px-6 py-4 font-semibold">Asset</th>
                <th className="px-6 py-4 font-semibold">Type</th>
                <th className="px-6 py-4 font-semibold">Quantity</th>
                <th className="px-6 py-4 font-semibold">Price</th>
                <th className="px-6 py-4 font-semibold text-right">Total</th>
                <th className="px-6 py-4 font-semibold text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-20 text-center">
                    <Loader2 className="animate-spin inline-block mr-2" />
                    Loading transactions...
                  </td>
                </tr>
              ) : filteredTransactions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-20 text-center text-muted-foreground">
                    No transactions found matching your criteria.
                  </td>
                </tr>
              ) : (
                filteredTransactions.map((t) => (
                  <tr key={t.id} className="hover:bg-white/5 transition-colors group">
                    <td className="px-6 py-4 text-sm text-white/80">{new Date(t.date).toLocaleDateString()}</td>
                    <td className="px-6 py-4 font-bold text-white uppercase">{t.symbol}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase ${t.type === 'BUY' ? 'bg-blue-500 text-white shadow-sm shadow-blue-500/20' :
                        t.type === 'SELL' ? 'bg-orange-600 text-white shadow-sm shadow-orange-500/20' :
                          'bg-purple-600 text-white shadow-sm shadow-purple-500/20'
                        }`}>
                        {t.type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-white/80">{t.quantity}</td>
                    <td className="px-6 py-4 text-sm text-white/80">{formatCurrency(t.price, t.currency)}</td>
                    <td className="px-6 py-4 text-sm font-bold text-white text-right">{formatCurrency(t.totalAmount, t.currency)}</td>
                    <td className="px-6 py-4 text-center">
                      <div className="flex justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => setEditingTransaction(t)}
                          className="px-3 py-1.5 hover:bg-white/10 rounded-lg text-xs font-semibold text-white/70 hover:text-white transition-colors"
                        >
                          Edit
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </main>

      {/* Add Transaction Modal */}
      {isAdding && (
        <AddTransactionModal
          onClose={() => setIsAdding(false)}
          onSuccess={fetchLedger}
        />
      )}
      {editingTransaction && (
        <EditTransactionModal
          transaction={editingTransaction}
          onClose={() => setEditingTransaction(null)}
          onSuccess={fetchLedger}
        />
      )}
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
