import type { AuthToken } from '@/lib/types';
import { readFileSync, lstatSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export type MilkcatRole = 'user' | 'admin';

/**
 * Operational bootstrap identities are stored outside the public Git checkout.
 * Only the Dashboard's own, owner-only regular file can contribute identities.
 * Existing environment-based administrator entries remain authoritative too.
 */
function privateAdminIdentities(): string[] {
  const file = join(homedir(), '.config', 'milkcat', 'admin-identities');
  try {
    const stat = lstatSync(file);
    const uid = process.getuid?.();
    if (!stat.isFile() || stat.isSymbolicLink() || uid === undefined ||
        stat.uid !== uid || (stat.mode & 0o077) !== 0) {
      console.error('Milkcat admin identities: private file ownership or permissions rejected');
      return [];
    }
    return readFileSync(file, 'utf8').split(/[\r\n,]+/);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
      console.error('Milkcat admin identities: private file could not be read');
    }
    return [];
  }
}

function adminIdentities(): Set<string> {
  return new Set(
    [...String(process.env.MILKCAT_ADMIN_IDENTITIES || '').split(','), ...privateAdminIdentities()]
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean)
  );
}

export function identityKeys(identity: Pick<AuthToken, 'provider' | 'subject' | 'username'>): string[] {
  const provider = String(identity.provider || '').trim().toLowerCase();
  const subject = String(identity.subject || '').trim().toLowerCase();
  const username = String(identity.username || '').trim().toLowerCase();
  const keys: string[] = [];

  if (provider && subject) keys.push(`${provider}:${subject}`);
  if (provider && username) keys.push(`${provider}:username:${username}`);

  return keys;
}

export function roleForIdentity(identity: Pick<AuthToken, 'provider' | 'subject' | 'username'>): MilkcatRole {
  const allowlist = adminIdentities();
  if (allowlist.size > 0 && identityKeys(identity).some((key) => allowlist.has(key))) return 'admin';
  return 'user';
}

export function isMilkcatAdmin(identity: Pick<AuthToken, 'provider' | 'subject' | 'username'>): boolean {
  return roleForIdentity(identity) === 'admin';
}
