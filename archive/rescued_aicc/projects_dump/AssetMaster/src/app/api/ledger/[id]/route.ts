import { NextResponse } from 'next/server';
import { prisma } from '@/lib/db';

export async function PUT(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const id = params.id;
    const data = await request.json();

    const transaction = await prisma.transaction.update({
      where: { id },
      data: {
        date: new Date(data.date),
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
    console.error('Ledger PUT Error:', error);
    return NextResponse.json({ error: 'Failed to update transaction' }, { status: 500 });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: { id: string } }
) {
  try {
    const id = params.id;
    await prisma.transaction.delete({
      where: { id },
    });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Ledger DELETE Error:', error);
    return NextResponse.json({ error: 'Failed to delete transaction' }, { status: 500 });
  }
}
