import yf from 'yahoo-finance2';
import ccxt from 'ccxt';

// In some environments, yahoo-finance2 needs to be initialized or accessed via default
const yahooFinance = typeof yf === 'function' ? new (yf as any)() : yf;

const binance = new ccxt.binance();


export interface StockQuote {
  symbol: string;
  price: number;
  currency: string;
  name?: string;
  exchange?: string;
  change?: number;
  changePercent?: number;
  updatedAt: Date;
}

/**
 * 獲取單一或多個標的的報價
 * @param symbols 標的代码，例如 ['AAPL', '2330.TW', '9984.T']
 */
export async function getStockQuotes(symbols: string[]): Promise<Map<string, StockQuote>> {
  const quotesMap = new Map<string, StockQuote>();

  // Fetch individually or in small chunks to prevent one failure from stopping others
  await Promise.all(symbols.map(async (symbol) => {
    try {
      const q: any = await yahooFinance.quote(symbol);
      if (q && q.symbol) {
        quotesMap.set(q.symbol, {
          symbol: q.symbol,
          price: q.regularMarketPrice || 0,
          currency: q.currency || 'USD',
          name: q.shortName || q.longName,
          exchange: q.fullExchangeName,
          change: q.regularMarketChange,
          changePercent: q.regularMarketChangePercent,
          updatedAt: new Date(),
        });
      }
    } catch (error: any) {
      console.warn(`Failed to fetch quote for ${symbol}:`, error.message);
      // Don't throw, just skip this symbol so the rest of the portfolio can load
    }
  }));

  return quotesMap;
}

/**
 * 獲取加密貨幣報價 (Binance)
 * @param symbols 標的代码，例如 ['BTC/USDT', 'ETH/USDT']
 */
export async function getCryptoQuotes(symbols: string[]): Promise<Map<string, StockQuote>> {
  const quotesMap = new Map<string, StockQuote>();

  try {
    const tickers = await binance.fetchTickers(symbols);

    for (const symbol of symbols) {
      const ticker = tickers[symbol];
      if (ticker) {
        quotesMap.set(symbol, {
          symbol: symbol,
          price: ticker.last || 0,
          currency: 'USDT',
          name: symbol.split('/')[0],
          exchange: 'Binance',
          change: ticker.change,
          changePercent: ticker.percentage,
          updatedAt: new Date(),
        });
      }
    }
  } catch (error) {
    console.error('Error fetching crypto quotes:', error);
  }

  return quotesMap;
}

/**
 * 獲取歷史價格 (用於畫趨勢圖)
 */
export async function getHistoricalData(symbol: string, from: string, to: string) {
  try {
    const queryOptions = { period1: from, period2: to };
    const result = await yahooFinance.historical(symbol, queryOptions);
    return result;
  } catch (error) {
    console.error(`Error fetching historical data for ${symbol}:`, error);
    throw error;
  }
}

/**
 * 獲取匯率，例如 USDTWD=X
 * @param pairs 匯率對，例如 ['USDTWD=X', 'JPYUSD=X']
 */
export async function getExchangeRates(pairs: string[]): Promise<Map<string, number>> {
  const ratesMap = new Map<string, number>();
  try {
    await Promise.all(pairs.map(async (pair) => {
      try {
        const q: any = await yahooFinance.quote(pair);
        if (q && q.regularMarketPrice) {
          ratesMap.set(pair, q.regularMarketPrice);
        }
      } catch (e) {
        console.warn(`Failed to fetch rate for ${pair}`);
      }
    }));
  } catch (error) {
    console.error('Error fetching exchange rates:', error);
  }
  return ratesMap;
}
