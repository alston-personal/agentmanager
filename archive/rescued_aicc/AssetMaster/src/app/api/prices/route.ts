import { NextResponse } from 'next/server';
import { getStockQuotes, getCryptoQuotes } from '@/lib/finance';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbolsParam = searchParams.get('symbols');

  if (!symbolsParam) {
    return NextResponse.json({ error: 'Symbols parameter is required' }, { status: 400 });
  }

  const allSymbols = symbolsParam.split(',').map(s => s.trim());
  const cryptoSymbols = allSymbols.filter(s => s.includes('/'));
  const stockSymbols = allSymbols.filter(s => !s.includes('/'));

  try {
    let combinedData = {};

    if (stockSymbols.length > 0) {
      const stockMap = await getStockQuotes(stockSymbols);
      combinedData = { ...combinedData, ...Object.fromEntries(stockMap) };
    }

    if (cryptoSymbols.length > 0) {
      const cryptoMap = await getCryptoQuotes(cryptoSymbols);
      combinedData = { ...combinedData, ...Object.fromEntries(cryptoMap) };
    }

    return NextResponse.json(combinedData);
  } catch (error) {
    console.error('API Price Error:', error);
    return NextResponse.json({ error: 'Failed to fetch prices' }, { status: 500 });
  }
}
