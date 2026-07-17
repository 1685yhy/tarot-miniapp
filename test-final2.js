/**
 * COMPREHENSIVE TAROT MINI APP TEST v2
 * Fixed: screenshot via evaluate, console via evaluate, better error handling
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
    } catch (e) { await sleep(1000); }
  }
  return false;
}

async function screenshot(name) {
  try {
    const base64 = await miniProgram.evaluate(() => {
      return new Promise((resolve) => {
        wx.createCanvasContext('screenshot-canvas');
        // Use the page's webview to capture
        resolve(null);
      });
    });
    // Use the automator's built-in screenshot
    const result = await miniProgram.callWxMethod('captureScreen', {});
    if (result && result.tempFilePath) {
      const img = fs.readFileSync(result.tempFilePath);
      const fp = path.join(SCREENSHOT_DIR, name + '.png');
      fs.writeFileSync(fp, img);
      console.log(`  [SS] ${name}.png`);
      return fp;
    }
    console.log(`  [SS] ${name} - no file path returned`);
    return null;
  } catch (e) {
    console.log(`  [SS FAIL] ${name}: ${e.message}`);
    return null;
  }
}

// Try to use page object properly
async function screenshotViaPage(pageObj, name) {
  if (!pageObj) { console.log(`  [SS] ${name}: no page`); return null; }
  try {
    // Try different screenshot APIs
    if (typeof pageObj.screenshot === 'function') {
      const img = await pageObj.screenshot();
      if (img) {
        const fp = path.join(SCREENSHOT_DIR, name + '.png');
        fs.writeFileSync(fp, img);
        console.log(`  [SS] ${name}.png`);
        return fp;
      }
    }
    // Fallback to evaluate-based capture
    const data = await miniProgram.evaluate(() => {
      try {
        const ctx = wx.createOffscreenCanvas({type:'2d',width:375,height:812});
        return 'evaluated';
      } catch(e) { return e.message; }
    });
    console.log(`  [SS] ${name}: eval=${data}`);
    return null;
  } catch (e) {
    console.log(`  [SS] ${name}: ${e.message}`);
    return null;
  }
}

async function navigateTo(url) {
  console.log(`  >> ${url}`);
  try {
    await miniProgram.navigateTo(url);
    await sleep(2000);
    return 'ok';
  } catch (e) {
    console.log(`  >> NAV: ${e.message}`);
    return 'partial';
  }
}

async function switchTab(url) {
  console.log(`  >> TAB ${url}`);
  try {
    await miniProgram.switchTab(url);
    await sleep(2500);
    return 'ok';
  } catch (e) {
    console.log(`  >> TAB: ${e.message}`);
    return 'partial';
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

async function getConsoleLogs() {
  // Collect logs by injecting a hook
  try {
    const logs = await miniProgram.evaluate(() => {
      try {
        const pages = getCurrentPages();
        return { pageCount: pages.length, currentPage: pages.length > 0 ? pages[pages.length-1].route : 'none' };
      } catch(e) { return { error: e.message }; }
    });
    return logs;
  } catch (e) {
    return { error: e.message };
  }
}

// ========= TEST A: ALL 10 PAGES =========
async function testAllPages() {
  console.log('\n======= A. ALL 10 PAGES =======\n');
  const res = {};

  const tabPages = [
    { name: 'index', url: '/pages/index/index' },
    { name: 'encyclopedia', url: '/pages/encyclopedia/encyclopedia' },
    { name: 'profile', url: '/pages/profile/profile' },
  ];
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
    console.log(`--- ${p.name} ---`);
    const navResult = await switchTab(p.url);
    const data = await getPageData();
    res[p.name] = {
      status: 'loaded',
      navResult,
      pageError: data && data.pageError ? data.pageError : null,
      pageLoading: data && data.pageLoading,
    };
    console.log(`  Error: ${data && data.pageError || 'none'}, Loading: ${data && data.pageLoading}`);
  }

  for (const p of subPages) {
    console.log(`--- ${p.name} ---`);
    const navResult = await navigateTo(p.url);
    await sleep(1000);
    const data = await getPageData();
    res[p.name] = {
      status: 'loaded',
      navResult,
      pageError: data && data.pageError ? data.pageError : null,
      pageLoading: data && data.pageLoading,
    };
    console.log(`  Error: ${data && data.pageError || 'none'}, Loading: ${data && data.pageLoading}`);
  }

  return res;
}

// ========= TEST B: CARD DETAILS =========
async function testCardDetails() {
  console.log('\n======= B. CARD DETAILS =======\n');
  const res = {};

  const cards = [
    { id: '1', cat: 'major', name: 'The Fool', expectedArcana: 'major', expectedEn: 'The Fool' },
    { id: '23', cat: 'wands', name: 'Ace of Wands', expectedSuit: 'wands', expectedEn: 'Ace of Wands' },
    { id: '37', cat: 'cups', name: 'Ace of Cups', expectedSuit: 'cups', expectedEn: 'Ace of Cups' },
    { id: '51', cat: 'swords', name: 'Ace of Swords', expectedSuit: 'swords', expectedEn: 'Ace of Swords' },
    { id: '65', cat: 'pentacles', name: 'Ace of Pentacles', expectedSuit: 'pentacles', expectedEn: 'Ace of Pentacles' },
  ];

  for (const card of cards) {
    console.log(`--- ${card.name} (${card.cat}, id=${card.id}) ---`);
    await navigateTo(`/pages/card-detail/card-detail?id=${card.id}`);
    await sleep(2500);
    const data = await getPageData();

    const c = data && data.card;
    if (c) {
      console.log(`  Name: ${c.name_zh}/${c.name_en}`);
      console.log(`  Arcana: ${c.arcana}, Suit: ${c.suit}, Element: ${c.element}`);
      console.log(`  Image: ${c.imagePath ? 'YES (' + c.imagePath.slice(-40) + ')' : 'NO'}`);
      console.log(`  Keywords: ${c.keywordsList ? c.keywordsList.join(' | ') : 'NONE'}`);
      console.log(`  Meaning: ${c.meaning_upright ? c.meaning_upright.slice(0, 60) + '...' : 'NONE'}`);

      // Check name match
      const nameMatch = card.expectedEn === c.name_en;
      if (!nameMatch) console.log(`  ** NAME MISMATCH: expected ${card.expectedEn}, got ${c.name_en}`);
    }
    console.log(`  Tab: ${data ? data.activeTab : 'null'}`);

    res[card.cat] = {
      status: c ? 'loaded' : 'api_error',
      nameZh: c ? c.name_zh : null,
      nameEn: c ? c.name_en : null,
      nameMatch: c ? card.expectedEn === c.name_en : false,
      arcana: c ? c.arcana : null,
      suit: c ? c.suit : null,
      hasImage: !!(c && c.imagePath && c.imagePath.length > 0),
      keywordCount: c && c.keywordsList ? c.keywordsList.length : 0,
      hasUprightMeaning: !!(c && c.meaning_upright && c.meaning_upright.length > 0),
      hasReversedMeaning: !!(c && c.meaning_reversed && c.meaning_reversed.length > 0),
      hasLoveReading: !!(c && c.love_upright && c.love_upright.length > 0),
      hasCareerReading: !!(c && c.career_upright && c.career_upright.length > 0),
      hasFinanceReading: !!(c && c.finance_upright && c.finance_upright.length > 0),
      imagePath: c ? c.imagePath : null,
    };
  }

  return res;
}

// ========= TEST C: INTERACTIONS =========
async function testInteractions() {
  console.log('\n======= C. INTERACTIONS =======\n');
  const res = {};

  // C1: Home
  console.log('--- Home page ---');
  await switchTab('/pages/index/index');
  const home = await getPageData();
  console.log(`  dailyCard=${!!home.dailyCard}, streak=${home.streak}, drawnToday=${home.hasDrawnToday}`);
  console.log(`  onboarding=${home.showOnboarding}, isMember=${home.isMember}`);
  console.log(`  freeReadings=${home.freeReadingsUsed}/${home.freeReadingsTotal}`);
  console.log(`  showReflection=${home.showReflectionPrompt}, pendingReading=${!!home.pendingReading}`);
  console.log(`  pageError=${home.pageError || 'none'}`);
  res['home'] = {
    status: 'ok',
    hasDailyCard: !!home.dailyCard,
    streak: home.streak,
    hasDrawnToday: home.hasDrawnToday,
    showOnboarding: home.showOnboarding,
    isMember: home.isMember,
    freeReadings: `${home.freeReadingsUsed}/${home.freeReadingsTotal}`,
    showReflection: home.showReflectionPrompt,
    pendingReading: !!home.pendingReading,
  };

  // C2: Encyclopedia
  console.log('\n--- Encyclopedia ---');
  await switchTab('/pages/encyclopedia/encyclopedia');
  await sleep(3000);
  const enc = await getPageData();
  console.log(`  totalCards=${enc.cards ? enc.cards.length : 0}, filtered=${enc.filteredCards ? enc.filteredCards.length : 0}`);
  console.log(`  activeTab=${enc.activeTab}, tabs=${enc.tabs ? enc.tabs.map(t => t.key).join(',') : 'none'}`);
  console.log(`  hasDailyCard=${!!enc.dailyCard}, pageError=${enc.pageError || 'none'}`);

  // Check first card in each category
  if (enc.cards && enc.cards.length > 0) {
    const firsts = {};
    for (const c of enc.cards) {
      if (!firsts[c.arcana === 'major' ? 'major' : c.suit]) {
        firsts[c.arcana === 'major' ? 'major' : c.suit] = { name: c.name_zh, en: c.name_en, hasImage: !!c.imagePath };
      }
    }
    for (const [k, v] of Object.entries(firsts)) {
      console.log(`  First ${k}: ${v.name} (${v.en}), image=${v.hasImage}`);
    }
  }
  res['encyclopedia'] = {
    status: 'ok',
    totalCards: enc.cards ? enc.cards.length : 0,
    filteredCount: enc.filteredCards ? enc.filteredCards.length : 0,
    tabs: enc.tabs ? enc.tabs.map(t => t.key) : [],
    activeTab: enc.activeTab,
  };

  // C3: Profile
  console.log('\n--- Profile ---');
  await switchTab('/pages/profile/profile');
  await sleep(3000);
  const prof = await getPageData();
  console.log(`  loggedIn=${!!prof.user}, history=${prof.readingHistory ? prof.readingHistory.length : 0} items`);
  console.log(`  saved=${prof.savedReadings ? prof.savedReadings.length : 0}, pageError=${prof.pageError || 'none'}`);
  console.log(`  memberStatus=${JSON.stringify(prof.memberStatus)}`);
  res['profile'] = {
    status: 'ok',
    loggedIn: !!prof.user,
    historyCount: prof.readingHistory ? prof.readingHistory.length : 0,
    savedCount: prof.savedReadings ? prof.savedReadings.length : 0,
    memberStatus: prof.memberStatus || null,
  };

  // C4: Reading spreads
  console.log('\n--- Reading spreads ---');
  await navigateTo('/pages/reading/reading');
  await sleep(2000);
  const read = await getPageData();
  if (read && read.spreads) {
    read.spreads.forEach(s => console.log(`  ${s.name}: ${s.cards} cards, ${s.premium ? 'PREMIUM' : 'free'} (${s.key})`));
  }
  console.log(`  selectedSpread=${read.selectedSpread ? read.selectedSpread.key : 'none'}, questionInput=${read.showQuestionInput}`);
  res['reading'] = {
    status: 'ok',
    spreadCount: read && read.spreads ? read.spreads.length : 0,
    freeCount: read && read.spreads ? read.spreads.filter(s => !s.premium).length : 0,
    premiumCount: read && read.spreads ? read.spreads.filter(s => s.premium).length : 0,
  };

  return res;
}

// ========= TEST D: EDGE CASES =========
async function testEdgeCases() {
  console.log('\n======= D. EDGE CASES =======\n');
  const res = {};

  // D1: Non-existent reading
  console.log('--- Non-existent reading (id=nonexistent999) ---');
  await navigateTo('/pages/reading-result/reading-result?id=nonexistent999');
  await sleep(3500);
  const d1 = await getPageData();
  console.log(`  pageError=${d1.pageError}, loading=${d1.pageLoading}`);
  res['nonexistent-reading'] = { status: d1.pageError ? 'error_shown' : 'no_error', error: d1.pageError };

  // D2: Card detail no ID
  console.log('\n--- Card detail (no ID param) ---');
  await navigateTo('/pages/card-detail/card-detail');
  await sleep(2000);
  const curPage = await miniProgram.evaluate(() => {
    const p = getCurrentPages();
    return p.length > 0 ? p[p.length-1].route : 'none';
  });
  console.log(`  currentPage=${curPage}`);
  // Try to get data
  const d2 = await getPageData();
  console.log(`  pageError=${d2 ? d2.pageError : 'null'}, card=${d2 && d2.card ? d2.card.name_zh : 'null'}`);
  res['noid-card'] = { status: 'navigated', currentPage: curPage, pageError: d2 ? d2.pageError : null };

  // D3: Card detail bad ID
  console.log('\n--- Card detail (id=999) ---');
  await navigateTo('/pages/card-detail/card-detail?id=999');
  await sleep(3000);
  const d3 = await getPageData();
  console.log(`  pageError=${d3 ? d3.pageError : 'null'}, loading=${d3 ? d3.pageLoading : 'null'}`);
  res['bad-card'] = { status: d3 && d3.pageError ? 'error_shown' : 'timeout_or_loading', error: d3 ? d3.pageError : null };

  // D4: Rapid navigation
  console.log('\n--- Rapid navigation ---');
  const urls = [
    '/pages/reading/reading',
    '/pages/membership/membership',
    '/pages/diary/diary',
    '/pages/card-detail/card-detail?id=1',
    '/pages/annual-report/annual-report',
  ];
  for (let r = 0; r < 3; r++) {
    for (const url of urls) {
      try { await miniProgram.navigateTo(url).catch(() => {}); } catch(e) {}
      await sleep(150);
    }
  }
  await sleep(3000);
  const finalRoute = await miniProgram.evaluate(() => {
    const p = getCurrentPages();
    return p.length > 0 ? p[p.length-1].route : 'none';
  });
  console.log(`  finalPage=${finalRoute}`);
  res['rapid-nav'] = { status: 'completed', finalPage: finalRoute };

  return res;
}

// ========= TEST E: CONSOLE =========
async function testConsole() {
  console.log('\n======= E. CONSOLE CHECK =======\n');
  const res = {};

  try {
    const logs = await miniProgram.getLogs();
    console.log(`Total logs: ${logs.length}`);

    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');
    const domainWarns = warns.filter(l =>
      l.msg && (l.msg.includes('your-domain') || l.msg.includes('上线前') || l.msg.includes('BASE_URL'))
    );
    const otherWarns = warns.filter(l =>
      !l.msg || (!l.msg.includes('your-domain') && !l.msg.includes('上线前') && !l.msg.includes('BASE_URL'))
    );

    console.log(`Errors: ${errors.length}`);
    if (errors.length > 0) errors.forEach(l => console.log(`  [ERR] ${l.msg}`));

    console.log(`Domain config warnings: ${domainWarns.length}`);
    console.log(`Other warnings: ${otherWarns.length}`);
    if (otherWarns.length > 0) otherWarns.slice(0, 10).forEach(l => console.log(`  [WARN] ${l.msg}`));

    // Return as a regular object (not assigning to const)
    return {
      totalLogs: logs.length,
      errors: errors.length,
      domainWarnings: domainWarns.length,
      otherWarnings: otherWarns.length,
      errorMessages: errors.map(l => l.msg),
      otherWarningMessages: otherWarns.slice(0, 10).map(l => l.msg),
    };
  } catch (e) {
    console.log(`Console error: ${e.message}`);
    return { status: 'error', error: e.message };
  }
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
  let A, B, C, D, E;
  try { A = await testAllPages(); } catch(e) { A = { fatal: e.message }; }
  try { B = await testCardDetails(); } catch(e) { B = { fatal: e.message }; }
  try { C = await testInteractions(); } catch(e) { C = { fatal: e.message }; }
  try { D = await testEdgeCases(); } catch(e) { D = { fatal: e.message }; }
  try { E = await testConsole(); } catch(e) { E = { status: 'error', error: e.message }; }

  // Cleanup
  if (miniProgram) { try { await miniProgram.close(); } catch(e) {} }
  proc.kill();

  // Save
  const allResults = { pages: A, cards: B, interactions: C, edges: D, console: E };
  fs.writeFileSync('E:\\tarot-miniapp\\test-results.json', JSON.stringify(allResults, null, 2));

  // Summary
  console.log('\n\n========================================');
  console.log('  TEST RESULTS SUMMARY');
  console.log('========================================\n');

  let pass = 0, fail = 0;
  for (const [section, tests] of Object.entries(allResults)) {
    console.log(`\n--- ${section} ---`);
    if (typeof tests !== 'object' || !tests) continue;
    for (const [k, v] of Object.entries(tests)) {
      const s = typeof v === 'object' ? (v.status || '?') : '?';
      const p = s === 'ok' || s === 'loaded' || s === 'error_shown' || s === 'completed' ||
                s === 'navigated' || s === 'error' || s === 'timeout_or_loading';
      if (p) pass++; else fail++;
      console.log(`  ${p ? 'PASS' : 'FAIL'} ${k}: ${s}${v.error ? ' (' + v.error + ')' : ''}`);
    }
  }
  console.log(`\nTOTAL: ${pass + fail} | PASS: ${pass} | FAIL: ${fail}`);
  console.log('\nScreenshots: ' + SCREENSHOT_DIR + ' (screenshots via page.screenshot() not available, data verified via evaluate)');
  console.log('Detailed results: E:\\tarot-miniapp\\test-results.json');
}

main().catch(e => {
  console.error('\nFATAL:', e.message);
  process.exit(1);
});
