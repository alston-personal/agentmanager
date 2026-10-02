import fs from 'node:fs';
import path from 'node:path';
import { NextRequest, NextResponse } from 'next/server';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

const GARMENT_DIR = path.join(
  AGENT_DATA_ROOT,
  'projects',
  'dressup-simulator',
  'garments',
  'imported'
);

const DEFAULT_CHARACTER_ID = 'sunlake-milkcat-ai-001';
const CHARACTER_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

type PublicGarment = {
  garmentId: string;
  characterId: string;
  name: string;
  retailer: string;
  brand: string | null;
  sku: string | null;
  variant: string | null;
  category: string | null;
  slot: string;
  price: number | null;
  currency: string | null;
  source: {
    canonicalUrl: string;
    imageUrl: string | null;
    extractedAt: string;
  };
  acquisition: {
    state: string;
    owned: boolean;
    worn: boolean;
  };
  tryOn: {
    state: string;
    asset: string | null;
  };
};

function readCatalog(characterId: string): PublicGarment[] {
  if (!fs.existsSync(GARMENT_DIR)) return [];
  const rows: PublicGarment[] = [];

  for (const name of fs.readdirSync(GARMENT_DIR)) {
    if (!name.endsWith('.json')) continue;
    try {
      const raw = JSON.parse(fs.readFileSync(path.join(GARMENT_DIR, name), 'utf8'));
      if (raw?.characterId !== characterId || !raw?.garmentId || !raw?.name) continue;
      rows.push({
        garmentId: String(raw.garmentId),
        characterId,
        name: String(raw.name),
        retailer: String(raw.retailer || raw.brand || 'Retail'),
        brand: raw.brand ? String(raw.brand) : null,
        sku: raw.sku ? String(raw.sku) : null,
        variant: raw.variant ? String(raw.variant) : null,
        category: raw.category ? String(raw.category) : null,
        slot: (() => { const rawSlot = String(raw.layer || raw.slot || 'accessories'); const productName = String(raw.name || ''); if ((rawSlot === 'accessories' || rawSlot === 'accessory_1') && /內衣|胸罩|小可愛|細肩|bra|bralette|camisole|lingerie/i.test(productName)) return 'upper_inner'; return rawSlot; })(),
        price: typeof raw.price === 'number' ? raw.price : null,
        currency: raw.currency ? String(raw.currency) : null,
        source: {
          canonicalUrl: String(raw?.source?.canonicalUrl || raw?.source?.submittedUrl || ''),
          imageUrl: raw?.source?.imageUrl ? String(raw.source.imageUrl) : null,
          extractedAt: String(raw?.source?.extractedAt || ''),
        },
        acquisition: {
          state: String(raw?.acquisition?.state || 'want_to_try'),
          owned: Boolean(raw?.acquisition?.owned),
          worn: Boolean(raw?.acquisition?.worn),
        },
        tryOn: {
          state: String(raw?.tryOn?.state || 'ready_for_tryon'),
          asset: raw?.tryOn?.asset ? String(raw.tryOn.asset) : null,
        },
      });
    } catch {
      // One malformed imported record must not break the public wardrobe.
    }
  }

  return rows.sort((a, b) => b.source.extractedAt.localeCompare(a.source.extractedAt));
}

export async function GET(request: NextRequest) {
  const characterId =
    request.nextUrl.searchParams.get('characterId')?.trim() || DEFAULT_CHARACTER_ID;
  if (!CHARACTER_ID_RE.test(characterId)) {
    return NextResponse.json({ error: 'Invalid characterId' }, { status: 400 });
  }

  return NextResponse.json(
    {
      schema: 'agentos.public-wardrobe-catalog/v1',
      characterId,
      garments: readCatalog(characterId),
    },
    {
      headers: {
        'cache-control': 'public, max-age=30, stale-while-revalidate=120',
      },
    }
  );
}
