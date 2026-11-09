#!/usr/bin/env node
const http=require('http');
const OURSONG_BASE='http://127.0.0.1:9223';
const MIO_BASE='http://127.0.0.1:9222';
const TARGET='mio.milkcat';
const INBOUND='聽說你那邊最近很會發文？等你的 DM 接好，我們再來看看誰比較會吐槽。';
const REPLY='收到。先別急著比誰會吐槽，至少我們現在真的能互相 DM 了。';
let STAGE='module';
function httpJson(method,url){return new Promise((resolve,reject)=>{const u=new URL(url);const req=http.request({method,hostname:u.hostname,port:u.port,path:u.pathname+u.search},res=>{let d='';res.on('data',x=>d+=x);res.on('end',()=>{try{resolve(JSON.parse(d))}catch(e){reject(e)}})});req.on('error',reject);req.end();});}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
async function connect(wsurl){const ws=new WebSocket(wsurl);await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('WS_OPEN_TIMEOUT')),10000);ws.addEventListener('open',()=>{clearTimeout(t);resolve()},{once:true});ws.addEventListener('error',e=>{clearTimeout(t);reject(e)},{once:true});});let seq=0;const pending=new Map();ws.addEventListener('message',async ev=>{let raw=ev.data;try{if(typeof raw!=='string'){if(raw instanceof ArrayBuffer)raw=Buffer.from(raw).toString('utf8');else if(ArrayBuffer.isView(raw))raw=Buffer.from(raw.buffer,raw.byteOffset,raw.byteLength).toString('utf8');else if(raw&&typeof raw.text==='function')raw=await raw.text();else raw=String(raw);}const msg=JSON.parse(raw);if(msg.id&&pending.has(msg.id)){const p=pending.get(msg.id);pending.delete(msg.id);p.resolve(msg);}}catch{}});function cmd(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP_TIMEOUT:'+method));},20000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v)}});ws.send(JSON.stringify({id,method,params}));});}return{ws,cmd};}
async function pageSession(base){const created=await httpJson('PUT',base+'/json/new?'+encodeURIComponent('https://www.threads.com/messages'));if(!created.webSocketDebuggerUrl)throw new Error('MISSING_TARGET_WS_URL');return connect(created.webSocketDebuggerUrl);}
function axv(n,k){const v=(n||{})[k];return v&&typeof v==='object'?String(v.value||''):String(v||'');}
async function ax(cmd){const r=await cmd('Accessibility.getFullAXTree',{});return (((r||{}).result||{}).nodes)||[];}
async function click(cmd,id){const b=await cmd('DOM.getBoxModel',{backendNodeId:id});const q=((((b||{}).result||{}).model||{}).content)||[];if(q.length<8)throw new Error('BOXMODEL_UNAVAILABLE');const x=(q[0]+q[2]+q[4]+q[6])/4,y=(q[1]+q[3]+q[5]+q[7])/4;await cmd('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});}
(async()=>{const s=await pageSession(OURSONG_BASE);try{await sleep(8000);STAGE='login_check';const ft=await s.cmd('Page.getFrameTree',{});const url=String((((ft||{}).result||{}).frameTree||{}).frame?.url||'').toLowerCase();if(url.includes('/login')||url.includes('accountscenter')){console.log('oursong_dm_mio_roundtrip=LOGIN_REQUIRED');process.exitCode=4;return;}STAGE='conversation_find';let nodes=await ax(s.cmd);const conv=nodes.find(n=>!n.ignored&&n.backendDOMNodeId&&axv(n,'name').includes(TARGET));if(!conv){console.log('oursong_dm_mio_roundtrip=NO_CONVERSATION');process.exitCode=5;return;}await click(s.cmd,conv.backendDOMNodeId);await sleep(2000);STAGE='verify_inbound';nodes=await ax(s.cmd);if(!nodes.some(n=>axv(n,'name').includes(INBOUND))){console.log('oursong_dm_mio_roundtrip=INBOUND_NOT_FOUND');process.exitCode=6;return;}console.log('oursong_dm_mio_inbound=PASS');if(nodes.some(n=>axv(n,'name').includes(REPLY))){console.log('oursong_dm_mio_reply=ALREADY_PRESENT');console.log('oursong_dm_mio_roundtrip=PASS');return;}STAGE='reply';const boxes=nodes.filter(n=>!n.ignored&&axv(n,'role')==='textbox'&&n.backendDOMNodeId);const box=boxes[boxes.length-1];if(!box){console.log('oursong_dm_mio_roundtrip=NO_COMPOSER');process.exitCode=7;return;}await s.cmd('DOM.focus',{backendNodeId:box.backendDOMNodeId});await s.cmd('Input.insertText',{text:REPLY});await sleep(500);nodes=await ax(s.cmd);const send=nodes.find(n=>!n.ignored&&n.backendDOMNodeId&&/^(send|傳送)$/i.test(axv(n,'name').trim()));if(send)await click(s.cmd,send.backendDOMNodeId);else{await s.cmd('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});await s.cmd('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13});}STAGE='readback';await sleep(2500);nodes=await ax(s.cmd);if(!nodes.some(n=>axv(n,'name').includes(REPLY))){console.log('oursong_dm_mio_roundtrip=UNVERIFIED');process.exitCode=8;return;}console.log('oursong_dm_mio_reply=PASS');
STAGE='mio_verify';
const m=await pageSession(MIO_BASE);
try{
  await sleep(5000);
  let mnodes=await ax(m.cmd);
  const mconv=mnodes.find(n=>!n.ignored&&n.backendDOMNodeId&&axv(n,'name').includes('oursong_alstonhuang'));
  if(!mconv){console.log('mio_dm_oursong_reply_verify=NO_CONVERSATION');process.exitCode=10;return;}
  await click(m.cmd,mconv.backendDOMNodeId);
  await sleep(1800);
  mnodes=await ax(m.cmd);
  if(!mnodes.some(n=>axv(n,'name').includes(REPLY))){console.log('mio_dm_oursong_reply_verify=NOT_FOUND');process.exitCode=11;return;}
  console.log('mio_dm_oursong_reply_verify=PASS');
  console.log('oursong_dm_mio_roundtrip=PASS');
}finally{try{m.ws.close()}catch{}}
}finally{try{s.ws.close()}catch{}}})().catch(e=>{console.log('oursong_dm_mio_stage='+STAGE);console.log('oursong_dm_mio_roundtrip=ERROR_RUNTIME');process.exit(9);});
