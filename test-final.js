/**
 * FINAL Comprehensive Tarot Mini App Test
 * Uses correct spawning and miniprogram-automator APIs
 */
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const net = require('net');
const auto = require(path.join('E:\\', 'tarot-miniapp', 'node_modules', 'miniprogram-automator'));

const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const AUTO_PORT = 9420;
const SCREENSHOT_DIR = 'E:\\tarot-miniapp\\test-screenshots';
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR);

let miniProgram = null;
const results = {};

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
    } catch (e) {
      await sleep(1000);
    }
  }
  return false;
}

async function screenshot(name) {
  try {
    const page = await miniProgram.currentPage();
    if (!page) return null;
    const img = await page.screenshot();
    const fp = path.join(SCREENSHOT_DIR, name + '.png');
    fs.writeFileSync(fp, img);
    console.log(`  [SS] ${name}.png`);
    return fp;
  } catch (e) {
    console.log(`  [SS FAIL] ${name}: ${e.message}`);
    return null;
  }
}

async function navigateTo(url) {
  console.log(`  >> navigateTo ${url}`);
  try {
    await miniProgram.navigateTo(url);
    await sleep(2000);
    return await miniProgram.currentPage();
  } catch (e) {
    console.log(`  >> NAV ERR: ${e.message}`);
    try { return await miniProgram.currentPage(); } catch(e2) { return null; }
  }
}

async function switchTab(url) {
  console.log(`  >> switchTab ${url}`);
  try {
    await miniProgram.switchTab(url);
    await sleep(2500);
    return await miniProgram.currentPage();
  } catch (e) {
    console.log(`  >> TAB ERR: ${e.message}`);
    try { return await miniProgram.currentPage(); } catch(e2) { return null; }
  }
}

async function getPageData() {
  try {
    return await miniProgram.evaluate(() => {
      const pages = getCurrentPages();
      if (!pages || pages.length === 0) return null;
      const d = pages[pages.length - 1].data;
      return JSON.parse(JSON.stringify(d));
    });
  } catch (e) {
    return { error: e.message };
  }
}

// ========= TEST A: ALL 10 PAGES =========
async function testAllPages() {
  console.log('\n======= A. ALL 10 PAGES =======\n');
  const res = {};

  // Tab pages (use switchTab)
  const tabPages = [
    { name: 'index', url: '/pages/index/index' },
    { name: 'encyclopedia', url: '/pages/encyclopedia/encyclopedia' },
    { name: 'profile', url: '/pages/profile/profile' },
  ];

  // Non-tab pages (use navigateTo)
  const subPages = [
    { name: 'reading', url: '/pages/reading/reading' },
    { name: 'reading-result', url: '/pages/reading-result/reading-result?id=test' },
    { name: 'card-detail', url: '/pages/card-detail/card-detail?id=1' },
    { name: 'chat', url: '/pages/chat/chat?readingId=test' },
    { name: 'membership', url: '/pages/membership/membership' },
    { name: 'diary', url: '/pages/diary/diary' },
    { name: 'annual-report', url: '/pages/annual-report/annual-report' },
  ];

  for (const p of tabPages) {
    console.log(`--- ${p.name} (tab) ---`);
    try {
      const page = await switchTab(p.url);
      if (!page) { res[p.name] = { status: 'error', error: 'no page' }; continue; }
      const data = await getPageData();
      res[p.name] = {
        status: 'loaded',
        path: page.path,
        pageLoading: data && data.pageLoading,
        pageError: data && data.pageError ? data.pageError : null,
      };
      console.log(`  Path: ${page.path}, Error: ${data && data.pageError || 'none'}, Loading: ${data && data.pageLoading}`);
      await screenshot(`page-${p.name}`);
    } catch (e) {
      console.log(`  FAIL: ${e.message}`);
      res[p.name] = { status: 'crash', error: e.message };
    }
  }

  for (const p of subPages) {
    console.log(`--- ${p.name} ---`);
    try {
      const page = await navigateTo(p.url);
      if (!page) { res[p.name] = { status: 'error', error: 'no page' }; continue; }
      const data = await getPageData();
      res[p.name] = {
        status: 'loaded',
        path: page.path,
        pageLoading: data && data.pageLoading,
        pageError: data && data.pageError ? data.pageError : null,
      };
      console.log(`  Path: ${page.path}, Error: ${data && data.pageError || 'none'}, Loading: ${data && data.pageLoading}`);
      await screenshot(`page-${p.name}`);
    } catch (e) {
      console.log(`  FAIL: ${e.message}`);
      res[p.name] = { status: 'crash', error: e.message };
    }
  }

  return res;
}

// ========= TEST B: CARD DETAILS =========
async function testCardDetails() {
  console.log('\n======= B. CARD DETAILS =======\n');
  const res = {};

  const cards = [
    { id: '1', cat: 'major', name: 'The Fool' },
    { id: '23', cat: 'wands', name: 'Ace of Wands' },
    { id: '37', cat: 'cups', name: 'Ace of Cups' },
    { id: '51', cat: 'swords', name: 'Ace of Swords' },
    { id: '65', cat: 'pentacles', name: 'Ace of Pentacles' },
  ];

  for (const card of cards) {
    console.log(`--- ${card.name} (${card.cat}, id=${card.id}) ---`);
    try {
      await navigateTo(`/pages/card-detail/card-detail?id=${card.id}`);
      await sleep(2000);
      const data = await getPageData();

      const c = data && data.card;
      console.log(`  Card: ${c ? c.name_zh + '/' + c.name_en : 'null'}`);
      console.log(`  Tab: ${data ? data.activeTab : 'null'}`);
      console.log(`  Image: ${c && c.imagePath ? 'YES ' + c.imagePath.slice(-40) : 'NO'}`);
      console.log(`  Keywords: ${c && c.keywordsList ? c.keywordsList.join(', ') : 'NONE'}`);

      await screenshot(`card-${card.cat}`);

      res[card.cat] = {
        status: c ? 'loaded' : 'api_error',
        nameZh: c ? c.name_zh : null,
        nameEn: c ? c.name_en : null,
        arcana: c ? c.arcana : null,
        suit: c ? c.suit : null,
        hasImage: !!(c && c.imagePath && c.imagePath.length > 0),
        hasKeywords: !!(c && c.keywordsList && c.keywordsList.length > 0),
        keywordCount: c && c.keywordsList ? c.keywordsList.length : 0,
        hasReversedMeaning: !!(c && c.meaning_reversed && c.meaning_reversed.length > 0),
      };
    } catch (e) {
      console.log(`  FAIL: ${e.message}`);
      res[card.cat] = { status: 'crash', error: e.message };
    }
  }

  return res;
}

// ========= TEST C: INTERACTIONS =========
async function testInteractions() {
  console.log('\n======= C. INTERACTIONS =======\n');
  const res = {};

  // C1: Home page
  console.log('--- Home: daily card, streak, spreads ---');
  try {
    await switchTab('/pages/index/index');
    await sleep(1500);
    const d = await getPageData();
    console.log(`  dailyCard=${!!d.dailyCard}, streak=${d.streak}, hasDrawnToday=${d.hasDrawnToday}`);
    console.log(`  showOnboarding=${d.showOnboarding}, pendingReading=${!!d.pendingReading}`);
    console.log(`  freeReadings=${d.freeReadingsUsed}/${d.freeReadingsTotal}, isMember=${d.isMember}`);
    await screenshot('interact-home');
    res['home'] = {
      status: 'ok',
      hasOnboarding: d.showOnboarding,
      hasDailyCard: !!d.dailyCard,
      streak: d.streak,
      hasDrawnToday: d.hasDrawnToday,
      pendingReading: !!d.pendingReading,
    };
  } catch (e) { res['home'] = { status: 'error', error: e.message }; }

  // C2: Encyclopedia interaction
  console.log('\n--- Encyclopedia: filters and search ---');
  try {
    await switchTab('/pages/encyclopedia/encyclopedia');
    await sleep(3000);
    const d = await getPageData();
    console.log(`  totalCards=${d.cards ? d.cards.length : 0}, filtered=${d.filteredCards ? d.filteredCards.length : 0}`);
    console.log(`  activeTab=${d.activeTab}, tabs=${d.tabs ? d.tabs.map(t => t.key).join(',') : 'none'}`);
    console.log(`  hasSearch=${d.searchKeyword !== undefined}, pageError=${d.pageError || 'none'}`);
    await screenshot('interact-encyclopedia');
    res['encyclopedia'] = {
      status: 'ok',
      totalCards: d.cards ? d.cards.length : 0,
      tabs: d.tabs ? d.tabs.map(t => t.key) : [],
      activeTab: d.activeTab,
    };
  } catch (e) { res['encyclopedia'] = { status: 'error', error: e.message }; }

  // C3: Profile interaction
  console.log('\n--- Profile: menus and history ---');
  try {
    await switchTab('/pages/profile/profile');
    await sleep(3000);
    const d = await getPageData();
    console.log(`  user=${!!d.user}, history=${d.readingHistory ? d.readingHistory.length : 0} items`);
    console.log(`  savedReadings=${d.savedReadings ? d.savedReadings.length : 0}, pageError=${d.pageError || 'none'}`);
    await screenshot('interact-profile');
    res['profile'] = {
      status: 'ok',
      loggedIn: !!d.user,
      historyCount: d.readingHistory ? d.readingHistory.length : 0,
      savedCount: d.savedReadings ? d.savedReadings.length : 0,
    };
  } catch (e) { res['profile'] = { status: 'error', error: e.message }; }

  // C4: Reading interaction
  console.log('\n--- Reading: spread selection ---');
  try {
    await navigateTo('/pages/reading/reading');
    await sleep(2000);
    const d = await getPageData();
    if (d && d.spreads) {
      console.log(`  spreadsCount=${d.spreads.length}`);
      d.spreads.forEach(s => console.log(`    ${s.name}: ${s.key}, ${s.cards}cards, premium=${!!s.premium}`));
      const free = d.spreads.filter(s => !s.premium).length;
      const premium = d.spreads.filter(s => s.premium).length;
      console.log(`  Free: ${free}, Premium: ${premium}`);
    }
    await screenshot('interact-reading');
    res['reading'] = {
      status: 'ok',
      spreadCount: d && d.spreads ? d.spreads.length : 0,
      freeCount: d && d.spreads ? d.spreads.filter(s => !s.premium).length : 0,
      premiumCount: d && d.spreads ? d.spreads.filter(s => s.premium).length : 0,
      hasQuestionInput: !!(d && d.showQuestionInput),
    };
  } catch (e) { res['reading'] = { status: 'error', error: e.message }; }

  return res;
}

// ========= TEST D: EDGE CASES =========
async function testEdgeCases() {
  console.log('\n======= D. EDGE CASES =======\n');
  const res = {};

  // D1: Non-existent reading result
  console.log('--- Non-existent reading result ---');
  try {
    await navigateTo('/pages/reading-result/reading-result?id=nonexistent999');
    await sleep(3500);
    const d = await getPageData();
    console.log(`  error=${d.pageError}, loading=${d.pageLoading}`);
    await screenshot('edge-nonexistent-reading');
    res['nonexistent-reading'] = {
      status: d && d.pageError ? 'error_shown_as_expected' : 'no_error',
      errorMessage: d ? d.pageError : null,
    };
  } catch (e) { res['nonexistent-reading'] = { status: 'crash', error: e.message }; }

  // D2: Card detail - no ID
  console.log('\n--- Card detail - no ID ---');
  try {
    await navigateTo('/pages/card-detail/card-detail');
    await sleep(2000);
    const page = await miniProgram.currentPage();
    console.log(`  pagePath=${page ? page.path : 'null'}`);
    await screenshot('edge-noid-card');
    res['noid-card'] = { status: 'navigated', path: page ? page.path : null };
  } catch (e) { res['noid-card'] = { status: 'crash', error: e.message }; }

  // D3: Card detail - bad ID
  console.log('\n--- Card detail - bad ID 999 ---');
  try {
    await navigateTo('/pages/card-detail/card-detail?id=999');
    await sleep(3000);
    const d = await getPageData();
    console.log(`  error=${d ? d.pageError : 'null'}, loading=${d ? d.pageLoading : 'null'}`);
    await screenshot('edge-bad-card');
    res['bad-card'] = {
      status: d && d.pageError ? 'error_shown' : 'no_error',
      errorMessage: d ? d.pageError : null,
    };
  } catch (e) { res['bad-card'] = { status: 'crash', error: e.message }; }

  // D4: Rapid navigation
  console.log('\n--- Rapid navigation (3 rounds x 4 pages) ---');
  try {
    const urls = [
      '/pages/reading/reading',
      '/pages/membership/membership',
      '/pages/diary/diary',
      '/pages/reading-result/reading-result?id=test',
    ];
    for (let r = 0; r < 3; r++) {
      for (const url of urls) {
        try { await miniProgram.navigateTo(url).catch(() => {}); } catch(e) {}
        await sleep(200);
      }
    }
    await sleep(2500);
    const page = await miniProgram.currentPage();
    console.log(`  finalPage=${page ? page.path : 'null'}`);
    await screenshot('edge-rapid-nav');
    res['rapid-nav'] = { status: 'completed', finalPage: page ? page.path : null };
  } catch (e) { res['rapid-nav'] = { status: 'crash', error: e.message }; }

  return res;
}

// ========= TEST E: CONSOLE =========
async function testConsole() {
  console.log('\n======= E. CONSOLE CHECK =======\n');
  const res = {};

  try {
    const logs = await miniProgram.getLogs();
    console.log(`Total log entries: ${logs.length}`);

    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');
    const domainWarns = warns.filter(l =>
      l.msg && (l.msg.includes('your-domain') || l.msg.includes('上线前') || l.msg.includes('BASE_URL'))
    );
    const otherWarns = warns.filter(l =>
      !l.msg || (!l.msg.includes('your-domain') && !l.msg.includes('上线前') && !l.msg.includes('BASE_URL'))
    );

    console.log(`\nErrors: ${errors.length}`);
    if (errors.length > 0) errors.forEach(l => console.log(`  [ERR] ${l.msg}`));

    console.log(`\nDomain config warnings (expected): ${domainWarns.length}`);
    console.log(`Other warnings: ${otherWarns.length}`);
    if (otherWarns.length > 0) otherWarns.slice(0, 10).forEach(l => console.log(`  [WARN] ${l.msg}`));

    res = {
      totalLogs: logs.length,
      errors: errors.length,
      domainWarnings: domainWarns.length,
      otherWarnings: otherWarns.length,
      errorMessages: errors.map(l => l.msg),
      otherWarningMessages: otherWarns.slice(0, 10).map(l => l.msg),
    };
  } catch (e) {
    console.log(`Console check error: ${e.message}`);
    res = { status: 'error', error: e.message };
  }

  return res;
}

// ========= MAIN =========
async function main() {
  console.log('========================================');
  console.log('  TAROT MINI APP - COMPREHENSIVE TEST');
  console.log('  Project: ' + PROJECT_PATH);
  console.log('========================================\n');

  // Start DevTools
  console.log('[SETUP] Launching DevTools...');
  const proc = spawn('cmd.exe', ['/c', CLI_PATH, 'auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    cwd: 'E:\\',
    windowsVerbatimArguments: true,
  });
  proc.stdout.on('data', d => {});
  proc.stderr.on('data', d => {});

  console.log('[SETUP] Waiting for automation port...');
  const opened = await waitForPort(AUTO_PORT, 40000);
  if (!opened) throw new Error('Port ' + AUTO_PORT + ' did not open within 40s');

  console.log('[SETUP] Connecting automator...');
  miniProgram = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT });
  console.log('[SETUP] Connected!\n');

  // Run tests
  const A = await testAllPages();
  const B = await testCardDetails();
  const C = await testInteractions();
  const D = await testEdgeCases();
  const E = await testConsole();

  // Cleanup
  if (miniProgram) { try { await miniProgram.close(); } catch(e) {} }
  proc.kill();

  // Save results
  const allResults = { pages: A, cards: B, interactions: C, edges: D, console: E };
  fs.writeFileSync('E:\\tarot-miniapp\\test-results.json', JSON.stringify(allResults, null, 2));

  // Print summary
  console.log('\n\n========================================');
  console.log('  TEST RESULTS SUMMARY');
  console.log('========================================\n');

  let passCount = 0, failCount = 0;
  const printSection = (label, section) => {
    console.log(`\n--- ${label} ---`);
    if (typeof section !== 'object') { console.log(`  ${section}`); return; }
    for (const [k, v] of Object.entries(section)) {
      const s = typeof v === 'object' ? (v.status || v) : v;
      if (typeof s === 'string') {
        const pass = s === 'ok' || s === 'loaded' || s === 'completed' ||
                     s === 'error_shown_as_expected' || s === 'error_shown' ||
                     s === 'navigated' || s.includes('expected');
        if (pass) passCount++; else failCount++;
        console.log(`  ${pass ? 'PASS' : 'FAIL'} ${k}: ${s}`);
      }
    }
  };
  printSection('A. All 10 Pages', A);
  printSection('B. Card Details', B);
  printSection('C. Interactions', C);
  printSection('D. Edge Cases', D);
  printSection('E. Console', E);

  console.log(`\n\nTOTAL: ${passCount + failCount} | PASS: ${passCount} | FAIL: ${failCount}`);
  console.log(`\nScreenshots: ${SCREENSHOT_DIR}`);
  console.log('Results: E:\\tarot-miniapp\\test-results.json');
}

main().catch(e => {
  console.error('\nFATAL:', e.message, e.stack);
  process.exit(1);
});
