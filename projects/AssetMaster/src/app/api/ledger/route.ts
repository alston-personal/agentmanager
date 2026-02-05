import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function GET() {
  try {
    const transactions = await prisma.transaction.findMany({
      orderBy: { date: 'desc' },
    });
    return NextResponse.json(transactions);
  } catch (error) {
    console.error('Ledger GET Error:', error);
    return NextResponse.json({ error: 'Failed to fetch ledger' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const data = await request.json();

    // Simple validation
    if (!data.symbol || !data.type || !data.quantity) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const transaction = await prisma.transaction.create({
      data: {
        date: new Date(data.date || Date.now()),
        assetType: data.assetType,
        symbol: data.symbol,
        type: data.type,
        quantity: parseFloat(data.quantity),
        price: parseFloat(data.price),
        currency: data.currency,
        exchangeRate: parseFloat(data.exchangeRate || 1),
        commission: parseFloat(data.commission || 0),
        tax: parseFloat(data.tax || 0),
        totalAmount: parseFloat(data.totalAmount),
        notes: data.notes,
        ratio: data.ratio ? parseFloat(data.ratio) : null,
      },
    });

    return NextResponse.json(transaction);
  } catch (error) {
    console.error('Ledger POST Error:', error);
    return NextResponse.json({ error: 'Failed to create transaction' }, { status: 500 });
  }
}
