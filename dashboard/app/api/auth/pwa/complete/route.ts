import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { completePwaHandoff } from '@/lib/auth/pwa-handoff';

export async function GET(request: NextRequest) {
  const handoff = new URL(request.url).searchParams.get('handoff') || '';
  const token = request.cookies.get('auth_token')?.value || '';
  if (!handoff || !token || !verifyToken(token)) {
    return new NextResponse('Login not completed. Return to the Mio wardrobe app and try again.', {
      status: 401,
      headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  try {
    completePwaHandoff(handoff, token);
  } catch {
    return new NextResponse('Login handoff expired. Return to the Mio wardrobe app and try again.', {
      status: 410,
      headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
    });
  }
  return new NextResponse('登入完成。請回到主畫面的「澪的衣櫃」App，系統會自動接回登入狀態。', {
    status: 200,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  });
}
