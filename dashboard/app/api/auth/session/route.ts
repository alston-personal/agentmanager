import { NextRequest, NextResponse } from 'next/server';
import { verifyToken } from '@/lib/auth';
import { authCookieName, resolveAuthSite } from '@/lib/auth/site';
import { roleForIdentity } from '@/lib/auth/roles';
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
  const site = resolveAuthSite(request);
  if (!site) return NextResponse.json({ loggedIn: false, error: 'invalid_site' }, { status: 400 });
  // AgentOS may only read AgentOS-scoped sessions. Studio retains its
  // existing auth_token cookie for backward-compatible Studio sign-ins.
  const authTokens = request.cookies.getAll(authCookieName(site.site))
    .map((cookie) => cookie.value).filter(Boolean);

  const providers = {
    github: !!process.env.GITHUB_CLIENT_ID,
    facebook: !!process.env.FACEBOOK_CLIENT_ID,
    line: !!process.env.LINE_CLIENT_ID,
    google: !!process.env.GOOGLE_CLIENT_ID,
  };

  if (!authTokens.length) {
    return NextResponse.json({ loggedIn: false, providers });
  }

  const user = authTokens
    .map((token) => verifyToken(token))
    .find((candidate) => candidate?.username) || null;

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
    role: roleForIdentity(user),
    providers,
  });
}
