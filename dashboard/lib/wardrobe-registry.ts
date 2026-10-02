import fs from 'node:fs';
import path from 'node:path';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

export const GARMENT_ROOT = path.join(
  AGENT_DATA_ROOT,
  'projects',
  'dressup-simulator',
  'garments'
);

export const ACTIVE_GARMENT_DIRS = ['seeded', 'imported'] as const;

export type CanonicalGarmentRecord = {
  garmentId?: string;
  garment_id?: string;
  characterId?: string;
  character_id?: string;
  name?: string;
  retailer?: string;
  brand?: string | null;
  sku?: string | null;
  variant?: string | null;
  category?: string | null;
  kind?: string | null;
  slot?: string;
  layer?: string;
  price?: number | string | null;
  priceTwd?: number | null;
  currency?: string | null;
  thumbnailUrl?: string | null;
  source?: {
    canonicalUrl?: string | null;
    submittedUrl?: string | null;
    productUrl?: string | null;
    product_url?: string | null;
    imageUrl?: string | null;
    officialVisualUrl?: string | null;
    extractedAt?: string | null;
  };
  official_visuals?: Array<{ url?: string | null }>;
  acquisition?: {
    state?: string;
    owned?: boolean;
    worn?: boolean;
  };
  tryOn?: {
    state?: string;
    status?: string;
    asset?: string | null;
  };
};

function safeReadJson(file: string): CanonicalGarmentRecord | null {
  try {
    const value = JSON.parse(fs.readFileSync(file, 'utf8'));
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as CanonicalGarmentRecord
      : null;
  } catch {
    return null;
  }
}

export function listActiveGarmentRecords(characterId?: string): CanonicalGarmentRecord[] {
  const byId = new Map<string, CanonicalGarmentRecord>();

  // Seeded is the stable baseline; imported is applied second so an explicitly
  // re-ingested canonical record may replace the seeded copy for the same id.
  for (const dirName of ACTIVE_GARMENT_DIRS) {
    const dir = path.join(GARMENT_ROOT, dirName);
    if (!fs.existsSync(dir)) continue;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isFile() || !entry.name.endsWith('.json')) continue;
      const row = safeReadJson(path.join(dir, entry.name));
      if (!row) continue;
      const id = String(row.garmentId || row.garment_id || '').trim();
      if (!id) continue;
      const rowCharacterId = String(row.characterId || row.character_id || '').trim();
      if (characterId && rowCharacterId && rowCharacterId !== characterId) continue;
      byId.set(id, row);
    }
  }

  return [...byId.values()];
}

export function findActiveGarment(garmentId: string): CanonicalGarmentRecord | null {
  const id = String(garmentId || '').trim();
  if (!id) return null;
  return listActiveGarmentRecords().find(
    (row) => String(row.garmentId || row.garment_id || '') === id
  ) || null;
}

export function garmentSourceImage(row: CanonicalGarmentRecord): string | null {
  const visual =
    row.source?.imageUrl ||
    row.source?.officialVisualUrl ||
    row.official_visuals?.find((item) => item?.url)?.url ||
    row.thumbnailUrl ||
    null;
  return visual ? String(visual) : null;
}

export function garmentCanonicalUrl(row: CanonicalGarmentRecord): string {
  return String(
    row.source?.canonicalUrl ||
    row.source?.submittedUrl ||
    row.source?.productUrl ||
    row.source?.product_url ||
    ''
  );
}
