import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { PrismaBetterSqlite3 } from '@prisma/adapter-better-sqlite3';
import path from 'path';

function getPrisma() {
  const dbPath = path.resolve(process.cwd(), 'prisma', 'dev.db');
  const adapter = new PrismaBetterSqlite3({ url: `file:${dbPath}` });
  return new PrismaClient({ adapter });
}

export async function POST() {
  const prisma = getPrisma();
  try {
    // 1. Initial Settings
    await prisma.systemSetting.upsert({
      where: { key: 'colorScheme' },
      update: {},
      create: { key: 'colorScheme', value: 'US' },
    });

    // 2. Initial Fee Rules (Standard Defaults)
    await prisma.feeRule.deleteMany({ where: { isSystem: true } });

    await prisma.feeRule.createMany({
      data: [
        { market: 'TW', assetType: 'STOCK', actionType: 'BUY', feeRate: 0.1425, taxRate: 0, minFee: 20, isSystem: true, description: 'Taiwan Stock Buy Standard' },
        { market: 'TW', assetType: 'STOCK', actionType: 'SELL', feeRate: 0.1425, taxRate: 0.3, minFee: 20, isSystem: true, description: 'Taiwan Stock Sell Standard' },
        { market: 'US', assetType: 'STOCK', actionType: 'ANY', feeRate: 0, taxRate: 0, minFee: 0, isSystem: true, description: 'US Stock Free Standard' },
        { market: 'JPY', assetType: 'STOCK', actionType: 'ANY', feeRate: 0.1, taxRate: 0, minFee: 0, isSystem: true, description: 'Japan Stock Standard' },
        { market: 'CRYPTO', assetType: 'CRYPTO', actionType: 'ANY', feeRate: 0.1, taxRate: 0, minFee: 0, isSystem: true, description: 'Crypto Standard' },
      ]
    });

    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('Init Error:', error);
    return NextResponse.json({ error: 'Init failed', details: error.message }, { status: 500 });
  } finally {
    await prisma.$disconnect();
  }
}
