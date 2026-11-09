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
  ws.addEventListener('message', ev=>{
    let msg; try { msg=JSON.parse(String(ev.data)); } catch { return; }
    if(msg.id && pending.has(msg.id)){
      const p=pending.get(msg.id); pending.delete(msg.id); p.resolve(msg);
    }
  });
  function cmd(method,params={}){
    return new Promise((resolve,reject)=>{
      const id=++seq;
      const timer=setTimeout(()=>{ pending.delete(id); reject(new Error('CDP_TIMEOUT:'+method)); },20000);
      pending.set(id,{resolve:(v)=>{clearTimeout(timer);resolve(v);}});
      ws.send(JSON.stringify({id,method,params}));
    });
  }
  return {ws,cmd};
}

async function newMessagesTarget(){
  const url = BASE + '/json/new?' + encodeURIComponent('https://www.threads.com/messages');
  const t = await httpJson('PUT', url);
  if(!t.webSocketDebuggerUrl) throw new Error('MISSING_WS_URL');
  return t;
}

async function evalValue(cmd, expr){
  const res = await cmd('Runtime.evaluate',{expression:expr,returnByValue:true,awaitPromise:true});
  const rr = (((res||{}).result||{}).result)||{};
  if(rr.exceptionDetails) throw new Error('RUNTIME_EVALUATE_EXCEPTION');
  return rr.value;
}

async function main(){
  STAGE='target_new';
  const target = await newMessagesTarget();
  await sleep(10000);
  STAGE='ws_connect';
  const session = await connectTarget(String(target.webSocketDebuggerUrl));
  try {
    STAGE='login_check';
    const stateExpr = "(()=>({url:location.href,body:(document.body?.innerText||'').slice(0,1200)}))()";
    const state = await evalValue(session.cmd, stateExpr) || {};
    const url = String(state.url||'').toLowerCase();
    if(url.includes('/login') || url.includes('accountscenter')) {
      console.log('mio_dm_oursong_acceptance=LOGIN_REQUIRED');
      return 4;
    }

    STAGE='conversation_find';
    const clickExpr = "(()=>{const target=" + JSON.stringify(TARGET) + ";const els=[...document.querySelectorAll('a,button,[role=\\\"button\\\"],[role=\\\"link\\\"]')];const e=els.find(x=>((x.innerText||'').trim()).includes(target));if(!e)return 'NOT_FOUND';e.click();return 'CLICKED';})()";
    const clicked = await evalValue(session.cmd, clickExpr);
    if(clicked!=='CLICKED'){ console.log('mio_dm_oursong_acceptance=NO_CONVERSATION'); return 5; }
    await sleep(2500);

    STAGE='precheck';
    const preExpr = "(()=>((document.querySelector('main')?.innerText||document.body.innerText||'').includes(" + JSON.stringify(MESSAGE) + ")?'FOUND':'MISSING'))()";
    const already = await evalValue(session.cmd, preExpr);
    if(already==='FOUND'){
      console.log('mio_dm_oursong_acceptance=PASS');
      console.log('mio_dm_oursong_send=ALREADY_PRESENT');
      console.log('mio_dm_oursong_readback=PASS');
      return 0;
    }

    STAGE='composer';
    const sendExpr = "(()=>{const text=" + JSON.stringify(MESSAGE) + ";const box=[...document.querySelectorAll('textarea,[contenteditable=\\\"true\\\"]')].find(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0});if(!box)return 'NO_COMPOSER';box.focus();if(box.tagName==='TEXTAREA'){const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;set.call(box,text);box.dispatchEvent(new Event('input',{bubbles:true}));}else{document.execCommand('selectAll',false,null);document.execCommand('insertText',false,text);box.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:text}));}const buttons=[...document.querySelectorAll('button,[role=\\\"button\\\"]')];const send=buttons.find(x=>/^(Send|傳送)$/i.test((x.innerText||x.getAttribute('aria-label')||'').trim()));if(send){send.click();return 'SENT_BUTTON';}box.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent('keypress',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));box.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));return 'SENT_ENTER';})()";
    const sendResult = await evalValue(session.cmd, sendExpr);
    if(sendResult==='NO_COMPOSER'){ console.log('mio_dm_oursong_acceptance=NO_COMPOSER'); return 6; }

    STAGE='readback';
    await sleep(3000);
    const verifyExpr = "(()=>((document.querySelector('main')?.innerText||document.body.innerText||'').includes(" + JSON.stringify(MESSAGE) + ")?'FOUND':'MISSING'))()";
    const verify = await evalValue(session.cmd, verifyExpr);
    if(verify!=='FOUND'){ console.log('mio_dm_oursong_acceptance=UNVERIFIED'); return 7; }

    console.log('mio_dm_oursong_acceptance=PASS');
    console.log('mio_dm_oursong_send=PASS');
    console.log('mio_dm_oursong_readback=PASS');
    return 0;
  } finally { try { session.ws.close(); } catch {} }
}

main().then(rc=>process.exit(rc)).catch(err=>{
  console.log('mio_dm_oursong_stage='+STAGE);
  const msg=String(err&&err.message||err||'');
  if(msg.startsWith('CDP_TIMEOUT:')) console.log('mio_dm_oursong_acceptance=ERROR_CDP_TIMEOUT');
  else if(msg==='NODE_WEBSOCKET_UNAVAILABLE') console.log('mio_dm_oursong_acceptance=ERROR_NODE_WEBSOCKET_UNAVAILABLE');
  else console.log('mio_dm_oursong_acceptance=ERROR_RUNTIME');
  process.exit(8);
});