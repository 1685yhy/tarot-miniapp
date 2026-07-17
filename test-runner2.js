/**
 * Comprehensive Tarot Mini App Test v2
 * Correctly handles tab pages, correct card IDs, proper API usage
 */

const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const auto = require(path.join('E:\\', 'tarot-miniapp', 'node_modules', 'miniprogram-automator'));

const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const AUTO_PORT = 9420;
const SCREENSHOT_DIR = 'E:\\tarot-miniapp\\test-screenshots';

if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR);

let miniProgram = null;
const results = {};

// ============== HELPERS ==============

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function ensureDevTools() {
  try {
    const closeProc = spawn(CLI_PATH, ['close', '--project', PROJECT_PATH], { shell: true, stdio: 'ignore', cwd: 'E:\\' });
    await new Promise(r => closeProc.on('exit', r));
  } catch(e) {}
  await sleep(3000);

  return new Promise((resolve, reject) => {
    console.log('[SETUP] Launching DevTools with automation...');
    const proc = spawn(CLI_PATH, ['open', '--project', PROJECT_PATH], {
      shell: true, stdio: ['ignore', 'pipe', 'pipe'], cwd: 'E:\\',
    });
    let out = '';
    proc.stdout.on('data', d => { out += d.toString(); });
    proc.stderr.on('data', d => { out += d.toString(); });
    proc.on('exit', () => { console.log('[SETUP] Open complete, waiting for IDE...'); });

    // Wait for IDE then enable auto
    setTimeout(async () => {
      try {
        const autoProc = spawn(CLI_PATH, ['auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
          shell: true, stdio: ['ignore', 'pipe', 'pipe'], cwd: 'E:\\',
        });
        autoProc.stdout.on('data', d => { out += d.toString(); });
        autoProc.stderr.on('data', d => { out += d.toString(); });
        autoProc.on('exit', () => { console.log('[SETUP] Auto command done'); });
      } catch(e) {}

      // Keep trying to connect
      for (let i = 0; i < 30; i++) {
        try {
          console.log(`[SETUP] Connection attempt ${i + 1}...`);
          const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT });
          miniProgram = mp;
          console.log('[SETUP] Connected!');
          resolve(mp);
          return;
        } catch (e) {
          await sleep(2000);
        }
      }
      reject(new Error('Could not connect'));
    }, 5000);
  });
}

async function screenshot(name) {
  try {
    const page = await miniProgram.currentPage();
    if (!page) return null;
    const img = await page.screenshot();
    const filepath = path.join(SCREENSHOT_DIR, name + '.png');
    fs.writeFileSync(filepath, img);
    console.log(`  [SS] ${name}.png`);
    return filepath;
  } catch (e) {
    console.log(`  [SS FAIL] ${name}: ${e.message}`);
    return null;
  }
}

async function navigateTo(url) {
  console.log(`  >> ${url}`);
  try {
    await miniProgram.navigateTo(url);
    await sleep(2000);
    return await miniProgram.currentPage();
  } catch (e) {
    console.log(`  NAV ERR: ${e.message}`);
    // Try to get current page anyway
    try { return await miniProgram.currentPage(); } catch(e2) { return null; }
  }
}

async function switchTab(url) {
  console.log(`  >> switchTab ${url}`);
  try {
    await miniProgram.switchTab(url);
    await sleep(2000);
    return await miniProgram.currentPage();
  } catch (e) {
    console.log(`  TAB ERR: ${e.message}`);
    try { return await miniProgram.currentPage(); } catch(e2) { return null; }
  }
}

async function evaluate(fn, args) {
  try {
    return await miniProgram.evaluate(fn, args);
  } catch (e) {
    return { error: e.message };
  }
}

// ============== TESTS ==============

async function testAllPages() {
  console.log('\n========== A. ALL 10 PAGES ==========\n');
  const pages = [
    { name: 'index', url: '/pages/index/index', tab: true },
    { name: 'encyclopedia', url: '/pages/encyclopedia/encyclopedia', tab: true },
    { name: 'profile', url: '/pages/profile/profile', tab: true },
    { name: 'reading', url: '/pages/reading/reading', tab: false },
    { name: 'reading-result', url: '/pages/reading-result/reading-result?id=test', tab: false },
    { name: 'card-detail', url: '/pages/card-detail/card-detail?id=1', tab: false },
    { name: 'chat', url: '/pages/chat/chat?readingId=test', tab: false },
    { name: 'membership', url: '/pages/membership/membership', tab: false },
    { name: 'diary', url: '/pages/diary/diary', tab: false },
    { name: 'annual-report', url: '/pages/annual-report/annual-report', tab: false },
  ];

  const res = {};
  for (const p of pages) {
    console.log(`\n--- ${p.name} ---`);
    try {
      const page = p.tab ? await switchTab(p.url) : await navigateTo(p.url);
      if (page) {
        console.log(`  Path: ${page.path}`);
        res[p.name] = { status: 'loaded', path: page.path };
        await screenshot(`page-${p.name}`);
      } else {
        res[p.name] = { status: 'error', error: 'Page returned null' };
      }
    } catch (e) {
      console.log(`  FAIL: ${e.message}`);
      res[p.name] = { status: 'crash', error: e.message };
    }
  }
  return res;
}

async function testCardDetails() {
  console.log('\n========== B. CARD DETAIL ==========\n');
  const cards = [
    { name: 'The Fool (Major)', id: '1', category: 'major' },
    { name: 'Ace of Wands', id: '23', category: 'wands' },
    { name: 'Ace of Cups', id: '37', category: 'cups' },
    { name: 'Ace of Swords', id: '51', category: 'swords' },
    { name: 'Ace of Pentacles', id: '65', category: 'pentacles' },
  ];

  const res = {};
  for (const card of cards) {
    console.log(`\n--- ${card.name} (ID: ${card.id}) ---`);
    try {
      const page = await navigateTo(`/pages/card-detail/card-detail?id=${card.id}`);
      await sleep(2000);

      if (!page) {
        res[card.category] = { status: 'error', error: 'no page' };
        continue;
      }

      const data = await evaluate(() => {
        const pages = getCurrentPages();
        return pages.length > 0 ? { card: pages[pages.length-1].data.card, activeTab: pages[pages.length-1].data.activeTab } : null;
      });

      console.log(`  Card: ${data && data.card ? data.card.name_zh + ' / ' + data.card.name_en : 'null'}`);
      console.log(`  Tab: ${data ? data.activeTab : 'null'}`);
      console.log(`  Image: ${data && data.card && data.card.imagePath ? data.card.imagePath.slice(-40) : 'NONE'}`);
      console.log(`  Keywords: ${data && data.card && data.card.keywordsList ? data.card.keywordsList.join(', ') : 'NONE'}`);

      await screenshot(`card-${card.category}`);

      res[card.category] = {
        status: data && data.card ? 'loaded' : 'api_error',
        name_zh: data && data.card ? data.card.name_zh : null,
        name_en: data && data.card ? data.card.name_en : null,
        hasImage: !!(data && data.card && data.card.imagePath),
        hasKeywords: !!(data && data.card && data.card.keywordsList && data.card.keywordsList.length > 0),
      };
    } catch (e) {
      console.log(`  FAIL: ${e.message}`);
      res[card.category] = { status: 'crash', error: e.message };
    }
  }
  return res;
}

async function testInteractions() {
  console.log('\n========== C. INTERACTIONS ==========\n');
  const res = {};

  // C1: Index page - daily card, spreads
  console.log('--- Home page ---');
  try {
    const page = await switchTab('/pages/index/index');
    await sleep(1500);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      if (p.length === 0) return null;
      const d = p[p.length-1].data;
      return {
        dailyCard: d.dailyCard ? 'exists' : null,
        streak: d.streak,
        hasDrawnToday: d.hasDrawnToday,
        showOnboarding: d.showOnboarding,
        freeReadingsUsed: d.freeReadingsUsed,
        freeReadingsTotal: d.freeReadingsTotal,
        isMember: d.isMember,
        pageLoading: d.pageLoading,
        pageError: d.pageError,
        showReflectionPrompt: d.showReflectionPrompt,
      };
    });
    console.log(`  Data: ${JSON.stringify(data)}`);
    await screenshot('interaction-home');
    res['home'] = { status: 'ok', data };
  } catch (e) {
    res['home'] = { status: 'error', error: e.message };
  }

  // C2: Profile page - check menus
  console.log('\n--- Profile page ---');
  try {
    const page = await switchTab('/pages/profile/profile');
    await sleep(3000);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      if (p.length === 0) return null;
      const d = p[p.length-1].data;
      return {
        user: d.user ? 'exists' : null,
        historyCount: d.readingHistory ? d.readingHistory.length : 0,
        savedCount: d.savedReadings ? d.savedReadings.length : 0,
        pageError: d.pageError,
      };
    });
    console.log(`  Data: ${JSON.stringify(data)}`);
    await screenshot('interaction-profile');
    res['profile'] = { status: 'ok', data };
  } catch (e) {
    res['profile'] = { status: 'error', error: e.message };
  }

  // C3: Encyclopedia - filters, search
  console.log('\n--- Encyclopedia ---');
  try {
    const page = await switchTab('/pages/encyclopedia/encyclopedia');
    await sleep(3000);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      if (p.length === 0) return null;
      const d = p[p.length-1].data;
      return {
        totalCards: d.cards ? d.cards.length : 0,
        filteredCount: d.filteredCards ? d.filteredCards.length : 0,
        activeTab: d.activeTab,
        tabs: d.tabs ? d.tabs.map(t => ({ key: t.key, label: t.label })) : [],
        pageError: d.pageError,
      };
    });
    console.log(`  Data: ${JSON.stringify(data)}`);
    await screenshot('interaction-encyclopedia');
    res['encyclopedia'] = { status: 'ok', data };
  } catch (e) {
    res['encyclopedia'] = { status: 'error', error: e.message };
  }

  // C4: Reading page - spreads
  console.log('\n--- Reading page ---');
  try {
    const page = await navigateTo('/pages/reading/reading');
    await sleep(2000);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      if (p.length === 0) return null;
      const d = p[p.length-1].data;
      return {
        spreads: d.spreads ? d.spreads.map(s => ({ key: s.key, name: s.name, premium: s.premium, cards: s.cards })) : [],
        selectedSpread: d.selectedSpread ? d.selectedSpread.key : null,
      };
    });
    console.log(`  Spreads: ${data ? data.spreads.length : 'null'}`);
    if (data && data.spreads) {
      data.spreads.forEach(s => console.log(`    ${s.name} (${s.key}) - ${s.premium ? 'premium' : 'free'} - ${s.cards} cards`));
    }
    await screenshot('interaction-reading');
    res['reading'] = { status: 'ok', data };
  } catch (e) {
    res['reading'] = { status: 'error', error: e.message };
  }

  return res;
}

async function testEdgeCases() {
  console.log('\n========== D. ERROR / EDGE CASES ==========\n');
  const res = {};

  // D1: Non-existent reading result
  console.log('--- Non-existent reading result ---');
  try {
    const page = await navigateTo('/pages/reading-result/reading-result?id=nonexistent123');
    await sleep(3000);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      return p.length > 0 ? { pageError: p[p.length-1].data.pageError, pageLoading: p[p.length-1].data.pageLoading } : null;
    });
    console.log(`  Error: ${data ? data.pageError : 'null'}, Loading: ${data ? data.pageLoading : 'null'}`);
    await screenshot('edge-nonexistent-reading');
    res['nonexistent-reading'] = { status: data && data.pageError ? 'error_shown' : 'no_error', error: data ? data.pageError : null };
  } catch (e) {
    res['nonexistent-reading'] = { status: 'crash', error: e.message };
  }

  // D2: Card detail with no ID
  console.log('\n--- Card detail (no ID param) ---');
  try {
    const page = await navigateTo('/pages/card-detail/card-detail');
    await sleep(2000);
    const curPage = await miniProgram.currentPage();
    console.log(`  Current path: ${curPage ? curPage.path : 'null'}`);
    await screenshot('edge-noid-card');
    res['noid-card'] = { status: 'navigated', path: curPage ? curPage.path : null };
  } catch (e) {
    res['noid-card'] = { status: 'error', error: e.message };
  }

  // D3: Card detail with bad ID
  console.log('\n--- Card detail (bad ID 999) ---');
  try {
    const page = await navigateTo('/pages/card-detail/card-detail?id=999');
    await sleep(3000);
    const data = await evaluate(() => {
      const p = getCurrentPages();
      return p.length > 0 ? { pageError: p[p.length-1].data.pageError, pageLoading: p[p.length-1].data.pageLoading } : null;
    });
    console.log(`  Error: ${data ? data.pageError : 'null'}`);
    await screenshot('edge-bad-card');
    res['bad-card'] = { status: data && data.pageError ? 'error_shown' : 'no_error', error: data ? data.pageError : null };
  } catch (e) {
    res['bad-card'] = { status: 'crash', error: e.message };
  }

  // D4: Rapid navigation
  console.log('\n--- Rapid navigation ---');
  try {
    for (let round = 0; round < 3; round++) {
      await miniProgram.navigateTo('/pages/reading/reading').catch(() => {});
      await sleep(200);
      await miniProgram.navigateTo('/pages/membership/membership').catch(() => {});
      await sleep(200);
      await miniProgram.navigateTo('/pages/diary/diary').catch(() => {});
      await sleep(200);
      await miniProgram.navigateTo('/pages/reading-result/reading-result?id=test').catch(() => {});
      await sleep(200);
    }
    await sleep(2000);
    const curPage = await miniProgram.currentPage();
    console.log(`  Final page: ${curPage ? curPage.path : 'null'}`);
    await screenshot('edge-rapid-nav');
    res['rapid-nav'] = { status: 'completed', finalPage: curPage ? curPage.path : null };
  } catch (e) {
    res['rapid-nav'] = { status: 'error', error: e.message };
  }

  return res;
}

async function testConsoleCheck() {
  console.log('\n========== E. CONSOLE CHECK ==========\n');
  const res = {};

  try {
    const logs = await miniProgram.getLogs();
    console.log(`Total log entries: ${logs.length}`);

    const errors = logs.filter(l => l.level === 'error');
    const warns = logs.filter(l => l.level === 'warn');
    const domainWarns = warns.filter(l => l.msg && (l.msg.includes('your-domain') || l.msg.includes('上线前')));
    const otherWarns = warns.filter(l => !l.msg || (!l.msg.includes('your-domain') && !l.msg.includes('上线前')));

    console.log(`\nErrors: ${errors.length}`);
    errors.forEach(l => console.log(`  [ERR] ${l.msg}`));

    console.log(`\nWarnings (domain config): ${domainWarns.length}`);
    console.log(`\nWarnings (other): ${otherWarns.length}`);
    otherWarns.slice(0, 10).forEach(l => console.log(`  [WARN] ${l.msg}`));

    res['console'] = {
      total: logs.length,
      errorCount: errors.length,
      domainWarningCount: domainWarns.length,
      otherWarningCount: otherWarns.length,
      errorMessages: errors.map(l => l.msg),
      otherWarningMessages: otherWarns.slice(0, 10).map(l => l.msg),
    };
  } catch (e) {
    console.log(`Console check error: ${e.message}`);
    res['console'] = { status: 'error', error: e.message };
  }

  return res;
}

// ============== MAIN ==============

async function main() {
  console.log('========================================');
  console.log('  TAROT MINI APP - COMPREHENSIVE TESTS');
  console.log('========================================\n');

  try {
    await ensureDevTools();
    console.log('\n======== DEVTOOLS READY ========\n');

    // A. All 10 pages
    results.pages = await testAllPages();

    // B. Card details
    results.cards = await testCardDetails();

    // C. Interactions
    results.interactions = await testInteractions();

    // D. Edge cases
    results.edges = await testEdgeCases();

    // E. Console
    results.console = await testConsoleCheck();

  } catch (e) {
    console.error('\nFATAL:', e.message);
    results.fatal = e.message;
  } finally {
    if (miniProgram) {
      try { await miniProgram.close(); } catch(e) {}
    }
  }

  // Save detailed results
  fs.writeFileSync(
    'E:\\tarot-miniapp\\test-results.json',
    JSON.stringify(results, null, 2)
  );

  // Print summary
  console.log('\n\n========================================');
  console.log('  TEST SUMMARY');
  console.log('========================================\n');

  let pass = 0, fail = 0;
  for (const [section, tests] of Object.entries(results)) {
    if (section === 'fatal' || section === 'console') continue;
    console.log(`\n${section.toUpperCase()}:`);
    for (const [name, result] of Object.entries(tests)) {
      const status = typeof result === 'object' ? (result.status || '?') : '?';
      const icon = status === 'ok' || status === 'loaded' || status === 'error_shown' || status === 'completed' ? 'PASS' : 'FAIL';
      if (icon === 'PASS') pass++; else fail++;
      console.log(`  ${icon} ${name}: ${status}`);
    }
  }
  console.log(`\n\nTotal: ${pass + fail} | PASS: ${pass} | FAIL: ${fail}`);
  console.log(`\nScreenshots: ${SCREENSHOT_DIR}`);
  console.log('Results: E:\\tarot-miniapp\\test-results.json');
}

main().catch(console.error);
