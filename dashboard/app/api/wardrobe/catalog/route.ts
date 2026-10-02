import { NextRequest, NextResponse } from 'next/server';
import { listActiveGarmentRecords, garmentCanonicalUrl, garmentSourceImage } from '@/lib/wardrobe-registry';

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

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  const text = String(value ?? '').replace(/[^0-9.]/g, '');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

function readCatalog(characterId: string): PublicGarment[] {
  return listActiveGarmentRecords(characterId)
    .flatMap((raw) => {
      const garmentId = String(raw.garmentId || raw.garment_id || '').trim();
      if (!garmentId || !raw.name) return [];
      return [{
        garmentId,
        characterId,
        name: String(raw.name),
        retailer: String(raw.retailer || raw.brand || 'Retail'),
        brand: raw.brand ? String(raw.brand) : null,
        sku: raw.sku ? String(raw.sku) : null,
        variant: raw.variant ? String(raw.variant) : null,
        category: raw.category ? String(raw.category) : raw.kind ? String(raw.kind) : null,
        slot: (() => {
          const rawSlot = String(raw.layer || raw.slot || 'accessories');
          const productName = String(raw.name || '');
          if ((rawSlot === 'accessories' || rawSlot === 'accessory_1') && /內衣|胸罩|小可愛|細肩|bra|bralette|camisole|lingerie/i.test(productName)) return 'upper_inner';
          return rawSlot;
        })(),
        price: toNumber(raw.priceTwd ?? raw.price),
        currency: raw.currency ? String(raw.currency) : (raw.priceTwd ? 'TWD' : null),
        source: {
          canonicalUrl: garmentCanonicalUrl(raw),
          imageUrl: garmentSourceImage(raw),
          extractedAt: String(raw?.source?.extractedAt || ''),
        },
        acquisition: {
          state: String(raw?.acquisition?.state || 'want_to_try'),
          owned: Boolean(raw?.acquisition?.owned),
          worn: Boolean(raw?.acquisition?.worn),
        },
        tryOn: {
          state: String(raw?.tryOn?.state || raw?.tryOn?.status || 'ready_for_tryon'),
          asset: raw?.tryOn?.asset ? String(raw.tryOn.asset) : null,
        },
      }];
    })
    .sort((a, b) => b.source.extractedAt.localeCompare(a.source.extractedAt));
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
