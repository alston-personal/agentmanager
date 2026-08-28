import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const url = process.env.CHARACTER_BLUEPRINT_URL || 'https://studio.milkcat.org/poc/character-blueprint/';
const fixture = process.env.CHARACTER_BLUEPRINT_FIXTURE || '';
const browser = await chromium.launch({
  headless: true,
  args: ['--use-angle=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));

async function openPublicPage() {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  assert(response && response.ok(), `public page HTTP failed: ${response?.status()}`);
  await page.waitForFunction(() => window.CharacterBlueprintPOC?.browserSelfTest === true, null, { timeout: 60_000 });
}

async function runSyntheticGeometrySmoke() {
  const result = await page.evaluate(() => {
    const P=(x=.5,y=.5,z=0,visibility=0)=>({x,y,z,visibility});
    const l=Array.from({length:33},()=>P());
    Object.assign(l, {
      0:P(.59,.24,-.06,.99), 7:P(.53,.27,0,.93), 8:P(.65,.26,-.03,.91),
      11:P(.47,.43,.02,.96), 12:P(.68,.42,-.03,.96),
      13:P(.42,.60,.02,.82), 14:P(.73,.57,-.02,.80),
      15:P(.46,.77,.01,.62), 16:P(.76,.73,-.01,.60),
      23:P(.51,.88,1.4,.08), 24:P(.69,.90,-1.1,.07),
      25:P(.25,.35,2,.04), 26:P(.95,.31,-2,.03),
      27:P(.08,.22,2.4,.02), 28:P(.98,.20,-2.4,.02),
    });
    return {
      version: window.CharacterBlueprintPOC.version,
      silhouetteEnvelope: window.CharacterBlueprintPOC.silhouetteEnvelope,
      ...window.CharacterBlueprintPOC.selfTestLandmarks(l),
    };
  });

  assert.equal(result.version, '0.5.0');
  assert.equal(result.silhouetteEnvelope, true);
  assert.equal(result.coverage, 'upper_body');
  assert.equal(result.bodyFrame, 'silhouette-envelope-v0.5');
  assert.equal(result.silhouetteEngine, 'pose-fallback');
  assert.equal(result.selected, 'head');
  assert(result.canvasCount >= 1, `no Three.js canvas: ${JSON.stringify(result)}`);
  assert(result.meshCount >= 6, `too few meshes: ${JSON.stringify(result)}`);
  for (const required of ['head','hair','body','garment','left_arm','right_arm']) {
    assert(result.parts.includes(required), `missing ${required}: ${JSON.stringify(result)}`);
  }
  assert(!result.parts.includes('left_leg') && !result.parts.includes('right_leg'), `upper-body fixture invented legs: ${JSON.stringify(result)}`);
  return result;
}

async function runRealImageUploadSmoke() {
  assert(fixture, 'CHARACTER_BLUEPRINT_FIXTURE is required for real-image E2E');
  assert(fs.existsSync(fixture), `fixture not found: ${fixture}`);

  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForFunction(() => window.CharacterBlueprintPOC?.browserSelfTest === true, null, { timeout: 60_000 });
  await page.locator('#file').setInputFiles(fixture);

  await page.waitForFunction(() => {
    const s = document.getElementById('status');
    return s?.classList.contains('ok') || s?.classList.contains('err');
  }, null, { timeout: 120_000 });

  const result = await page.evaluate(() => {
    const status = document.getElementById('status');
    const irText = document.getElementById('json')?.textContent || '';
    let ir = null;
    try { ir = JSON.parse(irText); } catch {}
    return {
      statusClass: status?.className || '',
      statusText: status?.textContent || '',
      pose: document.getElementById('mPose')?.textContent || '',
      coverage: document.getElementById('mCoverage')?.textContent || '',
      partsMetric: Number(document.getElementById('mParts')?.textContent || 0),
      partButtons: [...document.querySelectorAll('#parts .part')].map(x => x.dataset.part),
      canvasCount: document.querySelectorAll('#viewer canvas').length,
      publicApi: {
        version: window.CharacterBlueprintPOC?.version,
        silhouetteEnvelope: window.CharacterBlueprintPOC?.silhouetteEnvelope,
      },
      ir,
    };
  });

  assert(result.statusClass.includes('ok'), `real-image analysis failed: ${JSON.stringify(result)}`);
  assert(result.statusText.includes('完成'), `unexpected success state: ${JSON.stringify(result)}`);
  assert.equal(result.publicApi.version, '0.5.0');
  assert.equal(result.publicApi.silhouetteEnvelope, true);
  assert(result.canvasCount >= 1, `real-image flow created no Three.js canvas: ${JSON.stringify(result)}`);
  assert(result.partsMetric >= 4, `real-image flow created too few 3D parts: ${JSON.stringify(result)}`);
  assert(result.ir, `real-image flow emitted invalid Character IR: ${JSON.stringify(result)}`);
  assert.equal(result.ir.schema, 'character-blueprint-ir/v0.5');
  assert.equal(result.ir.llm_tokens, 0);
  assert.equal(result.ir.proxy_3d?.renderer, 'threejs-silhouette-envelope/v0.5');
  assert.equal(result.ir.observed?.silhouette?.engine, 'border-evidence-silhouette/v0.5');
  assert(result.ir.observed?.silhouette?.torso_rows >= 5, `too few silhouette torso rows: ${JSON.stringify(result.ir.observed?.silhouette)}`);
  assert(result.ir.observed?.silhouette?.hair_rows >= 4, `too few silhouette hair rows: ${JSON.stringify(result.ir.observed?.silhouette)}`);
  assert(result.ir.observed?.pose?.mean_visibility > 0.1, `pose visibility too low: ${JSON.stringify(result.ir.observed?.pose)}`);
  assert(['full_body','three_quarter','upper_body'].includes(result.ir.observed?.pose?.coverage), `invalid coverage: ${JSON.stringify(result.ir.observed?.pose)}`);
  for (const required of ['head','hair','body','garment']) {
    assert(result.partButtons.includes(required), `real-image flow missing ${required}: ${JSON.stringify(result)}`);
  }
  return result;
}

try {
  await openPublicPage();
  const synthetic = await runSyntheticGeometrySmoke();
  const realImage = fixture ? await runRealImageUploadSmoke() : null;
  assert.equal(pageErrors.length, 0, `browser page errors: ${pageErrors.join(' | ')}`);

  console.log(JSON.stringify({
    ok: true,
    suite: 'character-blueprint-browser-smoke/v3',
    url,
    synthetic,
    realImage,
  }, null, 2));
} finally {
  await browser.close();
}
