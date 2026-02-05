'use client';

import { useState } from 'react';
import { Wallet, Plus, Edit2, Trash2, Building2, Bitcoin } from 'lucide-react';
import { formatCurrency } from '@/lib/utils';

interface BankAccount {
  id: string;
  accountName: string;
  accountType: string;
  currency: string;
  balance: number;
  institution?: string;
  notes?: string;
  isActive: boolean;
}

interface BankAccountsProps {
  accounts: BankAccount[];
  onRefresh: () => void;
}

export function BankAccounts({ accounts, onRefresh }: BankAccountsProps) {
  const [showModal, setShowModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState<BankAccount | null>(null);
  const [formData, setFormData] = useState({
    accountName: '',
    accountType: 'FIAT',
    currency: 'TWD',
    balance: 0,
    institution: '',
    notes: ''
  });

  const fiatAccounts = accounts.filter(a => a.accountType === 'FIAT');
  const cryptoAccounts = accounts.filter(a => a.accountType === 'CRYPTO');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      if (editingAccount) {
        // Update existing account
        await fetch('/api/bank-accounts', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: editingAccount.id, ...formData })
        });
      } else {
        // Create new account
        await fetch('/api/bank-accounts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formData)
        });
      }

      setShowModal(false);
      setEditingAccount(null);
      setFormData({
        accountName: '',
        accountType: 'FIAT',
        currency: 'TWD',
        balance: 0,
        institution: '',
        notes: ''
      });
      onRefresh();
    } catch (error) {
      console.error('Error saving account:', error);
    }
  };

  const handleEdit = (account: BankAccount) => {
    setEditingAccount(account);
    setFormData({
      accountName: account.accountName,
      accountType: account.accountType,
      currency: account.currency,
      balance: account.balance,
      institution: account.institution || '',
      notes: account.notes || ''
    });
    setShowModal(true);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('確定要刪除此帳戶嗎？')) return;

    try {
      await fetch(`/api/bank-accounts?id=${id}`, { method: 'DELETE' });
      onRefresh();
    } catch (error) {
      console.error('Error deleting account:', error);
    }
  };

  const getTotalByType = (type: string) => {
    return accounts
      .filter(a => a.accountType === type)
      .reduce((sum, a) => sum + a.balance, 0);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Wallet size={24} className="text-blue-500" />
          銀行餘額
        </h2>
        <button
          onClick={() => {
            setEditingAccount(null);
            setFormData({
              accountName: '',
              accountType: 'FIAT',
              currency: 'TWD',
              balance: 0,
              institution: '',
              notes: ''
            });
            setShowModal(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-xl transition-all active:scale-95"
        >
          <Plus size={18} />
          新增帳戶
        </button>
      </div>

      {/* Fiat Accounts */}
      <div className="glass p-6 rounded-3xl">
        <div className="flex items-center gap-2 mb-4">
          <Building2 size={20} className="text-emerald-500" />
          <h3 className="text-lg font-bold">法定貨幣帳戶</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {fiatAccounts.length === 0 ? (
            <p className="text-muted-foreground italic col-span-full">尚無法定貨幣帳戶</p>
          ) : (
            fiatAccounts.map(account => (
              <AccountCard
                key={account.id}
                account={account}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>

      {/* Crypto Accounts */}
      <div className="glass p-6 rounded-3xl">
        <div className="flex items-center gap-2 mb-4">
          <Bitcoin size={20} className="text-orange-500" />
          <h3 className="text-lg font-bold">加密貨幣帳戶</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {cryptoAccounts.length === 0 ? (
            <p className="text-muted-foreground italic col-span-full">尚無加密貨幣帳戶</p>
          ) : (
            cryptoAccounts.map(account => (
              <AccountCard
                key={account.id}
                account={account}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass p-8 rounded-3xl max-w-md w-full border border-white/10">
            <h3 className="text-xl font-bold mb-6">
              {editingAccount ? '編輯帳戶' : '新增帳戶'}
            </h3>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">帳戶名稱 *</label>
                <input
                  type="text"
                  required
                  value={formData.accountName}
                  onChange={e => setFormData({ ...formData, accountName: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="例如：台新銀行台幣帳戶"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">帳戶類型 *</label>
                <select
                  required
                  value={formData.accountType}
                  onChange={e => setFormData({ ...formData, accountType: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={!!editingAccount}
                >
                  <option value="FIAT">法定貨幣</option>
                  <option value="CRYPTO">加密貨幣</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">幣別 *</label>
                <select
                  required
                  value={formData.currency}
                  onChange={e => setFormData({ ...formData, currency: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  disabled={!!editingAccount}
                >
                  {formData.accountType === 'FIAT' ? (
                    <>
                      <option value="TWD">台幣 (TWD)</option>
                      <option value="USD">美元 (USD)</option>
                      <option value="JPY">日圓 (JPY)</option>
                    </>
                  ) : (
                    <>
                      <option value="USDT">USDT</option>
                      <option value="BTC">BTC</option>
                      <option value="ETH">ETH</option>
                      <option value="BNB">BNB</option>
                    </>
                  )}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">餘額 *</label>
                <input
                  type="number"
                  required
                  step="0.01"
                  value={formData.balance}
                  onChange={e => setFormData({ ...formData, balance: parseFloat(e.target.value) || 0 })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">金融機構</label>
                <input
                  type="text"
                  value={formData.institution}
                  onChange={e => setFormData({ ...formData, institution: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="例如：台新銀行、Binance"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">備註</label>
                <textarea
                  value={formData.notes}
                  onChange={e => setFormData({ ...formData, notes: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  rows={2}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingAccount(null);
                  }}
                  className="flex-1 px-4 py-2 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 transition-all"
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-xl transition-all active:scale-95"
                >
                  {editingAccount ? '更新' : '新增'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function AccountCard({
  account,
  onEdit,
  onDelete
}: {
  account: BankAccount;
  onEdit: (account: BankAccount) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 hover:bg-white/10 transition-all">
      <div className="flex justify-between items-start mb-3">
        <div className="flex-1">
          <h4 className="font-bold text-white">{account.accountName}</h4>
          {account.institution && (
            <p className="text-xs text-muted-foreground mt-1">{account.institution}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onEdit(account)}
            className="p-1.5 hover:bg-white/10 rounded-lg transition-all"
            title="編輯"
          >
            <Edit2 size={14} className="text-blue-400" />
          </button>
          <button
            onClick={() => onDelete(account.id)}
            className="p-1.5 hover:bg-white/10 rounded-lg transition-all"
            title="刪除"
          >
            <Trash2 size={14} className="text-rose-400" />
          </button>
        </div>
      </div>

      <div className="text-2xl font-black text-white">
        {formatCurrency(account.balance, account.currency)}
      </div>

      {account.notes && (
        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{account.notes}</p>
      )}
    </div>
  );
}
