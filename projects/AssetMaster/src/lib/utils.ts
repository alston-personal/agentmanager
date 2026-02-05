import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, currency: string = 'USD') {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(value);
  } catch (e) {
    // Fallback for non-standard currencies (e.g., USDT, BTC)
    return `${value.toLocaleString('en-US', { minimumFractionDigits: 2 })} ${currency.toUpperCase()}`;
  }
}

export function formatPercent(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
  }).format(value / 100);
}

export function getMarketFromSymbol(symbol: string, assetType: string) {
  if (assetType === 'CRYPTO') return 'CRYPTO';
  if (symbol.endsWith('.TW')) return 'TW';
  if (symbol.endsWith('.T')) return 'JP';
  return 'US';
}

export function calculateFees(
  symbol: string,
  assetType: string,
  type: string,
  quantity: number,
  price: number,
  rules: any[] = []
) {
  const market = getMarketFromSymbol(symbol, assetType);
  const totalValue = quantity * price;

  // Sort rules to prioritize CUSTOM rules (isSystem === false) over SYSTEM rules
  const sortedRules = [...rules].sort((a, b) => (Number(a.isSystem) - Number(b.isSystem)));

  // Try to find a matching rule from the table
  const rule = sortedRules.find(r =>
    r.market.toUpperCase() === market.toUpperCase() &&
    r.assetType.toUpperCase() === assetType.toUpperCase() &&
    (r.actionType === 'ANY' || r.actionType === type)
  );

  if (rule) {
    const feeRate = parseFloat(rule.feeRate) / 100;
    const taxRate = parseFloat(rule.taxRate) / 100;
    const minFee = parseFloat(rule.minFee);

    let commission = totalValue * feeRate;
    if (commission < minFee) commission = minFee;

    const tax = totalValue * taxRate;

    // For TW market, round the results
    if (market === 'TW') {
      return { commission: Math.round(commission), tax: Math.round(tax) };
    }
    return { commission, tax };
  }

  return { commission: 0, tax: 0 };
}
