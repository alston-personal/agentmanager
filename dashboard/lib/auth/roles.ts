import type { AuthToken } from '@/lib/types';

export type MilkcatRole = 'user' | 'admin';

function adminIdentities(): Set<string> {
  return new Set(
    String(process.env.MILKCAT_ADMIN_IDENTITIES || '')
      .split(',')
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
