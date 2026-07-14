/**
 * Minimal CDP test - just read state, take screenshots, no navigation
 */
const { spawn, execSync } = require('child_process');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');

const WS_PORT = 9420;
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let msgId = 0;
let handlers = new Map();

function send(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    ws.send(JSON.stringify({ id, method, params }));
    const timer = setTimeout(() => { handlers.delete(id); reject(new Error(`Timeout ${method}`)); }, 15000);
    handlers.set(id, (err, result) => { clearTimeout(timer); err ? reject(err) : resolve(result); });
  });
}

function log(label, data) {
  if (data && typeof data === 'object') {
    console.log(`  ${label}:`, JSON.stringify(data).slice(0, 500));
  } else {
    console.log(`  ${label}:`, String(data).slice(0, 500));
  }
}

(async () => {
  console.log('=== Minimal CDP Test ===\n');

  // Cleanup and launch
  try { execSync('powershell.exe -Command "Get-Process wechatdevtools -ErrorAction SilentlyContinue | Stop-Process -Force"', { timeout: 10000 }); } catch(e) {}
  await sleep(3000);

  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c', 'E:\\微信web开发者工具\\cli.bat', 'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], { windowsHide: true, stdio: 'ignore' });

  // Wait for WS
  let ws;
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    try {
      ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);
      await new Promise((res, rej) => {
        ws.on('open', res);
        ws.on('error', rej);
        ws.on('message', data => {
          try {
            const m = JSON.parse(data.toString());
            if (m.id != null && handlers.has(m.id)) {
              const h = handlers.get(m.id);
              handlers.delete(m.id);
              if (m.error) h(new Error(typeof m.error.message === 'string' ? m.error.message : JSON.stringify(m.error)), null);
              else h(null, m.result);
            }
          } catch(e) {}
        });
      });
      console.log('Connected after', i+1, 's\n');
      break;
    } catch(e) {
      if (i === 59) { console.error('Timeout'); proc.kill(); process.exit(1); }
    }
  }

  try {
    // === Step 1: Get IDE info ===
    console.log('=== 1. Tool Info ===');
    const toolInfo = await send(ws, 'Tool.getInfo');
    log('Tool Info', toolInfo);

    // === Step 2: Get current page ===
    console.log('\n=== 2. Current Page ===');
    const cp = await send(ws, 'App.getCurrentPage');
    log('Current Page', cp);

    // === Step 3: Screenshot ===
    console.log('\n=== 3. Screenshot ===');
    const ss = await send(ws, 'App.captureScreenshot');
    if (ss && ss.data) {
      const buf = Buffer.from(ss.data, 'base64');
      fs.writeFileSync(path.join(SS_DIR, 'cdp_home.png'), buf);
      console.log(`  Screenshot saved: ${buf.length} bytes`);
    }

    // === Step 4: Get page data ===
    console.log('\n=== 4. Page Data ===');
    const evalResult = await send(ws, 'App.callFunction', {
      functionDeclaration: 'function() { try { var p = getCurrentPages(); if (p.length > 0) { return JSON.stringify({ route: p[p.length-1].route, pageLoading: p[p.length-1].data.pageLoading, pageError: p[p.length-1].data.pageError, dailyCard: p[p.length-1].data.dailyCard ? p[p.length-1].data.dailyCard.name_zh : null }); } return "no_pages"; } catch(e) { return "err:" + e.message; } }',
      args: []
    });
    log('Evaluate', evalResult);

    // === Step 5: Get page stack ===
    console.log('\n=== 5. Page Stack ===');
    const ps = await send(ws, 'App.getPageStack');
    log('Page Stack', ps);

    // === Step 6: Try navigate ===
    console.log('\n=== 6. Try switchTab ===');
    try {
      const nav = await send(ws, 'App.callWxMethod', {
        method: 'switchTab',
        args: [{ url: 'pages/index/index' }]
      });
      log('switchTab', nav);
    } catch(e) {
      console.log('  switchTab FAILED:', e.message.slice(0, 200));
    }

    ws.close();
  } catch(e) {
    console.error('\nERROR:', e.message || e);
  }

  proc.kill();
  console.log('\nDone.');
})();
