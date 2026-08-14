import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import fs from 'fs';
import path from 'path';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const REGISTRY_FILE = path.join(AGENT_DATA_ROOT, 'likes_registry.json');

function getLikedSlugs(username: string): string[] {
  try {
    if (fs.existsSync(REGISTRY_FILE)) {
      const data = JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf-8'));
      return data[username] || [];
    }
  } catch (e) {
    console.error('Failed to read likes registry:', e);
  }
  return [];
}

export async function GET(request: NextRequest) {
  const token = request.cookies.get('auth_token')?.value;

  const providers = {
    github: !!process.env.GITHUB_CLIENT_ID,
    facebook: !!process.env.FACEBOOK_CLIENT_ID,
    line: !!process.env.LINE_CLIENT_ID,
    google: !!process.env.GOOGLE_CLIENT_ID,
  };

  if (!token) {
    return NextResponse.json({ loggedIn: false, providers });
  }

  const user = verifyToken(token);

  if (!user || !user.username) {
    return NextResponse.json({ loggedIn: false, providers });
  }

  const likedSlugs = getLikedSlugs(user.username);

  return NextResponse.json({
    loggedIn: true,
    username: user.username,
    provider: user.provider,
    subject: user.subject,
    likedProjects: likedSlugs,
    providers,
  });
}
