/* Layout Lab -> AgentOS Capability Experience Bridge v0.7.0
 *
 * The LayoutLib library remains unaware of AgentOS. This browser-side adapter
 * observes editing outcomes, makes completion the learning boundary, and queues
 * abstract capability experiences for later governed convergence.
 *
 * No raw image bytes or image fingerprint are stored in the experience queue.
 */
(()=>{
'use strict';
const L=window.LayoutLibBrowser;
if(!L)return;

const VERSION='0.7.0';
const EXPERIENCE_KEY='layoutlib.capability.pending.v1';
const NODE_KEY='agentos.layoutlib.node_id.v1';
const PROFILE_CAPABILITY='layoutlib.profile-detection';
const RECONSTRUCTION_CAPABILITY='layoutlib.layout-reconstruction';
const MAX_PENDING=100;
const clone=v=>JSON.parse(JSON.stringify(v));
const now=()=>new Date().toISOString();
const uuid=()=>globalThis.crypto?.randomUUID?.()||`browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function nodeId(){
  let id=localStorage.getItem(NODE_KEY);
  if(!id){id=`layoutlab-${uuid()}`;localStorage.setItem(NODE_KEY,id)}
  return id;
}
function pending(){
  try{const v=JSON.parse(localStorage.getItem(EXPERIENCE_KEY)||'[]');return Array.isArray(v)?v:[]}catch(_){return[]}
}
function savePending(xs){localStorage.setItem(EXPERIENCE_KEY,JSON.stringify(xs.slice(-MAX_PENDING)))}
function queue(exp){const xs=pending();xs.push(exp);savePending(xs);refreshPendingLabel();return exp}
function correctionCost(m){return Number(m.walls_added||0)+Number(m.walls_deleted||0)+Number(m.erase_length_px||0)/100+Number(m.reanalyze_count||0)*.5+Number(m.manual_parameter_changes||0)*.25}
function quality(cost){return 1/(1+Math.max(0,Number(cost)||0))}
function wallPixels(ir){
  if(!ir?.walls||!ir.coordinate_frame)return 0;
  let n=0;
  for(const w of ir.walls){
    const a=L.worldToSourcePx(ir.coordinate_frame,w.start),b=L.worldToSourcePx(ir.coordinate_frame,w.end);
    n+=Math.hypot(b.x-a.x,b.y-a.y);
  }
  return n;
}

let session=null;
function resetSession(){
  session={
    id:uuid(),started_at:now(),revision:0,analyze_count:0,
    metrics:{walls_added:0,walls_deleted:0,erase_length_px:0,reanalyze_count:0,manual_parameter_changes:0}
  };
  if(finishBtn)finishBtn.disabled=!globalThis.currentIr;
  refreshPendingLabel();
}
function markDirty(){if(!session)resetSession();session.revision++;if(finishBtn)finishBtn.disabled=!globalThis.currentIr}

// Learning used to be coupled to pressing Analyze. Preserve the local prototype
// learner as an edge cache, but invoke it only at explicit completion.
let originalAssimilate=null;
try{
  if(typeof assimilateLearning==='function'){
    originalAssimilate=assimilateLearning;
    assimilateLearning=()=>{};
  }
}catch(_){/* older UI without this learner */}

// Instrument domain editing without changing LayoutLib's implementation.
if(typeof L.addWallPx==='function'){
  const old=L.addWallPx;
  L.addWallPx=(ir,...args)=>{
    const before=ir?.walls?.length||0,out=old(ir,...args),after=out?.walls?.length||0;
    if(after>before){if(!session)resetSession();session.metrics.walls_added+=after-before;markDirty()}
    return out;
  };
}
if(typeof L.eraseStrokePx==='function'){
  const old=L.eraseStrokePx;
  L.eraseStrokePx=(ir,...args)=>{
    const before=wallPixels(ir),out=old(ir,...args),after=wallPixels(out),delta=Math.max(0,before-after);
    if(delta>.01){if(!session)resetSession();session.metrics.erase_length_px+=delta;markDirty()}
    return out;
  };
}
if(typeof L.deleteWallsById==='function'){
  const old=L.deleteWallsById;
  L.deleteWallsById=(ir,...args)=>{
    const before=ir?.walls?.length||0,out=old(ir,...args),after=out?.walls?.length||0;
    if(after<before){if(!session)resetSession();session.metrics.walls_deleted+=before-after;markDirty()}
    return out;
  };
}

const analyzeBtn=document.getElementById('analyze');
analyzeBtn?.addEventListener('click',()=>{
  if(!session)resetSession();
  session.analyze_count++;
  session.metrics.reanalyze_count=Math.max(0,session.analyze_count-1);
  markDirty();
});
for(const id of ['threshold','thresholdRange','minlen']){
  document.getElementById(id)?.addEventListener('change',()=>{
    if(!session)resetSession();session.metrics.manual_parameter_changes++;markDirty();
  });
}
document.getElementById('file')?.addEventListener('change',()=>setTimeout(resetSession,0));

// Keep the completion affordance adjacent to Analyze: completion is the strong
// reward signal and the boundary at which experience becomes eligible to leave
// the browser edge cache.
const actionRow=analyzeBtn?.parentElement;
const finishBtn=document.createElement('button');
finishBtn.id='finishModel';
finishBtn.textContent='✓ 完成模型';
finishBtn.disabled=true;
if(actionRow)actionRow.appendChild(finishBtn);
const pendingLabel=document.createElement('div');
pendingLabel.id='capabilityPending';
pendingLabel.className='hint';
pendingLabel.style.marginTop='6px';
actionRow?.parentElement?.appendChild(pendingLabel);

function refreshPendingLabel(){
  if(!pendingLabel)return;
  const n=pending().length;
  pendingLabel.textContent=n?`Capability Experience：${n} 筆待回歸 AgentOS`:'Capability Experience：目前無待回歸資料';
}

function makeExperiences(){
  if(!globalThis.currentIr)throw new Error('no current Spatial IR');
  if(!session)resetSession();
  const metrics=clone(session.metrics),cost=correctionCost(metrics),accepted=true;
  const features=(typeof profileFeatures!=='undefined'&&profileFeatures)?clone(profileFeatures):{};
  const policy={
    threshold:Number(document.getElementById('threshold')?.value||128),
    min_wall_length_px:Number(document.getElementById('minlen')?.value||16)
  };
  const common={
    node_id:nodeId(),created_at:now(),session_id:session.id,revision:session.revision,
    provenance:{source:'layoutlab-web',bridge_version:VERSION,spatial_ir_version:String(currentIr.version||'unknown')}
  };
  const profile={
    schema:'agentos.capability-experience/v1',experience_id:`exp-${uuid()}`,
    capability_id:PROFILE_CAPABILITY,...common,
    observation:{profile_features:features,document_stats:{wall_count:currentIr.walls?.length||0,image_width_px:currentIr.image_width_px||0,image_height_px:currentIr.image_height_px||0}},
    policy_used:policy,
    outcome:{accepted,correction_cost:cost,quality:quality(cost),...metrics}
  };
  const reconstruction={
    schema:'agentos.capability-experience/v1',experience_id:`exp-${uuid()}`,
    capability_id:RECONSTRUCTION_CAPABILITY,...common,
    observation:{component_receipts:{profile_experience:profile.experience_id},document_stats:{wall_count:currentIr.walls?.length||0}},
    policy_used:{},
    outcome:{accepted,correction_cost:cost,quality:quality(cost),...metrics}
  };
  return [profile,reconstruction];
}

finishBtn.onclick=()=>{
  try{
    const xs=makeExperiences();xs.forEach(queue);
    if(originalAssimilate&&typeof profileFeatures!=='undefined'&&profileFeatures)originalAssimilate();
    finishBtn.disabled=true;
    if(typeof status!=='undefined')status.textContent=`模型完成：correction cost ${xs[0].outcome.correction_cost.toFixed(2)}；已產生抽象 Capability Experience，等待回歸。`;
  }catch(err){if(typeof status!=='undefined')status.textContent=`完成失敗：${err.message||err}`}
};

function applyCanonicalPolicy(state){
  const policy=state?.payload?.policy||state?.policy||{};
  const t=Number(policy.threshold),m=Number(policy.min_wall_length_px);
  if(Number.isFinite(t)){
    const a=document.getElementById('threshold'),b=document.getElementById('thresholdRange');
    if(a)a.value=String(Math.round(t));if(b)b.value=String(Math.round(t));
    const badge=document.getElementById('thrBadge');if(badge)badge.textContent=String(Math.round(t));
  }
  if(Number.isFinite(m)){const el=document.getElementById('minlen');if(el)el.value=String(Math.round(m))}
  if(typeof profilePrediction!=='undefined')profilePrediction={threshold:Number.isFinite(t)?Math.round(t):Number(document.getElementById('threshold')?.value||128),min_wall_length_px:Number.isFinite(m)?Math.round(m):Number(document.getElementById('minlen')?.value||16),confidence:Number(state?.confidence||0),source:'agentos_canonical'};
  if(typeof refreshLearnerLabel==='function')refreshLearnerLabel();
  return policy;
}

window.LayoutCapabilityBridge={
  version:VERSION,
  experienceKey:EXPERIENCE_KEY,
  nodeId,
  pendingExperiences:()=>clone(pending()),
  drainPendingExperiences:()=>{const xs=pending();localStorage.removeItem(EXPERIENCE_KEY);refreshPendingLabel();return clone(xs)},
  applyCanonicalPolicy,
  correctionCost,
  makeExperiences:()=>clone(makeExperiences())
};
resetSession();
})();
