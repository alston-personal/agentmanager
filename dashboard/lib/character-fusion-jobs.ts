import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { AGENT_DATA_ROOT } from '@/lib/data-root';

export const CHARACTER_FUSION_SCHEMA = 'agentos.character-fusion-job/v1' as const;
export type CharacterFusionStatus = 'queued' | 'extracting' | 'rendering' | 'validating' | 'ready' | 'failed';

export type CharacterFusionJob = {
  schema: typeof CHARACTER_FUSION_SCHEMA;
  jobId: string;
  requestedBy: string;
  preset: string;
  status: CharacterFusionStatus;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  failedAt: string | null;
  input: {
    personAsset: string;
    mainVisualAsset: string | null;
  };
  output: {
    asset: string | null;
    serial: string | null;
    targetIr: unknown | null;
    actualIr: unknown | null;
    acceptance: unknown | null;
    provider: string | null;
  };
  error: { code: string; message: string } | null;
};

const ROOT = path.join(AGENT_DATA_ROOT, 'projects', 'character-fusion');
const JOB_DIR = path.join(ROOT, 'jobs');
const INPUT_DIR = path.join(ROOT, 'inputs');

function mkdir(dir: string) {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
}

function atomicWrite(file: string, payload: unknown) {
  mkdir(path.dirname(file));
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2) + '\n', { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(tmp, file);
}

function safeId(value: string) {
  if (!/^[A-Za-z0-9._-]{1,220}$/.test(value)) throw new Error('invalid id');
  return value;
}

function extForMime(mime: string) {
  if (mime === 'image/png') return '.png';
  if (mime === 'image/webp') return '.webp';
  if (mime === 'image/jpeg') return '.jpg';
  throw new Error('unsupported image type');
}

export function jobPath(jobId: string) {
  return path.join(JOB_DIR, safeId(jobId) + '.json');
}

export function readCharacterFusionJob(jobId: string): CharacterFusionJob | null {
  try {
    return JSON.parse(fs.readFileSync(jobPath(jobId), 'utf8')) as CharacterFusionJob;
  } catch {
    return null;
  }
}

export function writeCharacterFusionJob(job: CharacterFusionJob) {
  atomicWrite(jobPath(job.jobId), job);
}

async function saveFile(file: File, targetBase: string) {
  if (file.size < 256 || file.size > 12 * 1024 * 1024) throw new Error('image size must be 256 B to 12 MB');
  const ext = extForMime(file.type);
  const target = targetBase + ext;
  mkdir(path.dirname(target));
  fs.writeFileSync(target, Buffer.from(await file.arrayBuffer()), { mode: 0o600 });
  return target;
}

export async function createCharacterFusionJob(args: {
  requestedBy: string;
  preset?: string;
  person: File;
  mainVisual?: File | null;
}) {
  const preset = (args.preset || 'water-drop').trim().toLowerCase();
  if (!/^[a-z0-9-]{1,48}$/.test(preset)) throw new Error('invalid preset');
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const jobId = 'character-fusion-' + stamp + '-' + randomUUID().slice(0, 8);
  const inputRoot = path.join(INPUT_DIR, jobId);
  const personAsset = await saveFile(args.person, path.join(inputRoot, 'person'));
  const mainVisualAsset = args.mainVisual ? await saveFile(args.mainVisual, path.join(inputRoot, 'main-visual')) : null;
  const job: CharacterFusionJob = {
    schema: CHARACTER_FUSION_SCHEMA,
    jobId,
    requestedBy: args.requestedBy,
    preset,
    status: 'queued',
    requestedAt: new Date().toISOString(),
    startedAt: null,
    completedAt: null,
    failedAt: null,
    input: { personAsset, mainVisualAsset },
    output: {
      asset: null,
      serial: null,
      targetIr: null,
      actualIr: null,
      acceptance: null,
      provider: null,
    },
    error: null,
  };
  writeCharacterFusionJob(job);
  return job;
}

export function launchCharacterFusionWorker(jobId: string) {
  const candidates = [
    path.join(process.cwd(), 'scripts', 'character_fusion_worker.py'),
    path.join(process.cwd(), '..', 'scripts', 'character_fusion_worker.py'),
    '/home/ubuntu/agentmanager/scripts/character_fusion_worker.py',
  ];
  const worker = candidates.find((candidate) => fs.existsSync(candidate));
  if (!worker) throw new Error('character fusion worker not installed');

  const repoRoot = path.dirname(path.dirname(worker));
  const child = spawn('python3', [worker, '--job-id', safeId(jobId)], {
    cwd: repoRoot,
    env: {
      ...process.env,
      AGENTOS_REPO_ROOT: repoRoot,
    },
    detached: true,
    stdio: 'ignore',
  });
  child.unref();
}
