import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const url = process.env.CHARACTER_BLUEPRINT_URL || 'https://studio.milkcat.org/poc/character-blueprint/';
const fixture = process.env.CHARACTER_BLUEPRINT_FIXTURE;
const outDir = process.env.CHARACTER_BLUEPRINT_BENCHMARK_OUT || '/tmp/image2ir-probe';
if (!fixture || !fs.existsSync(fixture)) throw new Error(`fixture missing: ${fixture}`);
fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
const page = await browser.newPage({viewport:{width:1440,height:1000}});
const pageErrors=[]; page.on('pageerror',e=>pageErrors.push(String(e)));
let probe={schema:'image2ir-teacher-probe/v0.1',url,fixture:path.basename(fixture),accepted:false};
try {
  const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  probe.http_status=response?.status() ?? null;
  await page.waitForFunction(()=>window.CharacterBlueprintPOC?.browserSelfTest===true,null,{timeout:60000});
  probe.app_version=await page.evaluate(()=>window.CharacterBlueprintPOC?.version||null);
  await page.locator('#file').setInputFiles(fixture);
  await page.waitForFunction(()=>{
    const s=document.getElementById('status');
    return s?.classList.contains('ok')||s?.classList.contains('err');
  },null,{timeout:120000});
  probe={...probe,...await page.evaluate(()=>{
    const s=document.getElementById('status');
    const text=document.getElementById('json')?.textContent||'';
    let ir=null; try{ir=JSON.parse(text)}catch{}
    return {
      accepted:s?.classList.contains('ok')||false,
      status_class:s?.className||'',
      status_text:s?.textContent||'',
      parts:[...document.querySelectorAll('#parts .part')].map(x=>x.dataset.part).filter(Boolean),
      ir,
    };
  })};
  probe.page_errors=pageErrors;
  await page.locator('#drop').screenshot({path:path.join(outDir,'probe-source-panel.png')});
  if (probe.ir) fs.writeFileSync(path.join(outDir,'character-ir.json'),JSON.stringify(probe.ir,null,2)+'\n');
} catch (e) {
  probe.runtime_error=String(e);
  probe.page_errors=pageErrors;
} finally {
  fs.writeFileSync(path.join(outDir,'probe.json'),JSON.stringify(probe,null,2)+'\n');
  await browser.close();
}
console.log(JSON.stringify({ok:true,accepted:probe.accepted,status_text:probe.status_text||null,app_version:probe.app_version||null}));
