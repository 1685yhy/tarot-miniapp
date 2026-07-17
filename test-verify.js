/**
 * Final verification - console logs, screenshots, and remaining card checks
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const auto = require(path.join('E:\\', 'tarot-miniapp', 'node_modules', 'miniprogram-automator'));

const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const AUTO_PORT = 9422;
const SS_DIR = 'E:\\tarot-miniapp\\test-screenshots';
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR);

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function waitForPort(port) {
  for (let i = 0; i < 40; i++) {
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

async function takeScreenshot(mp, name) {
  try {
    const buf = await mp.screenshot();
    if (buf && buf.length > 0) {
      const fp = path.join(SS_DIR, name + '.png');
      fs.writeFileSync(fp, buf);
      console.log(`  [SS] ${name}.png (${buf.length} bytes)`);
      return fp;
    }
    console.log(`  [SS] ${name}: empty screenshot`);
    return null;
  } catch (e) {
    console.log(`  [SS] ${name}: ${e.message}`);
    return null;
  }
}

async function main() {
  // Close existing
  try {
    const c = spawn('cmd.exe', ['/c', CLI_PATH, 'quit'], { stdio: 'ignore', cwd: 'E:\\', windowsVerbatimArguments: true });
    await new Promise(r => c.on('exit', r));
  } catch(e) {}
  await sleep(3000);

  const proc = spawn('cmd.exe', ['/c', CLI_PATH, 'auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'], cwd: 'E:\\', windowsVerbatimArguments: true,
  });

  console.log('Waiting for automation...');
  await waitForPort(AUTO_PORT);
  const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT });
  console.log('Connected!');

  // Navigate through pages and take screenshots
  const pages = [
    { type: 'tab', url: '/pages/index/index', name: 'page-index' },
    { type: 'tab', url: '/pages/encyclopedia/encyclopedia', name: 'page-encyclopedia' },
    { type: 'tab', url: '/pages/profile/profile', name: 'page-profile' },
    { type: 'nav', url: '/pages/reading/reading', name: 'page-reading' },
  ];

  for (const p of pages) {
    console.log(`\n--- ${p.name} ---`);
    try {
      if (p.type === 'tab') await mp.switchTab(p.url).catch(() => {});
      else await mp.navigateTo(p.url).catch(() => {});
      await sleep(3000);
    } catch(e) {}
    await takeScreenshot(mp, p.name);
  }

  // Card detail screenshots
  const cards = [
    { id: 1, name: 'card-major-fool' },
    { id: 23, name: 'card-wands-acewands' },
    { id: 37, name: 'card-cups-acecups' },
    { id: 51, name: 'card-swords-aceswords' },
    { id: 65, name: 'card-pentacles-acepentacles' },
  ];

  for (const card of cards) {
    console.log(`\n--- ${card.name} (id=${card.id}) ---`);
    try {
      await mp.navigateTo('/pages/card-detail/card-detail?id=' + card.id).catch(() => {});
      await sleep(3000);
    } catch(e) {}
    await takeScreenshot(mp, card.name);
    // Verify data
    const data = await mp.evaluate(() => {
      const pages = getCurrentPages();
      if (!pages || pages.length === 0) return null;
      const d = pages[pages.length - 1].data;
      return d.card ? { nameZh: d.card.name_zh, nameEn: d.card.name_en, keywords: d.card.keywordsList } : null;
    });
    console.log(`  Data: ${JSON.stringify(data)}`);
  }

  // Console logs
  console.log('\n\n========== CONSOLE LOGS ==========');
  try {
    const logs = await mp.getLogs();
    console.log(`Total log entries: ${logs.length}`);

    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');

    console.log(`\nERRORS (${errors.length}):`);
    errors.forEach(l => console.log(`  ${l.msg}`));

    console.log(`\nWARNINGS (${warns.length}):`);
    warns.forEach(l => console.log(`  ${l.msg}`));
  } catch(e) {
    console.log(`getLogs error: ${e.message}`);
    // Try alternative: get logs from the connection
    try {
      const logs = await mp.evaluate(() => {
        // Inject log capture
        const capturedErrors = [];
        const capturedWarns = [];
        const origError = console.error;
        const origWarn = console.warn;
        console.error = function() { capturedErrors.push(Array.from(arguments).join(' ')); origError.apply(console, arguments); };
        console.warn = function() { capturedWarns.push(Array.from(arguments).join(' ')); origWarn.apply(console, arguments); };
        return { capturedErrors: capturedErrors.slice(0, 20), capturedWarns: capturedWarns.slice(0, 20) };
      });
      console.log('Captured via eval:', JSON.stringify(logs));
    } catch(e2) {
      console.log(`Alt error: ${e2.message}`);
    }
  }

  await mp.close();
  proc.kill();
  console.log('\nDone! Screenshots saved to', SS_DIR);
}

main().catch(console.error);
