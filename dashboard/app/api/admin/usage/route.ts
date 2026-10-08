import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { isMilkcatAdmin } from '@/lib/auth/roles';
import { getFengshuiAdminSummary } from '@/lib/fengshui-admin';

export async function GET(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;
  const identity = token ? verifyToken(token) : null;

  if (!identity) return NextResponse.json({ error: 'authentication_required' }, { status: 401 });
  if (!isMilkcatAdmin(identity)) return NextResponse.json({ error: 'admin_required' }, { status: 403 });

  const days = Number(new URL(request.url).searchParams.get('days') || '30');
  try {
    const summary = await getFengshuiAdminSummary(days);
    return NextResponse.json({
      viewer: {
        username: identity.username,
        provider: identity.provider,
        subject: identity.subject,
        role: 'admin',
      },
      services: { fengshui: summary },
    });
  } catch (error) {
    console.error('Admin usage summary failed:', error);
    return NextResponse.json({ error: 'admin_usage_unavailable' }, { status: 503 });
  }
}
