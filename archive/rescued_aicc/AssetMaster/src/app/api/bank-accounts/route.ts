import { NextRequest, NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// GET /api/bank-accounts - Get all bank accounts
export async function GET() {
  try {
    const accounts = await prisma.bankAccount.findMany({
      where: { isActive: true },
      orderBy: [
        { accountType: 'asc' },
        { currency: 'asc' }
      ]
    });

    return NextResponse.json(accounts);
  } catch (error) {
    console.error('Error fetching bank accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch bank accounts' }, { status: 500 });
  }
}

// POST /api/bank-accounts - Create a new bank account
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { accountName, accountType, currency, balance, institution, notes } = body;

    if (!accountName || !accountType || !currency) {
      return NextResponse.json(
        { error: 'Missing required fields: accountName, accountType, currency' },
        { status: 400 }
      );
    }

    const account = await prisma.bankAccount.create({
      data: {
        accountName,
        accountType,
        currency,
        balance: balance || 0,
        institution,
        notes
      }
    });

    return NextResponse.json(account, { status: 201 });
  } catch (error) {
    console.error('Error creating bank account:', error);
    return NextResponse.json({ error: 'Failed to create bank account' }, { status: 500 });
  }
}

// PATCH /api/bank-accounts - Update a bank account
export async function PATCH(req: NextRequest) {
  try {
    const body = await req.json();
    const { id, accountName, balance, institution, notes, isActive } = body;

    if (!id) {
      return NextResponse.json({ error: 'Missing account ID' }, { status: 400 });
    }

    const updateData: any = {};
    if (accountName !== undefined) updateData.accountName = accountName;
    if (balance !== undefined) updateData.balance = balance;
    if (institution !== undefined) updateData.institution = institution;
    if (notes !== undefined) updateData.notes = notes;
    if (isActive !== undefined) updateData.isActive = isActive;

    const account = await prisma.bankAccount.update({
      where: { id },
      data: updateData
    });

    return NextResponse.json(account);
  } catch (error) {
    console.error('Error updating bank account:', error);
    return NextResponse.json({ error: 'Failed to update bank account' }, { status: 500 });
  }
}

// DELETE /api/bank-accounts - Soft delete a bank account
export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ error: 'Missing account ID' }, { status: 400 });
    }

    const account = await prisma.bankAccount.update({
      where: { id },
      data: { isActive: false }
    });

    return NextResponse.json(account);
  } catch (error) {
    console.error('Error deleting bank account:', error);
    return NextResponse.json({ error: 'Failed to delete bank account' }, { status: 500 });
  }
}
