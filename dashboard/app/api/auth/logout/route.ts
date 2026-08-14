import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://studio.milkcat.org';
  const requestedReturnTo = new URL(request.url).searchParams.get('returnTo') || '/';
  const returnTo = requestedReturnTo.startsWith('/') && !requestedReturnTo.startsWith('//') ? requestedReturnTo : '/';
  const response = NextResponse.redirect(new URL(returnTo, siteUrl));
  
  // Clear cookie across the entire domain
  response.cookies.set({
    name: 'auth_token',
    value: '',
    httpOnly: true,
    secure: true,
    domain: '.milkcat.org',
    path: '/',
    maxAge: 0, // Expire immediately
  });

  return response;
}
