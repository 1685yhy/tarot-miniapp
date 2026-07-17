/**
 * Comprehensive Tarot Mini App Tester
 * Runs inside Windows Node, connects to WeChat DevTools via miniprogram-automator
 */

const path = require('path');
const { spawn } = require('child_process');
const auto = require(path.join('E:\\', 'tarot-miniapp', 'node_modules', 'miniprogram-automator'));

const PROJECT_PATH = 'E:\\tarot-miniapp\\miniapp';
const CLI_PATH = 'E:\\微信web开发者工具\\cli.bat';
const AUTO_PORT = 9420;

let miniProgram = null;

// ============== HELPERS ==============

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function ensureDevTools() {
  // First close any existing session
  try { spawn(CLI_PATH, ['close', '--project', PROJECT_PATH], { shell: true, stdio: 'ignore' }); } catch(e) {}
  await sleep(2000);

  return new Promise((resolve, reject) => {
    console.log('[SETUP] Opening DevTools with automation...');
    const proc = spawn(CLI_PATH, ['auto', '--project', PROJECT_PATH, '--auto-port', String(AUTO_PORT)], {
      shell: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: 'E:\\',
    });

    let output = '';
    proc.stdout.on('data', d => { output += d.toString(); });
    proc.stderr.on('data', d => { output += d.toString(); });

    proc.on('error', e => reject(e));
    proc.on('exit', () => {
      console.log('[SETUP] CLI exited. Output:', output.slice(0, 300));
    });

    // Try connecting repeatedly
    let attempts = 0;
    const maxAttempts = 30;
    const tryConnect = async () => {
      while (attempts < maxAttempts) {
        try {
          console.log(`[SETUP] Connection attempt ${attempts + 1}...`);
          const mp = await auto.connect({ wsEndpoint: 'ws://127.0.0.1:' + AUTO_PORT });
          console.log('[SETUP] Connected to DevTools!');
          miniProgram = mp;
          resolve(mp);
          return;
        } catch (e) {
          attempts++;
          await sleep(2000);
        }
      }
      reject(new Error('Could not connect to DevTools after ' + maxAttempts + ' attempts'));
    };
    tryConnect();
  });
}

async function screenshot(page, name) {
  try {
    const img = await page.screenshot();
    const fs = require('fs');
    const dir = 'E:\\tarot-miniapp\\test-screenshots';
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);
    const filepath = path.join(dir, name + '.png');
    fs.writeFileSync(filepath, img);
    console.log(`  [SCREENSHOT] Saved ${filepath}`);
    return filepath;
  } catch (e) {
    console.log(`  [SCREENSHOT FAIL] ${name}: ${e.message}`);
    return null;
  }
}

async function navigateToPage(url) {
  console.log(`  Navigating to ${url}...`);
  try {
    await miniProgram.navigateTo(url);
    await sleep(2000);
    const page = await miniProgram.currentPage();
    return page;
  } catch (e) {
    console.log(`  Navigate error: ${e.message}`);
    return null;
  }
}

async function getPageData() {
  try {
    return await miniProgram.evaluate(() => {
      const page = getCurrentPages();
      if (page.length > 0) return page[page.length - 1].data;
      return null;
    });
  } catch (e) {
    return { error: e.message };
  }
}

async function callPageMethod(method, args) {
  try {
    return await miniProgram.callFunction({
      method: method,
      args: args || [],
    });
  } catch (e) {
    return { error: e.message };
  }
}

// ============== TESTS ==============

// A. ALL 10 PAGES
async function testAllPages() {
  console.log('\n========== A. ALL 10 PAGES ==========');
  const pages = [
    { name: 'index', url: '/pages/index/index' },
    { name: 'encyclopedia', url: '/pages/encyclopedia/encyclopedia' },
    { name: 'profile', url: '/pages/profile/profile' },
    { name: 'reading', url: '/pages/reading/reading' },
    { name: 'reading-result', url: '/pages/reading-result/reading-result?id=test' },
    { name: 'card-detail', url: '/pages/card-detail/card-detail?id=1' },
    { name: 'chat', url: '/pages/chat/chat?readingId=test' },
    { name: 'membership', url: '/pages/membership/membership' },
    { name: 'diary', url: '/pages/diary/diary' },
    { name: 'annual-report', url: '/pages/annual-report/annual-report' },
  ];

  const results = {};
  for (const p of pages) {
    console.log(`\n--- Page: ${p.name} (${p.url}) ---`);
    try {
      const page = await navigateToPage(p.url);
      if (page) {
        console.log(`  Path: ${page.path}`);
        results[p.name] = { status: 'loaded', path: page.path };
        await screenshot(miniProgram, `page-${p.name}`);
      } else {
        results[p.name] = { status: 'error', error: 'Page returned null' };
      }
    } catch (e) {
      console.log(`  FAILED: ${e.message}`);
      results[p.name] = { status: 'error', error: e.message };
    }
  }
  return results;
}

// B. CARD DETAIL
async function testCardDetails() {
  console.log('\n========== B. CARD DETAIL ==========');
  const cards = [
    { name: 'Major Arcana - The Fool', id: '1', suit: 'major' },
    { name: 'Wands - Ace of Wands', id: '57', suit: 'wands' },
    { name: 'Cups - Ace of Cups', id: '36', suit: 'cups' },
    { name: 'Swords - Ace of Swords', id: '15', suit: 'swords' },
    { name: 'Pentacles - Ace of Pentacles', id: '78', suit: 'pentacles' },
  ];

  const results = {};
  for (const card of cards) {
    console.log(`\n--- Card: ${card.name} (ID: ${card.id}) ---`);
    try {
      const url = `/pages/card-detail/card-detail?id=${card.id}`;
      const page = await navigateToPage(url);
      await sleep(1500);

      if (page) {
        // Get page data
        const data = await getPageData();
        console.log(`  Card: ${data.card ? data.card.name_zh : 'null'}, Tab: ${data.activeTab}`);

        // Check upright view
        if (data.activeTab === 'upright' && data.card && data.card.keywordsList) {
          console.log(`  Upright keywords: ${data.card.keywordsList.join(', ')}`);
        }

        // Switch to reversed view
        if (data.card) {
          // Try tapping the reversed tab
          try {
            await miniProgram.callFunction({
              method: 'onTabTap',
              args: [{ currentTarget: { dataset: { tab: 'reversed' } } }],
            });
            await sleep(500);
            const revData = await getPageData();
            console.log(`  Reversed tab: ${revData.activeTab === 'reversed' ? 'OK' : 'FAIL'}`);
          } catch (e) {
            console.log(`  Reversed tab click: ${e.message}`);
          }
        }

        await screenshot(miniProgram, `card-${card.suit}-${card.id}`);
        results[card.suit] = {
          status: 'loaded',
          name: data.card ? data.card.name_zh : 'null',
          hasImage: !!(data.card && data.card.imagePath),
          hasKeywords: !!(data.card && data.card.keywordsList && data.card.keywordsList.length > 0)
        };
      }
    } catch (e) {
      console.log(`  FAILED: ${e.message}`);
      results[card.suit] = { status: 'error', error: e.message };
    }
  }
  return results;
}

// C. INTERACTIONS
async function testInteractions() {
  console.log('\n========== C. INTERACTIONS ==========');
  const results = {};

  // C1: Index page
  console.log('\n--- Home page interactions ---');
  try {
    await navigateToPage('/pages/index/index');
    await sleep(1500);
    const data = await getPageData();
    console.log(`  Daily card: ${data.dailyCard ? 'exists' : 'null'}`);
    console.log(`  Onboarding: ${data.showOnboarding}`);
    console.log(`  Streak: ${data.streak}, Drawn today: ${data.hasDrawnToday}`);
    results['index-load'] = { status: 'ok', data };
  } catch (e) {
    results['index-load'] = { status: 'error', error: e.message };
  }

  // C2: Profile page
  console.log('\n--- Profile page ---');
  try {
    await navigateToPage('/pages/profile/profile');
    await sleep(2000);
    const data = await getPageData();
    console.log(`  User: ${data.user ? 'exists' : 'null'}`);
    console.log(`  History: ${data.readingHistory ? data.readingHistory.length : 'null'} items`);
    results['profile-load'] = { status: 'ok', user: !!data.user, historyCount: data.readingHistory ? data.readingHistory.length : 0 };
  } catch (e) {
    results['profile-load'] = { status: 'error', error: e.message };
  }

  // C3: Encyclopedia page
  console.log('\n--- Encyclopedia page ---');
  try {
    await navigateToPage('/pages/encyclopedia/encyclopedia');
    await sleep(2000);
    const data = await getPageData();
    console.log(`  Cards loaded: ${data.cards ? data.cards.length : 'null'}`);
    console.log(`  Filtered: ${data.filteredCards ? data.filteredCards.length : 'null'}`);
    console.log(`  Active tab: ${data.activeTab}`);
    // Try filter taps
    if (data.tabs) {
      for (const tab of data.tabs.slice(0, 3)) {
        console.log(`  Tab available: ${tab.key} - ${tab.label}`);
      }
    }
    results['encyclopedia-load'] = {
      status: 'ok',
      totalCards: data.cards ? data.cards.length : 0,
      tabs: data.tabs ? data.tabs.length : 0
    };
  } catch (e) {
    results['encyclopedia-load'] = { status: 'error', error: e.message };
  }

  // C4: Reading page
  console.log('\n--- Reading page ---');
  try {
    await navigateToPage('/pages/reading/reading');
    await sleep(1500);
    const data = await getPageData();
    console.log(`  Spreads: ${data.spreads ? data.spreads.length : 'null'}`);
    console.log(`  Selected: ${data.selectedSpread ? data.selectedSpread.key : 'null'}`);
    if (data.spreads) {
      data.spreads.forEach(s => console.log(`  Spread: ${s.name} (${s.key}) - ${s.premium ? 'premium' : 'free'}`));
    }
    results['reading-load'] = {
      status: 'ok',
      spreads: data.spreads ? data.spreads.length : 0
    };
  } catch (e) {
    results['reading-load'] = { status: 'error', error: e.message };
  }

  return results;
}

// D. ERROR / EDGE CASES
async function testEdgeCases() {
  console.log('\n========== D. ERROR / EDGE CASES ==========');
  const results = {};

  // D1: Non-existent reading result
  console.log('\n--- Non-existent reading result ---');
  try {
    await navigateToPage('/pages/reading-result/reading-result?id=nonexistent123');
    await sleep(2000);
    const data = await getPageData();
    console.log(`  Page loading: ${data.pageLoading}, error: ${data.pageError}`);
    await screenshot(miniProgram, 'edge-nonexistent-reading');
    results['nonexistent-reading'] = { status: data.pageError ? 'error-shown' : 'loaded', error: data.pageError };
  } catch (e) {
    results['nonexistent-reading'] = { status: 'error', error: e.message };
  }

  // D2: Non-existent card detail (missing id)
  console.log('\n--- Non-existent card detail (no id) ---');
  try {
    await navigateToPage('/pages/card-detail/card-detail');
    await sleep(1000);
    const page = await miniProgram.currentPage();
    console.log(`  Current path after navigate: ${page ? page.path : 'null'}`);
    await screenshot(miniProgram, 'edge-noid-card');
    results['noid-card'] = { status: page ? page.path : 'null', expected: 'should go back' };
  } catch (e) {
    results['noid-card'] = { status: 'error', error: e.message };
  }

  // D3: Non-existent card detail (bad id)
  console.log('\n--- Non-existent card detail (bad id) ---');
  try {
    await navigateToPage('/pages/card-detail/card-detail?id=999999');
    await sleep(2000);
    const data = await getPageData();
    console.log(`  Page loading: ${data.pageLoading}, error: ${data.pageError}`);
    await screenshot(miniProgram, 'edge-bad-card');
    results['bad-card'] = { status: data.pageError ? 'error-shown' : 'loaded', error: data.pageError };
  } catch (e) {
    results['bad-card'] = { status: 'error', error: e.message };
  }

  // D4: Rapid navigation
  console.log('\n--- Rapid navigation ---');
  try {
    const urls = [
      '/pages/index/index',
      '/pages/encyclopedia/encyclopedia',
      '/pages/profile/profile',
      '/pages/reading/reading',
    ];
    for (let i = 0; i < 3; i++) {
      for (const url of urls) {
        try {
          await miniProgram.navigateTo(url);
          await sleep(300);
        } catch(e) {}
      }
    }
    await sleep(2000);
    const page = await miniProgram.currentPage();
    console.log(`  Final page after rapid nav: ${page ? page.path : 'null'}`);
    await screenshot(miniProgram, 'edge-rapid-nav');
    results['rapid-nav'] = { status: 'completed', finalPage: page ? page.path : 'null' };
  } catch (e) {
    results['rapid-nav'] = { status: 'error', error: e.message };
  }

  return results;
}

// E. CONSOLE CHECK
async function testConsoleCheck() {
  console.log('\n========== E. CONSOLE CHECK ==========');
  const results = {};

  try {
    const logs = await miniProgram.getLogs();
    console.log(`Total logs: ${logs.length}`);

    const errors = logs.filter(l => l.level === 'error');
    const warnings = logs.filter(l => l.level === 'warn');
    const domainWarnings = warnings.filter(l => l.msg && l.msg.includes('your-domain'));
    const otherWarnings = warnings.filter(l => !l.msg || !l.msg.includes('your-domain'));

    console.log(`Errors: ${errors.length}`);
    errors.forEach(l => console.log(`  [ERR] ${l.msg}`));

    console.log(`Domain validation warnings: ${domainWarnings.length}`);
    console.log(`Other warnings: ${otherWarnings.length}`);
    otherWarnings.slice(0, 10).forEach(l => console.log(`  [WARN] ${l.msg}`));

    results['console'] = {
      totalLogs: logs.length,
      errors: errors.length,
      domainWarnings: domainWarnings.length,
      otherWarnings: otherWarnings.length,
      errorMessages: errors.map(l => l.msg),
      warningMessages: otherWarnings.slice(0, 10).map(l => l.msg),
    };
  } catch (e) {
    console.log(`Console check failed: ${e.message}`);
    results['console'] = { status: 'error', error: e.message };
  }

  return results;
}

// ============== MAIN ==============

async function main() {
  console.log('========================================');
  console.log('  TAROT MINI APP - COMPREHENSIVE TESTS');
  console.log('========================================\n');

  let allResults = {};

  try {
    // Step 0: Ensure DevTools is running and connected
    await ensureDevTools();

    // Step A: All 10 pages
    allResults.pages = await testAllPages();

    // Step B: Card details
    allResults.cards = await testCardDetails();

    // Step C: Interactions
    allResults.interactions = await testInteractions();

    // Step D: Edge cases
    allResults.edges = await testEdgeCases();

    // Step E: Console check
    allResults.console = await testConsoleCheck();

  } catch (e) {
    console.error('Fatal error:', e.message);
    allResults.fatal = e.message;
  } finally {
    if (miniProgram) {
      try { await miniProgram.close(); } catch(e) {}
    }
  }

  // Generate report
  console.log('\n\n========================================');
  console.log('  TEST RESULTS SUMMARY');
  console.log('========================================\n');

  for (const [section, results] of Object.entries(allResults)) {
    console.log(`\n--- ${section.toUpperCase()} ---`);
    if (typeof results === 'object') {
      for (const [key, val] of Object.entries(results)) {
        const status = val.status || 'unknown';
        console.log(`  ${key}: ${status}`);
        if (val.error) console.log(`    Error: ${val.error}`);
      }
    }
  }

  // Write results to JSON
  const fs = require('fs');
  fs.writeFileSync(
    'E:\\tarot-miniapp\\test-results.json',
    JSON.stringify(allResults, null, 2)
  );
  console.log('\nResults saved to E:\\tarot-miniapp\\test-results.json');
}

main().catch(console.error);
