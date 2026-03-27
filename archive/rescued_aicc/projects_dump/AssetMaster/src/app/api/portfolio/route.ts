import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';
import { getStockQuotes, getCryptoQuotes, getExchangeRates } from '@/lib/finance';

export async function GET() {
  try {
    const transactions = await prisma.transaction.findMany();

    // Group transactions by symbol
    const portfolio: Record<string, any> = {};

    transactions.forEach((t) => {
      if (!portfolio[t.symbol]) {
        portfolio[t.symbol] = {
          symbol: t.symbol,
          assetType: t.assetType,
          totalQuantity: 0,
          totalCost: 0,
          currency: t.currency,
        };
      }

      const p = portfolio[t.symbol];

      if (t.type === 'BUY' || t.type === 'DIVIDEND_STOCK' || t.type === 'DEPOSIT') {
        p.totalQuantity += t.quantity;
        // Simplified cost basis calculation (Weighted Average)
        if (t.type === 'BUY') {
          p.totalCost += t.totalAmount;
        }
      } else if (t.type === 'SELL' || t.type === 'WITHDRAW') {
        p.totalQuantity -= t.quantity;
        // Selling doesn't change average cost basis, but decreases total cost proportional to quantity
        // This is a simplified FIFO/WAC approach
      }
    });

    // Remove assets with 0 quantity
    const activeSymbols = Object.keys(portfolio).filter(s => portfolio[s].totalQuantity > 0);

    // Fetch current prices
    const cryptoSymbols = activeSymbols.filter(s => s.includes('/'));
    const stockSymbols = activeSymbols.filter(s => !s.includes('/'));

    let currentPrices: Record<string, any> = {};

    if (stockSymbols.length > 0) {
      const stockQuotes = await getStockQuotes(stockSymbols);
      currentPrices = { ...currentPrices, ...Object.fromEntries(stockQuotes) };
    }
    if (cryptoSymbols.length > 0) {
      const cryptoQuotes = await getCryptoQuotes(cryptoSymbols);
      currentPrices = { ...currentPrices, ...Object.fromEntries(cryptoQuotes) };
    }

    // Fetch exchange rates if needed
    let twdRate = 1 / 32; // Fallback
    if (activeSymbols.some(s => portfolio[s].currency === 'TWD')) {
      const rates = await getExchangeRates(['TWDUSD=X']);
      twdRate = rates.get('TWDUSD=X') || twdRate;
    }

    // Final calculation
    const results = activeSymbols.map((symbol) => {
      const p = portfolio[symbol];
      const current = currentPrices[symbol];
      const price = current?.price || 0;
      const value = p.totalQuantity * price;

      // Normalize to USD for total calculation
      let valueUSD = value;
      if (p.currency === 'TWD') valueUSD = value * twdRate;
      // USDT is roughly 1:1 with USD for dashboard purposes

      const avgCost = p.totalQuantity > 0 ? (p.totalCost / p.totalQuantity) : 0;
      const gainLoss = value - p.totalCost;
      const gainLossPercent = p.totalCost > 0 ? (gainLoss / p.totalCost) * 100 : 0;

      return {
        ...p,
        currentPrice: price,
        currentValue: value,
        currentValueUSD: valueUSD, // New field for normalized total
        averageCost: avgCost,
        unrealizedGainLoss: gainLoss,
        unrealizedGainLossPercentage: gainLossPercent,
      };
    });

    return NextResponse.json(results);
  } catch (error) {
    console.error('Portfolio API Error:', error);
    return NextResponse.json({ error: 'Failed to calculate portfolio' }, { status: 500 });
  }
}
