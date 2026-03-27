'use client';

import { useState, useEffect } from 'react';
import { X, Loader2 } from 'lucide-react';
import { calculateFees, getMarketFromSymbol } from '@/lib/utils';

interface AddTransactionModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function AddTransactionModal({ onClose, onSuccess }: AddTransactionModalProps) {
  const [loading, setLoading] = useState(false);
  const [feeRules, setFeeRules] = useState<any[]>([]);
  const [formData, setFormData] = useState({
    date: new Date().toISOString().split('T')[0],
    assetType: 'STOCK',
    symbol: '',
    type: 'BUY',
    quantity: '',
    price: '',
    currency: 'USD',
    exchangeRate: '1',
    commission: '0',
    tax: '0',
    notes: '',
  });

  useEffect(() => {
    async function fetchRules() {
      const res = await fetch('/api/settings/fee-rules');
      if (res.ok) setFeeRules(await res.json());
    }
    fetchRules();
  }, []);

  // Auto-calculate fees
  useEffect(() => {
    const q = parseFloat(formData.quantity);
    const p = parseFloat(formData.price);
    if (!isNaN(q) && !isNaN(p) && formData.symbol) {
      const { commission, tax } = calculateFees(
        formData.symbol,
        formData.assetType,
        formData.type,
        q,
        p,
        feeRules
      );
      setFormData(prev => ({
        ...prev,
        commission: commission.toString(),
        tax: tax.toString()
      }));
    }
  }, [formData.symbol, formData.assetType, formData.type, formData.quantity, formData.price]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const totalAmount = (parseFloat(formData.quantity) * parseFloat(formData.price)) +
      parseFloat(formData.commission) + parseFloat(formData.tax);

    try {
      const res = await fetch('/api/ledger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          totalAmount: totalAmount.toString(),
        }),
      });

      if (res.ok) {
        onSuccess();
        onClose();
      } else {
        alert('Failed to add transaction');
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="glass w-full max-w-2xl p-8 rounded-3xl animate-in fade-in zoom-in duration-300 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white">Add New Transaction</h2>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Date</label>
            <input
              type="date"
              required
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.date}
              onChange={(e) => setFormData({ ...formData, date: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Asset Type</label>
            <select
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.assetType}
              onChange={(e) => setFormData({ ...formData, assetType: e.target.value })}
            >
              <option value="STOCK">Stock</option>
              <option value="CRYPTO">Crypto</option>
              <option value="CASH">Cash</option>
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Symbol (e.g. AAPL, 2330.TW, BTC/USDT)</label>
            <input
              type="text"
              required
              placeholder="AAPL"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"
              value={formData.symbol}
              onChange={(e) => {
                const sym = e.target.value.toUpperCase();
                let currency = formData.currency;
                const market = getMarketFromSymbol(sym, formData.assetType);
                if (market === 'TW') currency = 'TWD';
                else if (market === 'JP') currency = 'JPY';
                else if (market === 'US') currency = 'USD';
                else if (market === 'CRYPTO') currency = 'USDT';
                setFormData({ ...formData, symbol: sym, currency });
              }}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Transaction Type</label>
            <select
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            >
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
              <option value="DIVIDEND_CASH">Dividend (Cash)</option>
              <option value="DIVIDEND_STOCK">Dividend (Stock)</option>
              <option value="DEPOSIT">Deposit</option>
              <option value="WITHDRAW">Withdraw</option>
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Quantity</label>
            <input
              type="number"
              step="any"
              required
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.quantity}
              onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Price</label>
            <input
              type="number"
              step="any"
              required
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.price}
              onChange={(e) => setFormData({ ...formData, price: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Currency</label>
            <select
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.currency}
              onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
            >
              <option value="USD">USD</option>
              <option value="TWD">TWD</option>
              <option value="JPY">JPY</option>
              <option value="USDT">USDT</option>
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Commission / Fees</label>
            <input
              type="number"
              step="any"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={formData.commission}
              onChange={(e) => setFormData({ ...formData, commission: e.target.value })}
            />
          </div>

          <div className="md:col-span-2 space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Notes</label>
            <textarea
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[80px]"
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            />
          </div>

          <div className="md:col-span-2 mt-4">
            <button
              type="submit"
              disabled={loading}
              className="w-full py-4 bg-blue-600 hover:bg-blue-700 rounded-2xl transition-all font-bold text-white shadow-lg shadow-blue-600/20 active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading && <Loader2 size={20} className="animate-spin" />}
              Save Transaction
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
