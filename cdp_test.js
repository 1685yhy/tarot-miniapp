/**
 * Connect via raw CDP WebSocket, handle commands manually
 */
const { spawn } = require('child_process');
const WebSocket = require('ws');

const WS_PORT = 9420;
const POLL_INTERVAL = 1000;
const MAX_WAIT = 45000;

function waitForWS(timeout) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    function tryConnect() {
      if (Date.now() - start > timeout) return reject(new Error('Timeout'));
      const ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);
      ws.on('open', () => { ws.close(); resolve(); });
      ws.on('error', () => setTimeout(tryConnect, POLL_INTERVAL));
    }
    tryConnect();
  });
}

function cdpCall(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = Math.floor(Math.random() * 100000);
    const msg = JSON.stringify({ id, method, params });
    ws.send(msg);

    const handler = (data) => {
      try {
        const resp = JSON.parse(data.toString());
        if (resp.id === id) {
          ws.removeListener('message', handler);
          if (resp.error) reject(new Error(resp.error.message || JSON.stringify(resp.error)));
          else resolve(resp.result);
        }
      } catch(e) {}
    };
    ws.on('message', handler);

    setTimeout(() => {
      ws.removeListener('message', handler);
      reject(new Error('Timeout waiting for response'));
    }, 10000);
  });
}

(async () => {
  console.log('=== CDP Test ===\n');

  // Launch IDE
  console.log('Launching IDE...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c','E:\\微信web开发者工具\\cli.bat','auto',
    '--project','E:\\tarot-miniapp\\miniapp','--auto-port',String(WS_PORT)
  ], {windowsHide:true, stdio:'ignore'});

  console.log(`Waiting for WS at ws://127.0.0.1:${WS_PORT}...`);
  await waitForWS(MAX_WAIT);
  console.log('WS available, connecting...\n');

  const ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);

  await new Promise((resolve, reject) => {
    ws.on('open', resolve);
    ws.on('error', reject);
    ws.on('message', data => {
      // Log all messages for debugging
      try {
        const parsed = JSON.parse(data.toString());
        if (!parsed.id) {
          // Notification (no id)
          console.log('  NOTIFY:', parsed.method || JSON.stringify(parsed).slice(0,200));
        }
      } catch(e) {}
    });
  });

  console.log('Connected!\n');

  try {
    // === 1. Enable Page domain ===
    console.log('Enabling Page domain...');
    await cdpCall(ws, 'Page.enable');
    console.log('  OK\n');

    // === 2. Navigate to home tab ===
    console.log('switchTab to pages/index/index...');
    const navigateResult = await cdpCall(ws, 'Page.navigate', { url: 'pages/index/index' });
    console.log('  Navigate result:', JSON.stringify(navigateResult).slice(0,200));
    console.log('');

    // === 3. Evaluate JS to check page ===
    console.log('Evaluating JS...');
    const evalResult = await cdpCall(ws, 'Runtime.evaluate', {
      expression: `
        (function() {
          const page = getCurrentPages ? getCurrentPages() : [];
          if (page.length > 0) {
            const p = page[page.length-1];
            return JSON.stringify({
              route: p.route,
              data: JSON.stringify(p.data),
              pageLoading: p.data.pageLoading,
              pageError: p.data.pageError
            });
          }
          return 'no pages';
        })()
      `,
      returnByValue: true,
    });
    console.log('  Evaluate:', JSON.stringify(evalResult).slice(0,500));
    console.log('');

    // === 4. Screenshot (via CDP) ===
    console.log('Screenshot...');
    const ssResult = await cdpCall(ws, 'Page.captureScreenshot', { format: 'png' });
    if (ssResult && ssResult.data) {
      const buf = Buffer.from(ssResult.data, 'base64');
      const fs = require('fs');
      fs.writeFileSync('/mnt/e/tarot-miniapp/test_screenshots/cdp_home.png', buf);
      console.log(`  Screenshot saved: ${buf.length} bytes`);
    } else {
      console.log('  Screenshot failed:', JSON.stringify(ssResult).slice(0,200));
    }

  } catch(e) {
    console.error('Error:', e.message);
  }

  ws.close();
  proc.kill();
  console.log('\nDone.');
})();
