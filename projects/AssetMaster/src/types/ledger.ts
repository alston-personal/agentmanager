export type AssetType = 'STOCK' | 'CRYPTO' | 'CASH';

export type TransactionType =
  | 'BUY'            // 買入
  | 'SELL'           // 賣出
  | 'DIVIDEND_CASH'  // 配息 (現金股利)
  | 'DIVIDEND_STOCK' // 配股 (股票股利)
  | 'SPLIT'          // 股票分割
  | 'MERGE'          // 股票合併
  | 'DEPOSIT'        // 入金 (入現金到帳戶)
  | 'WITHDRAW';      // 出金 (提領現金)

export type Currency = 'USD' | 'TWD' | 'JPY' | 'USDT' | 'BTC' | 'ETH';

export interface LedgerEntry {
  id: string;
  date: string;              // ISO Date string
  assetType: AssetType;
  symbol: string;            // e.g., "AAPL", "2330.TW", "BTC", or "CASH"
  type: TransactionType;
  quantity: number;          // 數量 (買賣股數、配股數、入金金額等)
  price: number;             // 單價 (買賣價格、配息金額/每股)
  currency: Currency;        // 交易幣別
  exchangeRate: number;      // 當時對基準貨幣的匯率
  commission: number;        // 手續費
  tax: number;               // 稅金
  totalAmount: number;       // 總計金額 (包含收支)
  notes?: string;            // 備註
  ratio?: number;            // 僅用於 SPLIT/MERGE (例如 1:10 則為 10)
}

/**
 * 投資組合摘要介面
 */
export interface PortfolioSummary {
  symbol: string;
  assetType: AssetType;
  totalQuantity: number;
  averageCost: number;
  currentPrice: number;
  currentValue: number;
  unrealizedGainLoss: number;
  unrealizedGainLossPercentage: number;
  realizedGainLoss: number;
}
