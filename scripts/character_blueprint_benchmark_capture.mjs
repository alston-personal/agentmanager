import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const url = process.env.CHARACTER_BLUEPRINT_URL || 'https://studio.milkcat.org/poc/character-blueprint/';
const fixture = process.env.CHARACTER_BLUEPRINT_FIXTURE;
const caseId = process.env.CHARACTER_BLUEPRINT_CASE_ID || 'real-person-fullbody';
const outDir = process.env.CHARACTER_BLUEPRINT_BENCHMARK_OUT || 'benchmark-artifacts/character-blueprint';

assert(fixture, 'CHARACTER_BLUEPRINT_FIXTURE is required');
assert(fs.existsSync(fixture), `fixture not found: ${fixture}`);
fs.mkdirSync(outDir, { recursive: true });

const sourceBytes = fs.readFileSync(fixture);
const sourceSha256 = crypto.createHash('sha256').update(sourceBytes).digest('hex');
const sourceExt = path.extname(fixture) || '.jpg';
const sourceCopy = path.join(outDir, `source${sourceExt}`);
fs.copyFileSync(fixture, sourceCopy);

const startedAt = new Date().toISOString();
const t0 = Date.now();
const browser = await chromium.launch({
  headless: true,
  args: ['--use-angle=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));

async function captureViewer(name) {
  const viewer = page.locator('#viewer');
  await viewer.screenshot({ path: path.join(outDir, `${name}.png`) });
}

async function dragYaw(deltaPixels) {
  const box = await page.locator('#viewer').boundingBox();
  assert(box, 'viewer bounding box missing');
  const x = box.x + box.width * 0.5;
  const y = box.y + box.height * 0.5;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x - deltaPixels, y, { steps: 14 });
  await page.mouse.up();
  await page.waitForTimeout(350);
}

try {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  assert(response && response.ok(), `public page HTTP failed: ${response?.status()}`);
  await page.waitForFunction(() => window.CharacterBlueprintPOC?.browserSelfTest === true, null, { timeout: 60_000 });
  await page.locator('#file').setInputFiles(fixture);
  await page.waitForFunction(() => {
    const s = document.getElementById('status');
    return s?.classList.contains('ok') || s?.classList.contains('err');
  }, null, { timeout: 120_000 });

  const state = await page.evaluate(() => {
    const status = document.getElementById('status');
    const irText = document.getElementById('json')?.textContent || '';
    let ir = null;
    try { ir = JSON.parse(irText); } catch {}
    return {
      statusClass: status?.className || '',
      statusText: status?.textContent || '',
      parts: [...document.querySelectorAll('#parts .part')].map(x => x.dataset.part),
      canvasCount: document.querySelectorAll('#viewer canvas').length,
      version: window.CharacterBlueprintPOC?.version || null,
      silhouetteEnvelope: window.CharacterBlueprintPOC?.silhouetteEnvelope === true,
      ir,
    };
  });

  assert(state.statusClass.includes('ok'), `analysis failed: ${JSON.stringify(state)}`);
  assert(state.ir, 'Character IR missing');
  assert.equal(state.ir.schema, 'character-blueprint-ir/v0.5');
  assert.equal(state.ir.proxy_3d?.renderer, 'threejs-silhouette-envelope/v0.5');
  assert(state.canvasCount >= 1, 'Three.js canvas missing');
  assert(pageErrors.length === 0, `page errors: ${pageErrors.join(' | ')}`);

  fs.writeFileSync(path.join(outDir, 'character-ir.json'), JSON.stringify(state.ir, null, 2) + '\n');

  // OrbitControls maps horizontal drag approximately to 2π * dx / element height.
  // Use cumulative calibrated drags: 0° -> 45° -> 90° -> 180°.
  const viewerBox = await page.locator('#viewer').boundingBox();
  assert(viewerBox, 'viewer bounding box missing');
  const h = viewerBox.height;
  await captureViewer('front');
  await dragYaw(h / 8);
  await captureViewer('yaw45');
  await dragYaw(h / 8);
  await captureViewer('right');
  await dragYaw(h / 4);
  await captureViewer('back');

  const result = {
    schema: 'character-blueprint-benchmark-result/v0.1',
    case_id: caseId,
    system_id: 'character-blueprint',
    model_version: state.version,
    settings: {
      public_url: url,
      renderer: state.ir.proxy_3d?.renderer || null,
      silhouette_engine: state.ir.observed?.silhouette?.engine || null,
      view_capture: 'orbitcontrols-drag-calibration/v0.1',
    },
    source_sha256: sourceSha256,
    started_at: startedAt,
    duration_seconds: Number(((Date.now() - t0) / 1000).toFixed(3)),
    credits: 0,
    estimated_cost_usd: 0,
    model_path: null,
    renders: {
      front: 'front.png',
      yaw45: 'yaw45.png',
      right: 'right.png',
      back: 'back.png',
    },
    geometry: {
      vertices: null,
      faces: null,
      components: state.parts.length,
    },
    scores: {},
    evidence: {
      character_ir: 'character-ir.json',
      source: path.basename(sourceCopy),
      coverage: state.ir.observed?.pose?.coverage || null,
      parts: state.parts,
      llm_tokens: state.ir.llm_tokens,
      assumed: state.ir.assumed || {},
    },
    notes: [
      'Character Blueprint v0.5 baseline capture.',
      'View angles are produced by deterministic OrbitControls drag calibration and are approximate until an explicit benchmark camera API is exposed.',
      'No external paid image-to-3D provider was invoked in this capture.',
    ],
  };
  fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ ok: true, suite: 'character-blueprint-benchmark-capture/v0.1', outDir, result }, null, 2));
} finally {
  await browser.close();
}
