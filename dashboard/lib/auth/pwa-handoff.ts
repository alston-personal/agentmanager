import fs from 'node:fs';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const ROOT = path.join(AGENT_DATA_ROOT, 'auth', 'pwa-handoffs');
const TTL_MS = 10 * 60 * 1000;

export type PwaHandoffRecord = {
  schema: 'agentos.auth-pwa-handoff/v1';
  id: string;
  createdAt: string;
  expiresAt: string;
  status: 'pending' | 'ready';
  authToken: string | null;
};

function ensureRoot() {
  fs.mkdirSync(ROOT, { recursive: true, mode: 0o700 });
}

function fileFor(id: string) {
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(id)) throw new Error('invalid handoff id');
  return path.join(ROOT, id + '.json');
}

function atomicWrite(file: string, payload: PwaHandoffRecord) {
  ensureRoot();
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(payload) + '\n', { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, file);
}

function cleanupExpired() {
  ensureRoot();
  const now = Date.now();
  for (const name of fs.readdirSync(ROOT)) {
    if (!name.endsWith('.json')) continue;
    const file = path.join(ROOT, name);
    try {
      const row = JSON.parse(fs.readFileSync(file, 'utf8')) as PwaHandoffRecord;
      if (Date.parse(row.expiresAt) <= now) fs.unlinkSync(file);
    } catch {
      try { fs.unlinkSync(file); } catch {}
    }
  }
}

export function createPwaHandoff() {
  cleanupExpired();
  const id = randomBytes(32).toString('base64url');
  const now = new Date();
  const record: PwaHandoffRecord = {
    schema: 'agentos.auth-pwa-handoff/v1',
    id,
    createdAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + TTL_MS).toISOString(),
    status: 'pending',
    authToken: null,
  };
  atomicWrite(fileFor(id), record);
  return record;
}

export function completePwaHandoff(id: string, authToken: string) {
  const record = readPwaHandoff(id);
  if (!record) throw new Error('handoff not found or expired');
  record.status = 'ready';
  record.authToken = authToken;
  atomicWrite(fileFor(id), record);
  return record;
}

export function readPwaHandoff(id: string): PwaHandoffRecord | null {
  cleanupExpired();
  try {
    const record = JSON.parse(fs.readFileSync(fileFor(id), 'utf8')) as PwaHandoffRecord;
    if (Date.parse(record.expiresAt) <= Date.now()) {
      fs.unlinkSync(fileFor(id));
      return null;
    }
    return record;
  } catch {
    return null;
  }
}

export function consumePwaHandoff(id: string): PwaHandoffRecord | null {
  const record = readPwaHandoff(id);
  if (!record || record.status !== 'ready' || !record.authToken) return null;
  try { fs.unlinkSync(fileFor(id)); } catch {}
  return record;
}
