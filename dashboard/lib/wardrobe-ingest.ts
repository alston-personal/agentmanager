import dns from 'node:dns/promises';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { normalizeWardrobeLayer } from '@/lib/wardrobe-layers';

export type IntakeState = 'pending_metadata' | 'fetching' | 'ready_for_tryon' | 'needs_review';

export type ResolvedProduct = {
  garmentId: string;
  name: string;
  brand: string | null;
  sku: string | null;
  variant: string | null;
  category: string | null;
  slot: 'upper_body' | 'lower_body' | 'dress' | 'outerwear' | 'shoes' | 'bag' | 'accessories';
  price: number | null;
  currency: string | null;
  imageUrl: string | null;
  canonicalUrl: string;
  retailer: string;
  extractedAt: string;
};

const MAX_HTML_BYTES = 1500000;
const FETCH_TIMEOUT_MS = 8000;
const MAX_REDIRECTS = 4;

function isPrivateIpv4(ip: string): boolean {
  const p = ip.split('.').map(Number);
  if (p.length !== 4 || p.some((n) => Number.isNaN(n))) return true;
  return p[0] === 10 || p[0] === 127 || p[0] === 0 ||
    (p[0] === 169 && p[1] === 254) ||
    (p[0] === 172 && p[1] >= 16 && p[1] <= 31) ||
    (p[0] === 192 && p[1] === 168) ||
    (p[0] === 100 && p[1] >= 64 && p[1] <= 127);
}

function isPrivateIp(ip: string): boolean {
  if (net.isIPv4(ip)) return isPrivateIpv4(ip);
  if (!net.isIPv6(ip)) return true;
  const v = ip.toLowerCase();
  return v === '::1' || v === '::' || v.startsWith('fc') || v.startsWith('fd') ||
    v.startsWith('fe8') || v.startsWith('fe9') || v.startsWith('fea') || v.startsWith('feb');
}

async function assertPublicHost(url: URL) {
  if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error('unsupported_protocol');
  if (!url.hostname || url.hostname === 'localhost') throw new Error('unsafe_host');
  const rows = await dns.lookup(url.hostname, { all: true, verbatim: true });
  if (!rows.length || rows.some((row) => isPrivateIp(row.address))) throw new Error('unsafe_host');
}

async function safeFetchHtml(initialUrl: URL): Promise<{ html: string; finalUrl: URL }> {
  let current = new URL(initialUrl);
  for (let redirect = 0; redirect <= MAX_REDIRECTS; redirect += 1) {
    await assertPublicHost(current);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetch(current, {
        redirect: 'manual',
        signal: controller.signal,
        headers: {
          'user-agent': 'MilkcatWardrobeBot/1.0 (+https://studio.milkcat.org/)',
          accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.5',
        },
        cache: 'no-store',
      });
    } finally {
      clearTimeout(timer);
    }
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location');
      if (!location || redirect === MAX_REDIRECTS) throw new Error('redirect_failed');
      current = new URL(location, current);
      continue;
    }
    if (!response.ok) throw new Error('http_' + response.status);
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/html') && !contentType.includes('application/xhtml+xml')) throw new Error('not_html');
    const lengthHeader = Number(response.headers.get('content-length') || '0');
    if (lengthHeader > MAX_HTML_BYTES) throw new Error('html_too_large');
    const html = await response.text();
    if (Buffer.byteLength(html, 'utf8') > MAX_HTML_BYTES) throw new Error('html_too_large');
    return { html, finalUrl: current };
  }
  throw new Error('redirect_failed');
}

function decodeHtml(value: string | null): string | null {
  if (!value) return null;
  return value.replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim();
}

function meta(html: string, key: string): string | null {
  const escaped = key.replace(/[.*+?^\${}()|[\]\\]/g, '\\$&');
  const patterns = [
    new RegExp('<meta[^>]+(?:property|name)=[\\"\\\']' + escaped + '[\\"\\\'][^>]+content=[\\"\\\']([^\\"\\\']+)[\\"\\\'][^>]*>', 'i'),
    new RegExp('<meta[^>]+content=[\\"\\\']([^\\"\\\']+)[\\"\\\'][^>]+(?:property|name)=[\\"\\\']' + escaped + '[\\"\\\'][^>]*>', 'i'),
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match?.[1]) return decodeHtml(match[1]);
  }
  return null;
}

function titleTag(html: string): string | null {
  const match = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return decodeHtml(match?.[1] || null);
}

function visibleText(html: string): string {
  return decodeHtml(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
  ) || '';
}

function netFallback(html: string) {
  const text = visibleText(html);
  const sku = text.match(/商品編號\s*[:：]\s*([A-Za-z0-9-]+)/)?.[1] || null;
  const priceRaw = text.match(/NT\$?\s*([0-9][0-9,]*)/)?.[1] || null;
  const price = priceRaw ? Number(priceRaw.replace(/,/g, '')) : null;
  return {
    sku,
    price: Number.isFinite(price) && price && price > 0 ? price : null,
    currency: priceRaw ? 'TWD' : null,
  };
}

function jsonLdObjects(html: string): unknown[] {
  const out: unknown[] = [];
  const re = /<script[^>]+type=[\\"\\\']application\/ld\+json[\\"\\\'][^>]*>([\s\S]*?)<\/script>/gi;
  for (const match of html.matchAll(re)) {
    try {
      const parsed = JSON.parse(match[1].trim());
      if (Array.isArray(parsed)) out.push(...parsed);
      else out.push(parsed);
    } catch {}
  }
  return out;
}

function flattenJsonLd(value: unknown): Record<string, unknown>[] {
  const result: Record<string, unknown>[] = [];
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { node.forEach(visit); return; }
    const obj = node as Record<string, unknown>;
    result.push(obj);
    if (obj['@graph']) visit(obj['@graph']);
    if (obj.itemListElement) visit(obj.itemListElement);
  };
  visit(value);
  return result;
}

function productJsonLd(html: string): Record<string, unknown> | null {
  for (const root of jsonLdObjects(html)) {
    for (const obj of flattenJsonLd(root)) {
      const type = obj['@type'];
      const types = Array.isArray(type) ? type.map(String) : [String(type || '')];
      if (types.some((t) => t.toLowerCase() === 'product')) return obj;
    }
  }
  return null;
}

function firstString(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = firstString(item);
      if (found) return found;
    }
  }
  return null;
}

function productImage(product: Record<string, unknown> | null): string | null {
  if (!product) return null;
  const image = product.image;
  if (typeof image === 'string') return image;
  if (Array.isArray(image)) return firstString(image);
  if (image && typeof image === 'object') return firstString((image as Record<string, unknown>).url);
  return null;
}

function productOffer(product: Record<string, unknown> | null) {
  if (!product) return { price: null as number | null, currency: null as string | null };
  const raw = product.offers;
  const offers = Array.isArray(raw) ? raw : raw && typeof raw === 'object' ? [raw] : [];
  for (const offer of offers) {
    if (!offer || typeof offer !== 'object') continue;
    const row = offer as Record<string, unknown>;
    const priceValue = row.price ?? row.lowPrice ?? row.highPrice;
    const n = typeof priceValue === 'number' ? priceValue : Number(String(priceValue || '').replace(/[^0-9.]/g, ''));
    return { price: Number.isFinite(n) && n > 0 ? n : null, currency: firstString(row.priceCurrency) };
  }
  return { price: null as number | null, currency: null as string | null };
}

function brandName(product: Record<string, unknown> | null): string | null {
  if (!product) return null;
  const brand = product.brand;
  if (typeof brand === 'string') return brand.trim() || null;
  if (brand && typeof brand === 'object') return firstString((brand as Record<string, unknown>).name);
  return null;
}

function classifySlot(text: string): ResolvedProduct['slot'] {
  const v = text.toLowerCase();
  if (/dress|洋裝|連身|連衣/.test(v)) return 'dress';
  if (/coat|jacket|blazer|cardigan|外套|夾克|西裝|罩衫/.test(v)) return 'outerwear';
  if (/shoe|sneaker|boot|loafer|sandal|鞋|靴|涼鞋|樂福/.test(v)) return 'shoes';
  if (/bag|tote|pouch|wallet|包|皮夾|錢包/.test(v)) return 'bag';
  if (/pant|trouser|jean|skirt|short|legging|褲|裙/.test(v)) return 'lower_body';
  if (/shirt|tee|top|blouse|sweater|knit|hoodie|上衣|襯衫|針織|毛衣|帽t|背心/.test(v)) return 'upper_body';
  return 'accessories';
}

function retailerName(hostname: string): string {
  return hostname.replace(/^www\./, '').split('.')[0].toUpperCase();
}

function stableGarmentId(characterId: string, canonicalUrl: string): string {
  const hash = createHash('sha256').update(characterId + '\n' + canonicalUrl).digest('hex').slice(0, 16);
  return 'retail-' + hash;
}

export async function resolveRetailProduct(sourceUrl: URL, characterId: string): Promise<ResolvedProduct> {
  const { html, finalUrl } = await safeFetchHtml(sourceUrl);
  const product = productJsonLd(html);
  const name = firstString(product?.name) || meta(html, 'og:title') || meta(html, 'twitter:title') || titleTag(html);
  if (!name) throw new Error('product_name_missing');
  const canonical = meta(html, 'og:url') || firstString(product?.url) || finalUrl.toString();
  const canonicalUrl = new URL(canonical, finalUrl).toString();
  const category = firstString(product?.category);
  const offer = productOffer(product);
  const fallback = /(^|\.)net-fashion\.net$/i.test(finalUrl.hostname) ? netFallback(html) : { sku: null, price: null, currency: null };
  const imageUrl = productImage(product) || meta(html, 'og:image') || meta(html, 'twitter:image');
  const brand = brandName(product);
  return {
    garmentId: stableGarmentId(characterId, canonicalUrl),
    name,
    brand,
    sku: firstString(product?.sku) || firstString(product?.productID) || firstString(product?.mpn) || fallback.sku,
    variant: firstString(product?.color),
    category,
    slot: classifySlot([name, category, firstString(product?.description)].filter(Boolean).join(' ')),
    price: offer.price ?? fallback.price,
    currency: offer.currency || fallback.currency,
    imageUrl: imageUrl ? new URL(imageUrl, finalUrl).toString() : null,
    canonicalUrl,
    retailer: brand || retailerName(finalUrl.hostname),
    extractedAt: new Date().toISOString(),
  };
}

export function writeCanonicalGarment(
  agentDataRoot: string,
  characterId: string,
  product: ResolvedProduct,
  sourceUrl: string,
  intakeId: string,
  note: string | null,
) {
  const dir = path.join(agentDataRoot, 'projects', 'dressup-simulator', 'garments', 'imported');
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  const destination = path.join(dir, product.garmentId + '.json');
  const payload = {
    schema: 'agentos.garment/v1',
    garmentId: product.garmentId,
    characterId,
    name: product.name,
    retailer: product.retailer,
    brand: product.brand,
    sku: product.sku,
    variant: product.variant,
    category: product.category,
    slot: product.slot,
    layer: normalizeWardrobeLayer(product.slot),
    price: product.price,
    currency: product.currency,
    source: {
      submittedUrl: sourceUrl,
      canonicalUrl: product.canonicalUrl,
      imageUrl: product.imageUrl,
      extractedAt: product.extractedAt,
      intakeId,
      note,
    },
    acquisition: { state: 'want_to_try', owned: false, worn: false },
    tryOn: { state: 'ready_for_tryon', asset: null },
  };
  const tmp = destination + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, destination);
  return payload;
}
