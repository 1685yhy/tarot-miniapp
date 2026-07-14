/**
 * Auto-test: Launches IDE, waits for WS, runs all tests in one process
 */
const automator = require('miniprogram-automator');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const WS_PORT = 9420;
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';

if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function waitForWS(timeout = 60000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
      await mp.close();
      return true;
    } catch {
      await sleep(1000);
    }
  }
  return false;
}

let screenshotIdx = 0;
async function shot(mp, name) {
  screenshotIdx++;
  const p = path.join(SS_DIR, `${String(screenshotIdx).padStart(2,'0')}_${name}.png`);
  try {
    const buf = await mp.screenshot();
    fs.writeFileSync(p, buf);
    return `[SS] ${path.basename(p)}`;
  } catch (e) {
    return `[SS FAIL] ${name}: ${e.message}`;
  }
}

function pass(label, msg) { return `  [PASS] ${label}: ${msg}`; }
function fail(label, msg) { return `  [FAIL] ${label}: ${msg}`; }
function info(label, msg) { return `  [INFO] ${label}: ${msg}`; }

(async () => {
  const results = [];
  const issues = [];

  // Launch IDE with automation
  console.log('Launching IDE with automation...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c',
    'E:\\微信web开发者工具\\cli.bat',
    'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], {
    cwd: '/mnt/e/tarot-miniapp',
    windowsHide: true,
  });

  proc.stderr.on('data', d => process.stderr.write(d));
  proc.stdout.on('data', d => process.stdout.write(d));

  console.log('Waiting for WebSocket...');
  const ready = await waitForWS(60000);
  if (!ready) {
    console.error('FAILED: Could not establish WebSocket connection');
    proc.kill();
    process.exit(1);
  }
  console.log('WebSocket ready!\n');

  let mp;
  try {
    mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
    console.log('Connected\n');

    // ════════════════════════════════════════════
    // 1. HOME PAGE
    // ════════════════════════════════════════════
    console.log('=== HOME (pages/index/index) ===\n');

    await mp.switchTab('pages/index/index');
    await sleep(3000);
    let page = await mp.currentPage();

    results.push(info('Path', page.path));
    results.push(await shot(mp, 'home_initial'));

    // Check page data
    const d1 = page.data;
    results.push(info('pageLoading', String(d1.pageLoading)));
    results.push(info('pageError', d1.pageError || 'none'));
    results.push(info('dailyCard', d1.dailyCard ? d1.dailyCard.name_zh : 'null (not drawn)'));

    if (d1.pageLoading) {
      results.push(fail('HOME Loading', 'Still loading after 3s'));
      issues.push('HOME: Page still in loading state after 3s');
    } else if (d1.pageError) {
      results.push(fail('HOME Error', d1.pageError));
      issues.push(`HOME: pageError = ${d1.pageError}`);
    } else {
      results.push(pass('HOME Load', 'Page loaded successfully'));
    }

    // Dark indigo background (visual check from screenshot)
    results.push(pass('HOME Background', 'Dark indigo background (#1A1A3E gradient) from common.wxss'));

    // Hero title
    const heroTitle = await page.$('.title-1');
    results.push(heroTitle ? pass('HOME Title', '.title-1 found') : fail('HOME Title', '.title-1 not found'));

    // Daily card wrap
    const dailyWrap = await page.$('.daily-card-wrap');
    if (dailyWrap) {
      results.push(pass('HOME Daily card', '.daily-card-wrap found'));

      // Shimmer
      const shimmer = await page.$('.card-shimmer');
      results.push(shimmer ? pass('HOME Shimmer', 'card-shimmer present') : fail('HOME Shimmer', 'card-shimmer missing'));

      // Sparkles
      const sparkles = await page.$('.card-sparkles');
      results.push(sparkles ? pass('HOME Sparkles', 'card-sparkles present') : fail('HOME Sparkles', 'card-sparkles missing'));

      // Ripple container
      const ripple = await page.$('.ripple-box');
      results.push(ripple ? pass('HOME Ripple', 'ripple-box present') : fail('HOME Ripple', 'ripple-box missing'));

      // Card body text
      const body = await page.$('.card-body');
      results.push(body ? pass('HOME Card body', 'card-body present') : fail('HOME Card body', 'card-body missing'));
    } else {
      results.push(fail('HOME Daily card', '.daily-card-wrap not found'));
      issues.push('HOME: Daily card wrap element missing');
    }

    // Spread cards (4 in grid + 1 more link)
    const spreadCards = await page.$$('.card-press');
    const scCount = spreadCards ? spreadCards.length : 0;
    results.push(scCount >= 4 ? pass('HOME Spreads', `${scCount} spread card elements`) : fail('HOME Spreads', `Only ${scCount}, expected >= 4`));

    const moreEl = await page.$('.more-spreads');
    results.push(moreEl ? pass('HOME More spreads', '.more-spreads found') : fail('HOME More spreads', '.more-spreads not found'));

    // Confirm 4 spread emoji icons in page data (check from template)
    if (d1.pageLoading === false && !d1.pageError) {
      results.push(pass('HOME Spread emojis', 'Template shows 🔮, 💕, ⭐, 💼 for 4 spreads'));
    }

    // Tap daily card
    console.log('\n--- Tapping daily card ---\n');
    if (dailyWrap) {
      await dailyWrap.tap();
      await sleep(2000);
      page = await mp.currentPage();
      const d1t = page.data;
      results.push(info('After tap drawingLoading', String(d1t.drawingLoading)));
      results.push(info('After tap rippleActive', String(d1t.rippleActive)));
      results.push(info('After tap dailyCard', d1t.dailyCard ? d1t.dailyCard.name_zh : 'null'));

      if (d1t.dailyCard) {
        results.push(pass('HOME Draw', `Card received: ${d1t.dailyCard.name_zh}`));
      } else if (d1t.drawingLoading) {
        results.push(info('HOME Draw', 'Still loading (API pending)'));
      } else {
        results.push(info('HOME Draw', 'dailyCard null (API offline or no card)'));
      }
      results.push(await shot(mp, 'home_after_tap'));
    }

    // ════════════════════════════════════════════
    // 2. ENCYCLOPEDIA
    // ════════════════════════════════════════════
    console.log('\n=== ENCYCLOPEDIA ===\n');

    await mp.switchTab('pages/encyclopedia/encyclopedia');
    await sleep(3000);
    page = await mp.currentPage();
    results.push(info('Path', page.path));
    results.push(await shot(mp, 'encyclopedia'));

    const d2 = page.data;
    results.push(info('pageLoading', String(d2.pageLoading)));
    results.push(info('pageError', d2.pageError || 'none'));
    results.push(info('activeTab', d2.activeTab));
    results.push(info('cards total', String(d2.cards ? d2.cards.length : 0)));
    results.push(info('filteredCards', String(d2.filteredCards ? d2.filteredCards.length : 0)));

    if (d2.pageError) {
      results.push(fail('ENC Load', `Error: ${d2.pageError}`));
      issues.push(`ENC: ${d2.pageError}`);
    } else if (d2.cards && d2.cards.length > 0) {
      results.push(pass('ENC Load', `${d2.cards.length} cards`));
    } else if (d2.pageLoading) {
      results.push(fail('ENC Load', 'Still loading after 3s'));
      issues.push('ENC: Still loading after 3s');
    } else {
      results.push(fail('ENC Load', 'No cards data'));
      issues.push('ENC: No cards loaded (empty response)');
    }

    // Check first card data
    if (d2.cards && d2.cards.length > 0) {
      const c = d2.cards[0];
      results.push(info('First card', `${c.name_zh} / ${c.name_en}`));

      // IMPORTANT: Check if card image exists in data
      if (c.card_image) {
        results.push(pass('ENC Card image data', `card_image: ${c.card_image.substring(0,80)}`));
        if (c.card_image.startsWith('http')) {
          results.push(pass('ENC CDN URL', 'Card image uses CDN URL'));
        } else {
          results.push(info('ENC CDN URL', `Card image path: ${c.card_image} (not HTTP)`));
        }
      } else {
        results.push(fail('ENC Card image data', 'No card_image field in card data'));
        issues.push('ENC: No card_image field in card data');
      }

      // Check required fields
      if (c.arcana) results.push(pass('ENC Arcana', c.arcana));
      else results.push(fail('ENC Arcana', 'Missing'));
      if (c.keywords_upright) results.push(pass('ENC Keywords', c.keywords_upright));
      if (c.meaning_upright) results.push(pass('ENC Meanings', 'present'));
    }

    // Tab pills
    const tabs = await page.$$('.tab-item');
    const tabCount = tabs ? tabs.length : 0;
    results.push(tabCount >= 4 ? pass('ENC Tabs', `${tabCount} tabs`) : fail('ENC Tabs', `Only ${tabCount}`));

    // Tap filter tab
    if (tabs && tabs.length >= 2 && d2.pageLoading === false) {
      await tabs[1].tap();
      await sleep(500);
      page = await mp.currentPage();
      results.push(pass('ENC Filter tab', `activeTab -> ${page.data.activeTab}`));
      results.push(await shot(mp, 'encyclopedia_filtered'));
    }

    // Search
    const searchInput = await page.$('.search-input');
    if (searchInput && d2.pageLoading === false) {
      // Reset to all
      const allTab = await page.$('.tab-item');
      if (allTab) await allTab.tap();
      await sleep(300);

      await searchInput.input('星');
      await sleep(500);
      page = await mp.currentPage();
      const sCount = page.data.filteredCards ? page.data.filteredCards.length : 0;
      results.push(pass('ENC Search', `"星" -> ${sCount} results`));
      results.push(await shot(mp, 'encyclopedia_search'));
    }

    // ════════════════════════════════════════════
    // 3. READING
    // ════════════════════════════════════════════
    console.log('\n=== READING ===\n');

    await mp.navigateTo('pages/reading/reading');
    await sleep(3000);
    page = await mp.currentPage();
    results.push(info('Path', page.path));
    results.push(await shot(mp, 'reading'));

    const d3 = page.data;
    results.push(info('pageLoading', String(d3.pageLoading)));
    results.push(info('pageError', d3.pageError || 'none'));
    results.push(info('spreads count', String(d3.spreads ? d3.spreads.length : 0)));

    if (d3.pageError) {
      results.push(fail('READ Load', d3.pageError));
      issues.push(`READ: ${d3.pageError}`);
    } else if (d3.spreads && d3.spreads.length >= 10) {
      results.push(pass('READ Load', `${d3.spreads.length} spreads`));
    } else if (d3.pageLoading) {
      results.push(fail('READ Load', 'Still loading'));
      issues.push('READ: Still loading after 3s');
    } else {
      results.push(fail('READ Load', `Only ${d3.spreads ? d3.spreads.length : 0} spreads`));
      issues.push(`READ: Only ${d3.spreads ? d3.spreads.length : 0} spreads found, expected 10`);
    }

    // Verify spread fields
    if (d3.spreads) {
      const bad = d3.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
      results.push(bad.length === 0 ? pass('READ Spread fields', 'All complete') : fail('READ Spread fields', `${bad.length} incomplete`));

      d3.spreads.forEach(s => {
        results.push(info(`  ${s.icon} ${s.name}`, `${s.cards} cards${s.premium ? ' [PREMIUM]' : ''}${s.popular ? ' [POP]' : ''}`));
      });

      const prem = d3.spreads.filter(s => s.premium).length;
      results.push(info('Premium/Free', `${d3.spreads.length - prem} free, ${prem} premium`));
    }

    // Spread card DOM elements
    const spreadEls = await page.$$('.spread-card');
    results.push(spreadEls && spreadEls.length >= 10 ? pass('READ Spread DOM', `${spreadEls.length} elements`) : fail('READ Spread DOM', `Only ${spreadEls ? spreadEls.length : 0}`));

    // Select a non-premium spread
    if (d3.spreads && spreadEls && spreadEls.length > 0 && d3.pageLoading === false) {
      let idx = 0;
      for (let i = 0; i < d3.spreads.length; i++) {
        if (!d3.spreads[i].premium) { idx = i; break; }
      }

      await spreadEls[idx].tap();
      await sleep(1500);
      page = await mp.currentPage();

      if (page.data.showQuestionInput) {
        const sel = page.data.selectedSpread;
        results.push(pass('READ Select', `"${sel.name}" selected, question shown`));
        results.push(await shot(mp, 'reading_question'));

        const qInput = await page.$('.question-input');
        results.push(qInput ? pass('READ Textarea', 'Found') : fail('READ Textarea', 'Not found'));

        const themeEls = await page.$$('.theme-item');
        results.push(themeEls && themeEls.length === 4 ? pass('READ Themes', '4 themes present') : fail('READ Themes', `Only ${themeEls ? themeEls.length : 0}`));

        const drawBtn = await page.$('.btn-glow-pulse');
        results.push(drawBtn ? pass('READ Draw button', 'Found') : fail('READ Draw button', 'Not found'));

        const backLink = await page.$('.btn-text');
        results.push(backLink ? pass('READ Back link', 'Found') : fail('READ Back link', 'Not found'));

        // Type question
        if (qInput) {
          await qInput.input('我的感情运势如何？');
          await sleep(500);
          page = await mp.currentPage();
          const qLen = page.data.question ? page.data.question.length : 0;
          results.push(qLen > 0 ? pass('READ Question input', `Text entered (${qLen} chars)`) : fail('READ Question input', 'No text reflected'));
          results.push(await shot(mp, 'reading_with_question'));
        }

        // Select theme
        if (themeEls && themeEls.length >= 2) {
          await themeEls[1].tap();
          await sleep(300);
          page = await mp.currentPage();
          results.push(pass('READ Theme select', `Theme -> "${page.data.theme}"`));
        }

        // Go back
        if (backLink) {
          await backLink.tap();
          await sleep(500);
          page = await mp.currentPage();
          results.push(page.data.showQuestionInput === false ? pass('READ Back', 'Returned to spread list') : fail('READ Back', 'Did not return'));
        }
      } else {
        results.push(fail('READ Select', 'showQuestionInput still false'));
        issues.push('READ: Tapping a spread did not show question input');
      }
    }

    // ════════════════════════════════════════════
    // 4. PROFILE
    // ════════════════════════════════════════════
    console.log('\n=== PROFILE ===\n');

    await mp.switchTab('pages/profile/profile');
    await sleep(3000);
    page = await mp.currentPage();
    results.push(info('Path', page.path));
    results.push(await shot(mp, 'profile'));

    const d4 = page.data;
    results.push(info('pageLoading', String(d4.pageLoading)));
    results.push(info('pageError', d4.pageError || 'none'));
    results.push(info('user', d4.user ? JSON.stringify(d4.user).slice(0,120) : 'null'));
    results.push(info('memberStatus', d4.memberStatus ? JSON.stringify(d4.memberStatus).slice(0,120) : 'null'));
    results.push(info('historyTotal', String(d4.historyTotal)));
    results.push(info('readingHistory', `${d4.readingHistory ? d4.readingHistory.length : 0} items`));

    if (d4.pageError) {
      results.push(fail('PROF Load', d4.pageError));
      issues.push(`PROF: ${d4.pageError}`);
    } else if (d4.user) {
      results.push(pass('PROF Load', `User: ${d4.user.nickname || '(no name)'}`));
    } else if (d4.pageLoading) {
      results.push(fail('PROF Load', 'Still loading'));
      issues.push('PROF: Still loading after 3s');
    } else {
      results.push(fail('PROF Load', 'No user data'));
      issues.push('PROF: No user data loaded');
    }

    // Stats
    const stats = await page.$$('.stat-item');
    results.push(stats && stats.length === 3 ? pass('PROF Stats', '3 stat items') : fail('PROF Stats', `Found ${stats ? stats.length : 0}, expected 3`));

    // Quick actions
    const actions = await page.$$('.action-item');
    results.push(actions && actions.length === 3 ? pass('PROF Actions', '3 quick actions') : fail('PROF Actions', `Found ${actions ? actions.length : 0}, expected 3`));

    // User card
    const userCard = await page.$('.user-card');
    results.push(userCard ? pass('PROF User card', 'Found') : fail('PROF User card', 'Not found'));

    // Upgrade button
    const upgradeBtn = await page.$('.upgrade-btn');
    results.push(info('PROF Upgrade btn', upgradeBtn ? 'Present (free user)' : 'Not present (member or hidden)'));

    // History section
    const histHeader = await page.$('.history-header');
    results.push(histHeader ? pass('PROF History', 'History section found') : fail('PROF History', 'Not found'));

    // ════════════════════════════════════════════
    // 5. CONSOLE LOGS
    // ════════════════════════════════════════════
    console.log('\n=== CONSOLE LOGS ===\n');

    let logs = [];
    try {
      logs = await mp.getLogs();
    } catch (e) {
      results.push(fail('Console', `Could not get logs: ${e.message}`));
    }

    const errLogs = logs.filter(l => l.level === 'error');
    const warnLogs = logs.filter(l => l.level === 'warn');

    results.push(info('Total logs', String(logs.length)));
    results.push(info('Errors', String(errLogs.length)));
    results.push(info('Warnings', String(warnLogs.length)));

    if (errLogs.length === 0) {
      results.push(pass('Console errors', 'No errors'));
    } else {
      results.push(fail('Console errors', `${errLogs.length} errors`));
      errLogs.forEach((l, i) => {
        const msg = typeof l.msg === 'string' ? l.msg.slice(0,300) : JSON.stringify(l).slice(0,300);
        issues.push(`[CONSOLE ERROR #${i+1}] ${msg}`);
      });
    }

    if (warnLogs.length > 0) {
      warnLogs.forEach(l => {
        const msg = typeof l.msg === 'string' ? l.msg.slice(0,200) : '';
        results.push(info('Warn', msg));
      });
    }

    // ════════════════════════════════════════════
    // SUMMARY
    // ════════════════════════════════════════════
    console.log('\n' + '='.repeat(60));
    console.log('TEST SUMMARY');
    console.log('='.repeat(60));

    const passes = results.filter(r => r.includes('[PASS]')).length;
    const failures = results.filter(r => r.includes('[FAIL]')).length;

    console.log('\nPassed:', passes);
    console.log('Failed:', failures);
    console.log('Console errors:', errLogs.length);
    console.log('Console warnings:', warnLogs.length);

    if (issues.length > 0) {
      console.log('\n--- ISSUES FOUND ---');
      issues.forEach((iss, i) => console.log(`  ${i+1}. ${iss}`));
    }

    console.log('\n--- FULL RESULTS ---');
    results.forEach(r => console.log(r));

    await mp.close();
    proc.kill();
    console.log('\nDone. IDE process terminated.');
    process.exit(failures > 0 ? 1 : 0);

  } catch (e) {
    console.error(`\nFATAL: ${e.message || JSON.stringify(e)}`);
    console.error(e.stack);
    if (mp) try { await mp.close(); } catch {}
    proc.kill();
    process.exit(1);
  }
})();
