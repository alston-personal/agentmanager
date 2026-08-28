import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).map((x, i, a) => x.startsWith('--') ? [x.slice(2), a[i + 1]] : null).filter(Boolean));
const glbPath = path.resolve(args.glb || 'model.glb');
const outDir = path.resolve(args.out || path.dirname(glbPath));
const resultPath = path.resolve(args.result || path.join(outDir, 'result.json'));
assert(fs.existsSync(glbPath), `GLB not found: ${glbPath}`);
fs.mkdirSync(outDir, { recursive: true });

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#07131d}canvas{display:block;width:100%;height:100%}
</style><script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.164.1/examples/jsm/"}}</script></head><body><script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x07131d);
const camera=new THREE.PerspectiveCamera(36,1,0.01,100); camera.position.set(0,0,4.2); camera.lookAt(0,0,0);
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true}); renderer.setPixelRatio(1); renderer.setSize(768,768); renderer.outputColorSpace=THREE.SRGBColorSpace; document.body.appendChild(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xddeeff,0x223344,2.2));
const key=new THREE.DirectionalLight(0xffffff,2.8); key.position.set(3,4,5); scene.add(key);
const fill=new THREE.DirectionalLight(0x9dc7ff,1.2); fill.position.set(-4,2,2); scene.add(fill);
const rim=new THREE.DirectionalLight(0xffffff,1.0); rim.position.set(0,3,-5); scene.add(rim);
const root=new THREE.Group(); scene.add(root);
let stats={vertices:0,faces:0,components:0};
function render(){renderer.render(scene,camera)}
window.setYaw=(deg)=>{root.rotation.y=-THREE.MathUtils.degToRad(deg);render();return deg};
new GLTFLoader().load('/model.glb',g=>{
 const model=g.scene; root.add(model);
 let box=new THREE.Box3().setFromObject(model); const center=box.getCenter(new THREE.Vector3()); model.position.sub(center);
 box=new THREE.Box3().setFromObject(model); const size=box.getSize(new THREE.Vector3()); const max=Math.max(size.x,size.y,size.z)||1; const scale=2.45/max; model.scale.setScalar(scale);
 box=new THREE.Box3().setFromObject(model); const sphere=box.getBoundingSphere(new THREE.Sphere());
 camera.position.set(0,0,Math.max(3.0,sphere.radius*3.15)); camera.lookAt(0,0,0);
 model.traverse(o=>{if(o.isMesh&&o.geometry){stats.components++;const p=o.geometry.getAttribute('position');if(p)stats.vertices+=p.count;const idx=o.geometry.index;stats.faces+=idx?Math.floor(idx.count/3):p?Math.floor(p.count/3):0;}});
 window.modelStats=stats; window.ready=true; render();
},undefined,e=>{window.loadError=String(e);window.ready=false});
</script></body></html>`;

const server = http.createServer((req, res) => {
  if (req.url === '/model.glb') {
    res.writeHead(200, {'Content-Type':'model/gltf-binary','Access-Control-Allow-Origin':'*'});
    fs.createReadStream(glbPath).pipe(res);
    return;
  }
  res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'}); res.end(html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;
const browser = await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-webgl','--ignore-gpu-blocklist']});
try {
  const page=await browser.newPage({viewport:{width:768,height:768}});
  const errors=[]; page.on('pageerror', e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>window.ready===true||window.loadError,{timeout:60000});
  const loadError=await page.evaluate(()=>window.loadError||null); assert(!loadError,`GLB load error: ${loadError}`);
  const views={front:0,yaw45:45,right:90,back:180};
  const renders={};
  for (const [name,yaw] of Object.entries(views)) {
    await page.evaluate(y=>window.setYaw(y),yaw); await page.waitForTimeout(120);
    const file=`canonical-${name}.png`; await page.locator('canvas').screenshot({path:path.join(outDir,file)}); renders[name]=file;
  }
  const stats=await page.evaluate(()=>window.modelStats);
  fs.writeFileSync(path.join(outDir,'geometry.json'),JSON.stringify(stats,null,2)+'\n');
  if (fs.existsSync(resultPath)) {
    const result=JSON.parse(fs.readFileSync(resultPath,'utf8'));
    result.renders=renders;
    result.geometry=stats;
    result.settings={...(result.settings||{}),canonical_render:'threejs-glb-canonical/v0.1'};
    result.notes=[...(result.notes||[]),'Canonical benchmark renders generated from downloaded GLB at yaw 0°, 45°, 90°, and 180°.'];
    fs.writeFileSync(resultPath,JSON.stringify(result,null,2)+'\n');
  }
  assert(errors.length===0,`browser errors: ${errors.join(' | ')}`);
  console.log(JSON.stringify({ok:true,suite:'character-blueprint-glb-render/v0.1',renders,geometry:stats},null,2));
} finally {
  await browser.close(); await new Promise(resolve=>server.close(resolve));
}
