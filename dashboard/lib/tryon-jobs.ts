import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { AGENT_DATA_ROOT } from '@/lib/data-root';
import { normalizeWardrobeLayer } from './wardrobe-layers.mjs';

export const TRYON_JOB_SCHEMA = 'agentos.tryon-render-job/v1' as const;
export const DEFAULT_CHARACTER_ID = 'sunlake-milkcat-ai-001';
export const DEFAULT_CHARACTER_VERSION = 'mio-body-v1';
export const DEFAULT_BASE_BODY_ASSET = '/personas/mio/mio-base-v2.webp';

export const LAYER_ORDER = [
  'upper_inner',
  'upper_main',
  'onepiece',
  'lower_main',
  'socks',
  'shoes',
  'upper_outer',
  'bag',
  'accessory_1',
  'accessory_2',
] as const;

export const ALLOWED_LAYERS = new Set<string>(LAYER_ORDER);

const ROOT = path.join(AGENT_DATA_ROOT, 'projects', 'dressup-simulator');
const JOB_DIR = path.join(ROOT, 'render_jobs', 'runtime');
const CURRENT_DIR = path.join(ROOT, 'current_outfits');
const GARMENT_DIR = path.join(ROOT, 'garments');

export type TryOnStatus = 'queued' | 'rendering' | 'ready' | 'failed' | 'cancelled';

export type LayerItem = {
  garmentId: string;
  name: string;
  layer: string;
  sourceImageUrl: string | null;
};

export type TryOnJob = {
  schema: typeof TRYON_JOB_SCHEMA;
  jobId: string;
  characterId: string;
  characterVersion: string;
  view: 'front';
  pose: 'neutral_standing';
  status: TryOnStatus;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  failedAt: string | null;
  supersededBy: string | null;
  input: {
    baseBodyAsset: string;
    layerOrder: string[];
    selectedLayers: Record<string, LayerItem>;
  };
  output: {
    asset: string | null;
    previewAsset: string | null;
    width: number | null;
    height: number | null;
    provider?: string;
    providerOutputs?: unknown[];
    renderedLayers?: string[];
    pendingLayers?: string[];
    warnings?: Array<{ layer?: string; code: string; message?: string }>;
    cacheKey?: string | null;
  };
  error: null | { code: string; message: string };
};

type GarmentRecord = {
  garmentId?: string;
  garment_id?: string;
  name?: string;
  slot?: string;
  layer?: string;
  source?: {
    imageUrl?: string | null;
    officialVisualUrl?: string | null;
    canonicalUrl?: string | null;
    product_url?: string | null;
  };
  official_visuals?: Array<{ url?: string | null }>;
};

function safeMkdir(dir: string) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
}

function atomicWrite(file: string, payload: unknown) {
  safeMkdir(path.dirname(file));
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, file);
}

function safeReadJson<T>(file: string): T | null {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8')) as T;
  } catch {
    return null;
  }
}

function listGarmentFiles(): string[] {
  const out: string[] = [];
  if (!fs.existsSync(GARMENT_DIR)) return out;
  for (const entry of fs.readdirSync(GARMENT_DIR, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith('.json')) out.push(path.join(GARMENT_DIR, entry.name));
    if (entry.isDirectory()) {
      const sub = path.join(GARMENT_DIR, entry.name);
      for (const child of fs.readdirSync(sub, { withFileTypes: true })) {
        if (child.isFile() && child.name.endsWith('.json')) out.push(path.join(sub, child.name));
      }
    }
  }
  return out;
}

export function resolveGarment(garmentId: string): LayerItem | null {
  for (const file of listGarmentFiles()) {
    const row = safeReadJson<GarmentRecord>(file);
    if (!row) continue;
    const id = String(row.garmentId || row.garment_id || '');
    if (id !== garmentId) continue;
    const layer = normalizeWardrobeLayer(row.layer || row.slot || '');
    if (!ALLOWED_LAYERS.has(layer)) return null;
    const visual =
      row.source?.imageUrl ||
      row.source?.officialVisualUrl ||
      row.official_visuals?.find((x) => x?.url)?.url ||
      null;
    return {
      garmentId: id,
      name: String(row.name || id),
      layer,
      sourceImageUrl: visual ? String(visual) : null,
    };
  }
  return null;
}

export function normalizeSelectedLayers(input: unknown): Record<string, LayerItem> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new Error('selectedLayers must be an object');
  }
  const result: Record<string, LayerItem> = {};
  for (const [layer, raw] of Object.entries(input as Record<string, unknown>)) {
    if (!ALLOWED_LAYERS.has(layer)) throw new Error('invalid layer: ' + layer);
    const garmentId = typeof raw === 'string'
      ? raw
      : raw && typeof raw === 'object' && 'garmentId' in raw
        ? String((raw as Record<string, unknown>).garmentId || '')
        : '';
    if (!garmentId) throw new Error('garmentId missing for layer: ' + layer);
    const garment = resolveGarment(garmentId);
    if (!garment) throw new Error('unknown garment: ' + garmentId);
    if (garment.layer !== layer) {
      throw new Error('garment layer mismatch: ' + garmentId + ' -> ' + garment.layer + ', requested ' + layer);
    }
    result[layer] = garment;
  }
  return result;
}

export function makeJobId(characterId: string) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return characterId.replace(/[^A-Za-z0-9._-]/g, '-') + '-tryon-' + stamp + '-' + randomUUID().slice(0, 8);
}

export function jobPath(jobId: string) {
  if (!/^[A-Za-z0-9._-]{1,220}$/.test(jobId)) throw new Error('invalid jobId');
  return path.join(JOB_DIR, jobId + '.json');
}

export function readJob(jobId: string): TryOnJob | null {
  return safeReadJson<TryOnJob>(jobPath(jobId));
}

export function writeJob(job: TryOnJob) {
  atomicWrite(jobPath(job.jobId), job);
}

export function currentOutfitPath(characterId: string) {
  if (!/^[A-Za-z0-9._-]{1,128}$/.test(characterId)) throw new Error('invalid characterId');
  return path.join(CURRENT_DIR, characterId + '.json');
}

export function writeCurrentOutfit(characterId: string, job: TryOnJob) {
  atomicWrite(currentOutfitPath(characterId), {
    schema: 'milkcat.outfit-simulator/v3',
    characterId,
    updatedAt: new Date().toISOString(),
    items: LAYER_ORDER
      .filter((layer) => job.input.selectedLayers[layer])
      .map((layer) => ({
        layer,
        garmentId: job.input.selectedLayers[layer].garmentId,
      })),
    tryOn: {
      jobId: job.jobId,
      status: job.status,
      asset: job.output.asset,
      previewAsset: job.output.previewAsset,
      view: job.view,
    },
  });
}

export function readCurrentOutfit(characterId: string) {
  return safeReadJson<Record<string, unknown>>(currentOutfitPath(characterId));
}

export function supersedeOlderJobs(characterId: string, newerJobId: string) {
  if (!fs.existsSync(JOB_DIR)) return;
  for (const name of fs.readdirSync(JOB_DIR)) {
    if (!name.endsWith('.json')) continue;
    const file = path.join(JOB_DIR, name);
    const job = safeReadJson<TryOnJob>(file);
    if (!job || job.characterId !== characterId || job.jobId === newerJobId) continue;
    if (job.status !== 'queued' && job.status !== 'rendering') continue;
    job.status = 'cancelled';
    job.supersededBy = newerJobId;
    atomicWrite(file, job);
  }
}

export function createTryOnJob(args: {
  characterId: string;
  selectedLayers: Record<string, LayerItem>;
  baseBodyAsset?: string;
}): TryOnJob {
  const now = new Date().toISOString();
  const job: TryOnJob = {
    schema: TRYON_JOB_SCHEMA,
    jobId: makeJobId(args.characterId),
    characterId: args.characterId,
    characterVersion: DEFAULT_CHARACTER_VERSION,
    view: 'front',
    pose: 'neutral_standing',
    status: 'queued',
    requestedAt: now,
    startedAt: null,
    completedAt: null,
    failedAt: null,
    supersededBy: null,
    input: {
      baseBodyAsset: args.baseBodyAsset || DEFAULT_BASE_BODY_ASSET,
      layerOrder: [...LAYER_ORDER],
      selectedLayers: args.selectedLayers,
    },
    output: {
      asset: null,
      previewAsset: null,
      width: null,
      height: null,
    },
    error: null,
  };
  supersedeOlderJobs(args.characterId, job.jobId);
  writeJob(job);
  writeCurrentOutfit(args.characterId, job);
  return job;
}
