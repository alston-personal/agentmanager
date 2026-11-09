#!/usr/bin/env node
const http = require('http');

const TARGET = 'oursong_alstonhuang';
const MESSAGE = '聽說你那邊最近很會發文？等你的 DM 接好，我們再來看看誰比較會吐槽。';
const BASE = 'http://127.0.0.1:9222';
let STAGE = 'module';

function httpJson(method, url) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = http.request({ method, hostname: u.hostname, port: u.port, path: u.pathname + u.search }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch (e) { reject(e); } });
    });
    req.on('error', reject);
    req.end();
  });
}
function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

async function connectTarget(wsurl) {
  if (typeof WebSocket === 'undefined') throw new Error('NODE_WEBSOCKET_UNAVAILABLE');
  const ws = new WebSocket(wsurl);
  await new Promise((resolve,reject)=>{
    const t=setTimeout(()=>reject(new Error('WS_OPEN_TIMEOUT')),10000);
    ws.addEventListener('open',()=>{clearTimeout(t);resolve();},{once:true});
    ws.addEventListener('error',e=>{clearTimeout(t);reject(e);},{once:true});
  });
  let seq=0;
  const pending=new Map();
  const listeners=new Set();
  ws.addEventListener('message', async ev=>{
    let raw=ev.data;
    try{
      if(typeof raw!=='string'){
        if(raw instanceof ArrayBuffer) raw=Buffer.from(raw).toString('utf8');
        else if(ArrayBuffer.isView(raw)) raw=Buffer.from(raw.buffer,raw.byteOffset,raw.byteLength).toString('utf8');
        else if(raw && typeof raw.text==='function') raw=await raw.text();
        else raw=String(raw);
      }
      const msg=JSON.parse(raw);
      if(msg.id && pending.has(msg.id)){
        const p=pending.get(msg.id); pending.delete(msg.id); p.resolve(msg);
      }else{
        for(const fn of listeners){ try{ fn(msg); }catch{} }
      }
    }catch{}
  });
  function cmd(method,params={},sessionId=null){
    return new Promise((resolve,reject)=>{
      const id=++seq;
      const timer=setTimeout(()=>{ pending.delete(id); reject(new Error('CDP_TIMEOUT:'+method)); },20000);
      pending.set(id,{resolve:(v)=>{clearTimeout(timer);resolve(v);}});
      const msg={id,method,params}; if(sessionId) msg.sessionId=sessionId; ws.send(JSON.stringify(msg));
    });
  }
  return {ws,cmd,onEvent:(fn)=>listeners.add(fn)};
}

async function browserSession(){
  const created=await httpJson('PUT',BASE+'/json/new?'+encodeURIComponent('https://www.threads.com/messages'));
  const wsurl=String(created.webSocketDebuggerUrl||'');
  if(!wsurl) throw new Error('MISSING_TARGET_WS_URL');
  const page=await connectTarget(wsurl);
  const cmd=(method,params={})=>page.cmd(method,params);
  return {browser:page,cmd};
}

function axValue(node,key){
  const v=(node||{})[key];
  return v && typeof v==='object' ? String(v.value||'') : String(v||'');
}

async function axNodes(cmd){
  const res=await cmd('Accessibility.getFullAXTree',{});
  return (((res||{}).result||{}).nodes)||[];
}

async function clickBackend(cmd,backendNodeId){
  const box=await cmd('DOM.getBoxModel',{backendNodeId});
  const model=((box||{}).result||{}).model||{};
  const q=model.content||model.border||[];
  if(!Array.isArray(q)||q.length<8) throw new Error('BOXMODEL_UNAVAILABLE');
  const xs=[q[0],q[2],q[4],q[6]], ys=[q[1],q[3],q[5],q[7]];
  const x=xs.reduce((a,b)=>a+b,0)/4, y=ys.reduce((a,b)=>a+b,0)/4;
  await cmd('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});
  await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});
}

async function main(){
  STAGE='browser_attach';
  const session=await browserSession();
  await sleep(10000);
  try{
    STAGE='login_check';
    const ft=await session.cmd('Page.getFrameTree',{});
    const frame=((((ft||{}).result||{}).frameTree||{}).frame)||{};
    const url=String(frame.url||'').toLowerCase();
    if(url.includes('/login')||url.includes('accountscenter')){
      console.log('mio_dm_oursong_acceptance=LOGIN_REQUIRED');
      return 4;
    }

    STAGE='conversation_find';
    let nodes=await axNodes(session.cmd);
    const conv=nodes.find(n=>!n.ignored && axValue(n,'name').includes(TARGET) && n.backendDOMNodeId);
    if(!conv){
      console.log('mio_dm_oursong_acceptance=NO_CONVERSATION');
      return 5;
    }
    await clickBackend(session.cmd,conv.backendDOMNodeId);
    await sleep(2500);

    STAGE='precheck';
    nodes=await axNodes(session.cmd);
    if(nodes.some(n=>axValue(n,'name').includes(MESSAGE))){
      console.log('mio_dm_oursong_acceptance=PASS');
      console.log('mio_dm_oursong_send=ALREADY_PRESENT');
      console.log('mio_dm_oursong_readback=PASS');
      return 0;
    }

    STAGE='composer';
    const textboxes=nodes.filter(n=>!n.ignored && axValue(n,'role')==='textbox' && n.backendDOMNodeId);
    const box=textboxes[textboxes.length-1];
    if(!box){
      console.log('mio_dm_oursong_acceptance=NO_COMPOSER');
      return 6;
    }
    await session.cmd('DOM.focus',{backendNodeId:box.backendDOMNodeId});
    await session.cmd('Input.insertText',{text:MESSAGE});
    await sleep(800);

    STAGE='send';
    nodes=await axNodes(session.cmd);
    const send=nodes.find(n=>!n.ignored && n.backendDOMNodeId && /^(send|傳送)$/i.test(axValue(n,'name').trim()));
    if(send){
      await clickBackend(session.cmd,send.backendDOMNodeId);
    }else{
      await session.cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
      await session.cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});
    }

    STAGE='readback';
    await sleep(3000);
    nodes=await axNodes(session.cmd);
    if(!nodes.some(n=>axValue(n,'name').includes(MESSAGE))){
      console.log('mio_dm_oursong_acceptance=UNVERIFIED');
      return 7;
    }

    console.log('mio_dm_oursong_acceptance=PASS');
    console.log('mio_dm_oursong_send=PASS');
    console.log('mio_dm_oursong_readback=PASS');
    return 0;
  }finally{
    try{session.browser.ws.close();}catch{}
  }
}

main().then(rc=>process.exit(rc)).catch(err=>{
  console.log('mio_dm_oursong_stage='+STAGE);
  const msg=String(err&&err.message||err||'');
  if(msg.startsWith('CDP_TIMEOUT:')) console.log('mio_dm_oursong_acceptance=ERROR_CDP_TIMEOUT');
  else if(msg==='NODE_WEBSOCKET_UNAVAILABLE') console.log('mio_dm_oursong_acceptance=ERROR_NODE_WEBSOCKET_UNAVAILABLE');
  else console.log('mio_dm_oursong_acceptance=ERROR_RUNTIME');
  process.exit(8);
});