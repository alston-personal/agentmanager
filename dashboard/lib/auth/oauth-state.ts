import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const ROOT = path.join(AGENT_DATA_ROOT, 'auth', 'oauth-states');
const TTL_MS = 10 * 60 * 1000;

type OAuthStateRecord = {
  schema: 'agentos.oauth-state/v1';
  state: string;
  returnTo: string;
  createdAt: string;
  expiresAt: string;
};

function ensureRoot() {
  fs.mkdirSync(ROOT, { recursive: true, mode: 0o700 });
}

function fileFor(state: string) {
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(state)) throw new Error('invalid oauth state');
  return path.join(ROOT, state + '.json');
}

function cleanupExpired() {
  ensureRoot();
  const now = Date.now();
  for (const name of fs.readdirSync(ROOT)) {
    if (!name.endsWith('.json')) continue;
    const file = path.join(ROOT, name);
    try {
      const row = JSON.parse(fs.readFileSync(file, 'utf8')) as OAuthStateRecord;
      if (Date.parse(row.expiresAt) <= now) fs.unlinkSync(file);
    } catch {
      try { fs.unlinkSync(file); } catch {}
    }
  }
}

export function createOAuthState(returnTo: string) {
  cleanupExpired();
  const state = randomBytes(32).toString('base64url');
  const now = new Date();
  const record: OAuthStateRecord = {
    schema: 'agentos.oauth-state/v1',
    state,
    returnTo,
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + TTL_MS).toISOString(),
  };
  fs.writeFileSync(fileFor(state), JSON.stringify(record) + '\n', { encoding: 'utf8', mode: 0o600 });
  return record;
}

export function consumeOAuthState(state: string): OAuthStateRecord | null {
  cleanupExpired();
  let record: OAuthStateRecord;
  try {
    record = JSON.parse(fs.readFileSync(fileFor(state), 'utf8')) as OAuthStateRecord;
  } catch {
    return null;
  }
  try { fs.unlinkSync(fileFor(state)); } catch {}
  if (Date.parse(record.expiresAt) <= Date.now()) return null;
  return record;
}
