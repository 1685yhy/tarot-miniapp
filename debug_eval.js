/**
 * Debug specific eval function formats
 */
const WebSocket = require('ws');
const { spawn } = require('child_process');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fs = require('fs');

let msgId = 0, handlers = new Map();
function send(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    ws.send(JSON.stringify({ id, method, params }));
    const t = setTimeout(() => { handlers.delete(id); reject(new Error('Timeout')); }, 15000);
    handlers.set(id, (err, result) => { clearTimeout(t); err ? reject(err) : resolve(result); });
  });
}

(async () => {
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c','E:\\微信web开发者工具\\cli.bat','auto',
    '--project','E:\\tarot-miniapp\\miniapp','--auto-port','9420'
  ], {windowsHide:true, stdio:'ignore'});

  let ws;
  for(let i=0;i<60;i++){
    await sleep(1000);
    try {
      ws = new WebSocket('ws://127.0.0.1:9420');
      await new Promise((res,rej) => {
        ws.on('open', res);
        ws.on('error', rej);
        ws.on('message', data => {
          try {
            const m = JSON.parse(data.toString());
            if(m.id != null && handlers.has(m.id)) {
              const h = handlers.get(m.id);
              handlers.delete(m.id);
              if(m.error) h(new Error(typeof m.error.message === 'string' ? m.error.message : JSON.stringify(m.error)), null);
              else h(null, m.result);
            }
          } catch(e) {}
        });
      });
      console.log('Connected');
      break;
    } catch(e) {
      if(i===59){console.log('Timeout');proc.kill();process.exit(1);}
    }
  }

  // Test 1: Simple
  console.log('\nTest 1: Simple 42');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){return 42}', args:[]});
    console.log('  OK:', JSON.stringify(r).slice(0,200));
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  // Test 2: getCurrentPages
  console.log('\nTest 2: getCurrentPages');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){var p=getCurrentPages();return p.length}', args:[]});
    console.log('  OK: pages=', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  // Test 3: drawDailyCard type
  console.log('\nTest 3: typeof drawDailyCard');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){var p=getCurrentPages();if(p.length){return typeof p[p.length-1].drawDailyCard}}', args:[]});
    console.log('  Result:', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  // Test 4: try-catch in function
  console.log('\nTest 4: try-catch simple');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){try{return 1}catch(e){return 0}}', args:[]});
    console.log('  OK:', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  // Test 5: try-catch with getCurrentPages
  console.log('\nTest 5: try-catch + pages');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){try{var p=getCurrentPages();if(p&&p.length){return p[p.length-1].route}}return"no_pages"}catch(e){return"err:"+e.message}', args:[]});
    console.log('  OK:', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  // Test 6: Call drawDailyCard
  console.log('\nTest 6: Call drawDailyCard');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){var p=getCurrentPages();if(p&&p.length&&p[p.length-1].drawDailyCard){p[p.length-1].drawDailyCard();return"called"}return"no_method"}', args:[]});
    console.log('  OK:', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  await sleep(2000);

  // Test 7: After draw state
  console.log('\nTest 7: After draw');
  try {
    const r = await send(ws, 'App.callFunction', {functionDeclaration: 'function(){var p=getCurrentPages();var d=p[p.length-1].data;return JSON.stringify({card:d.dailyCard?d.dailyCard.name_zh:null,loading:d.drawingLoading,err:d.pageError})}', args:[]});
    console.log('  OK:', r && r.result);
  } catch(e) { console.log('  FAIL:', e.message.slice(0,100)); }

  ws.close();
  proc.kill();
  console.log('\nDone');
})();
