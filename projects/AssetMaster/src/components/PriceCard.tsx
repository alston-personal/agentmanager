'use client';

import { TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { cn, formatCurrency, formatPercent } from '@/lib/utils';
import { useSettings } from '@/context/SettingsContext';

interface PriceCardProps {
  symbol: string;
  name?: string;
  price: number;
  change?: number;
  changePercent?: number;
  currency: string;
  loading?: boolean;
}

export function PriceCard({
  symbol,
  name,
  price,
  change = 0,
  changePercent = 0,
  currency,
  loading = false,
}: PriceCardProps) {
  const { colorScheme } = useSettings();

  if (loading) {
    return (
      <div className="glass p-6 rounded-2xl animate-pulse">
        <div className="h-4 w-16 bg-white/10 rounded mb-4" />
        <div className="h-8 w-32 bg-white/10 rounded mb-2" />
        <div className="h-4 w-24 bg-white/10 rounded" />
      </div>
    );
  }

  const isPositive = change > 0;
  const isNegative = change < 0;

  // Color logic based on scheme
  const upColor = colorScheme === 'TW' ? 'text-rose-400' : 'text-emerald-400';
  const downColor = colorScheme === 'TW' ? 'text-emerald-400' : 'text-rose-400';
  const upBg = colorScheme === 'TW' ? 'bg-rose-500/10' : 'bg-emerald-500/10';
  const downBg = colorScheme === 'TW' ? 'bg-emerald-500/10' : 'bg-rose-500/10';

  return (
    <div className="glass p-6 rounded-2xl transition-all duration-300">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">{symbol}</h3>
          <p className="text-sm font-semibold text-white/80 line-clamp-1">{name}</p>
        </div>
        <div className={cn(
          "px-2 py-1 rounded-md text-xs font-bold flex items-center gap-1",
          isPositive ? `${upBg} ${upColor}` :
            isNegative ? `${downBg} ${downColor}` : "bg-white/10 text-white/60"
        )}>
          {isPositive ? <TrendingUp size={14} /> : isNegative ? <TrendingDown size={14} /> : <Minus size={14} />}
          {formatPercent(Math.abs(changePercent))}
        </div>
      </div>

      <div className="mt-2">
        <div className="text-3xl font-bold tracking-tight text-white">
          {formatCurrency(price, currency)}
        </div>
        <div className={cn(
          "text-sm font-medium mt-1 transition-colors",
          isPositive ? upColor : isNegative ? downColor : "text-white/40"
        )}>
          {isPositive ? '+' : ''}{change.toFixed(2)} ({currency})
        </div>
      </div>
    </div>
  );
}
