import { NextResponse } from 'next/server';
import { getKnowledgeItem } from '@/lib/knowledge';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ slug: string[] }> }
) {
  const resolvedParams = await params;
  const slug = resolvedParams.slug.join('/');
  
  try {
    const item = getKnowledgeItem(slug);
    if (!item) return NextResponse.json({ error: 'Not found' }, { status: 404 });
    return NextResponse.json({ item });
  } catch (error) {
    return NextResponse.json({ error: 'Failed' }, { status: 500 });
  }
}
