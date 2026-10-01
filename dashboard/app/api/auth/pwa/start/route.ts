import { NextResponse } from 'next/server';
import { createPwaHandoff } from '@/lib/auth/pwa-handoff';

export async function POST() {
  const record = createPwaHandoff();
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://studio.milkcat.org';
  const returnTo = '/dashboard/api/auth/pwa/complete?handoff=' + encodeURIComponent(record.id);
  const signInUrl = siteUrl + '/dashboard/api/auth/signin/google?returnTo=' + encodeURIComponent(returnTo);
  return NextResponse.json({ handoffId: record.id, expiresAt: record.expiresAt, signInUrl });
}
