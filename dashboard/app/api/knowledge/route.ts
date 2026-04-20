import { NextResponse } from 'next/server';
import { getAllKnowledgeItems } from '@/lib/knowledge';

export async function GET() {
  try {
    const items = getAllKnowledgeItems();
    return NextResponse.json({ items });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to fetch knowledge' }, { status: 500 });
  }
}
