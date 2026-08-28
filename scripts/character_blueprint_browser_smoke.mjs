import { chromium } from 'playwright';
import assert from 'node:assert/strict';

const url = process.env.CHARACTER_BLUEPRINT_URL || 'https://studio.milkcat.org/poc/character-blueprint/';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const pageErrors = [];
page.on('pageerror', e => pageErrors.push(String(e)));

try {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  assert(response && response.ok(), `public page HTTP failed: ${response?.status()}`);
  await page.waitForFunction(() => window.CharacterBlueprintPOC?.browserSelfTest === true, null, { timeout: 60_000 });

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
      ...window.CharacterBlueprintPOC.selfTestLandmarks(l),
    };
  });

  assert.equal(result.version, '0.4.1');
  assert.equal(result.coverage, 'upper_body');
  assert.equal(result.bodyFrame, 'visibility-gated-v0.4.1');
  assert.equal(result.selected, 'head');
  assert(result.canvasCount >= 1, `no Three.js canvas: ${JSON.stringify(result)}`);
  assert(result.meshCount >= 6, `too few meshes: ${JSON.stringify(result)}`);
  for (const required of ['head','hair','body','garment','left_arm','right_arm']) {
    assert(result.parts.includes(required), `missing ${required}: ${JSON.stringify(result)}`);
  }
  assert(!result.parts.includes('left_leg') && !result.parts.includes('right_leg'), `upper-body fixture invented legs: ${JSON.stringify(result)}`);
  assert.equal(pageErrors.length, 0, `browser page errors: ${pageErrors.join(' | ')}`);

  console.log(JSON.stringify({ ok:true, suite:'character-blueprint-browser-smoke/v1', url, result }, null, 2));
} finally {
  await browser.close();
}
