import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import path from 'path';

function getPrisma() {
  const dbPath = path.resolve(process.cwd(), 'prisma', 'dev.db');
  const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
  return new PrismaClient({ adapter });
}

export async function GET() {
  const prisma = getPrisma();
  try {
    const rules = await prisma.feeRule.findMany({
      orderBy: { market: 'asc' }
    });
    return NextResponse.json(rules);
  } catch (error) {
    console.error('FeeRules GET Error:', error);
    return NextResponse.json({ error: 'Failed to fetch fee rules' }, { status: 500 });
  } finally {
    await prisma.$disconnect();
  }
}

export async function POST(request: Request) {
  const prisma = getPrisma();
  try {
    const data = await request.json();
    const rule = await prisma.feeRule.create({
      data: {
        market: data.market,
        assetType: data.assetType,
        actionType: data.actionType,
        feeRate: parseFloat(data.feeRate || 0),
        taxRate: parseFloat(data.taxRate || 0),
        minFee: parseFloat(data.minFee || 0),
        description: data.description,
        isSystem: false, // User created rules are never system rules
      },
    });
    return NextResponse.json(rule);
  } catch (error) {
    console.error('FeeRules POST Error:', error);
    return NextResponse.json({ error: 'Failed to create fee rule' }, { status: 500 });
  } finally {
    await prisma.$disconnect();
  }
}

export async function DELETE(request: Request) {
  const prisma = getPrisma();
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');
    if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 });

    await prisma.feeRule.delete({ where: { id } });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('FeeRules DELETE Error:', error);
    return NextResponse.json({ error: 'Failed to delete fee rule' }, { status: 500 });
  } finally {
    await prisma.$disconnect();
  }
}
