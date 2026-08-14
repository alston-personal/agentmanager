import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
import { verifyToken } from '@/lib/auth';

const LIKES_FILE_PATH = path.join(AGENT_DATA_ROOT, 'likes.json');
const REGISTRY_FILE_PATH = path.join(AGENT_DATA_ROOT, 'likes_registry.json');

// Helper to read likes file
function readLikes(): Record<string, number> {
  try {
    if (fs.existsSync(LIKES_FILE_PATH)) {
      const content = fs.readFileSync(LIKES_FILE_PATH, 'utf-8');
      return JSON.parse(content);
    }
  } catch (error) {
    console.error('Failed to read likes file:', error);
  }
  return {
    "leopardcat-tarot": 0,
    "youtube-ai-manager": 0,
    "if-tv-station": 0,
    "ai-market-research-os": 0,
    "metashield-protocol": 0,
    "hanzi-gene-database": 0
  };
}

// Helper to write likes file
function writeLikes(data: Record<string, number>) {
  try {
    fs.writeFileSync(LIKES_FILE_PATH, JSON.stringify(data, null, 2), 'utf-8');
  } catch (error) {
    console.error('Failed to write likes file:', error);
  }
}

// Helper to read likes registry
function readRegistry(): Record<string, string[]> {
  try {
    if (fs.existsSync(REGISTRY_FILE_PATH)) {
      const content = fs.readFileSync(REGISTRY_FILE_PATH, 'utf-8');
      return JSON.parse(content);
    }
  } catch (error) {
    console.error('Failed to read registry file:', error);
  }
  return {};
}

// Helper to write likes registry
function writeRegistry(data: Record<string, string[]>) {
  try {
    fs.writeFileSync(REGISTRY_FILE_PATH, JSON.stringify(data, null, 2), 'utf-8');
  } catch (error) {
    console.error('Failed to write registry file:', error);
  }
}

export async function GET() {
  const likes = readLikes();
  return NextResponse.json({ likes });
}

export async function POST(req: NextRequest) {
  try {
    // 1. Verify authentication
    const token = req.cookies.get('auth_token')?.value;
    if (!token) {
      return NextResponse.json({ error: 'Unauthorized: Login required to vote' }, { status: 401 });
    }

    const user = verifyToken(token);
    if (!user || !user.username) {
      return NextResponse.json({ error: 'Unauthorized: Invalid session token' }, { status: 401 });
    }

    const username = user.username;

    // 2. Validate slug
    const { slug } = await req.json();
    if (!slug || typeof slug !== 'string' || !/^[a-z0-9_-]+$/.test(slug)) {
      return NextResponse.json({ error: 'Invalid slug' }, { status: 400 });
    }

    // 3. Check registry to prevent double voting
    const registry = readRegistry();
    const userLikes = registry[username] || [];

    if (userLikes.includes(slug)) {
      return NextResponse.json({ error: 'You have already liked this project' }, { status: 400 });
    }

    // 4. Update registry
    userLikes.push(slug);
    registry[username] = userLikes;
    writeRegistry(registry);

    // 5. Update likes count
    const likes = readLikes();
    likes[slug] = (likes[slug] || 0) + 1;
    writeLikes(likes);

    return NextResponse.json({ success: true, likes: likes[slug] });
  } catch (error) {
    console.error('Failed to update likes:', error);
    return NextResponse.json({ error: 'Failed to update likes' }, { status: 500 });
  }
}
