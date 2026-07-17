/**
 * Debug test - specifically test the failing card IDs and get console logs
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const auto = require(path.join('E:\\', 'tarot-miniapp', 'node_modules', 'miniprogram-automator'));

const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const AUTO_PORT = 9421;  // Use different port to avoid conflict

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForPort(port, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      await new Promise((resolve, reject) => {
        const sock = new net.Socket();
        sock.setTimeout(2000);
        sock.on('connect', () => { sock.destroy(); resolve(); });
        sock.on('error', reject);
        sock.on('timeout', () => { sock.destroy(); reject(new Error('timeout')); });
        sock.connect(port, '127.0.0.1');
      });
      return true;
    } catch (e) { await sleep(1000); }
  }
  return false;
}

async function main() {
  // Close existing
  try {
    const c = spawn('cmd.exe', ['/c', CLI_PATH, 'quit'], { stdio: 'ignore', cwd: 'E:\\', windowsVerbatimArguments: true });
    await new Promise(r => c.on('exit', r));
  } catch(e) {}
  await sleep(3000);

  // Launch
  const proc = spawn('cmd.exe', ['/c', CLI_PATH, 'auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'], cwd: 'E:\\', windowsVerbatimArguments: true,
  });
  proc.stdout.on('data', d => {});
  proc.stderr.on('data', d => {});

  console.log('Waiting for automation...');
  await waitForPort(AUTO_PORT, 40000);
  const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT });
  console.log('Connected!\n');

  // Test 1: Load cards one at a time, starting fresh after each
  const cardIds = [51, 65];
  for (const id of cardIds) {
    console.log(`\n=== Card ID ${id} ===`);

    // Navigate directly from current state
    try {
      await mp.navigateTo('/pages/card-detail/card-detail?id=' + id);
    } catch(e) {
      console.log(`  navigateTo error: ${e.message}`);
    }
    await sleep(3000);

    const data = await mp.evaluate(() => {
      const pages = getCurrentPages();
      if (!pages || pages.length === 0) return null;
      const d = pages[pages.length - 1].data;
      return {
        nameZh: d.card ? d.card.name_zh : null,
        nameEn: d.card ? d.card.name_en : null,
        pageError: d.pageError,
        pageLoading: d.pageLoading,
      };
    });
    console.log(`  Result: ${JSON.stringify(data)}`);
  }

  // Test 2: Console logs - try getting them from wx API
  console.log('\n=== Console logs ===');
  try {
    const logInfo = await mp.evaluate(() => {
      // Collect console logs by wrapping console functions
      const logs = [];
      const origError = console.error;
      console.error = function() {
        logs.push({ level: 'error', msg: Array.from(arguments).join(' ') });
        origError.apply(console, arguments);
      };

      // Return all wx logs
      return {
        captured: logs.slice(0, 20),
        // Try to get system info
        SDKVersion: wx.getSystemInfoSync ? wx.getSystemInfoSync().SDKVersion : 'unknown',
      };
    });
    console.log(`  App info: ${JSON.stringify(logInfo)}`);
  } catch(e) {
    console.log(`  Evaluate error: ${e.message}`);
  }

  // Test 3: Try miniProgram.getLogs (might be available as a method on the connection)
  console.log('\n=== Checking MP methods ===');
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(mp));
  console.log('  MP methods:', methods.join(', '));

  // Actually verify card 51 and 65 work when loaded as first card
  console.log('\n=== Loading cards as the FIRST navigation (fresh state) ===');

  // First go to index
  try { await mp.switchTab('/pages/index/index'); } catch(e) {}
  await sleep(2000);

  // Now go to card 51
  try {
    console.log('\nNavigating to card 51 from index...');
    await mp.navigateTo('/pages/card-detail/card-detail?id=51');
    await sleep(2500);
    const data51 = await mp.evaluate(() => {
      const pages = getCurrentPages();
      if (!pages || pages.length === 0) return null;
      const d = pages[pages.length - 1].data;
      return {
        nameZh: d.card ? d.card.name_zh : null,
        nameEn: d.card ? d.card.name_en : null,
        pageError: d.pageError,
        pageLoading: d.pageLoading,
      };
    });
    console.log(`  Card 51: ${JSON.stringify(data51)}`);
  } catch(e) { console.log(`  Error: ${e.message}`); }

  // Try console logs one more way
  console.log('\n=== Checking console logs via connection ===');
  try {
    if (mp._conn && typeof mp._conn.getLogs === 'function') {
      const logs = await mp._conn.getLogs();
      console.log(`  Logs: ${logs.length}`);
    }
  } catch(e) {
    console.log(`  Connection logs not available: ${e.message}`);
  }

  await mp.close();
  proc.kill();
  console.log('\nDone!');
}

main().catch(console.error);
