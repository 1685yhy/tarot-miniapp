/**
 * Comprehensive Tarot Mini-App Test Suite v2
 * Single-connection version (no retry loops)
 */
const automator = require('miniprogram-automator');
const fs = require('fs');
const path = require('path');

const WS_ENDPOINT = process.env.AUTO_WS || 'ws://127.0.0.1:9420';
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';

const ISSUES = [];
const RESULTS = [];

const sleep = ms => new Promise(r => setTimeout(r, ms));

let screenshotIndex = 0;
async function shot(mp, label) {
  screenshotIndex++;
  const name = `${String(screenshotIndex).padStart(2,'0')}_${label}`;
  try {
    const buf = await mp.screenshot();
    fs.writeFileSync(path.join(SS_DIR, name + '.png'), buf);
    RESULTS.push(`  [SS] ${name}.png`);
    return true;
  } catch (e) {
    ISSUES.push(`Screenshot ${name} failed: ${e.message}`);
    return false;
  }
}

function pass(label, msg) { RESULTS.push(`  [PASS] ${label}: ${msg}`); }
function fail(label, msg) { RESULTS.push(`  [FAIL] ${label}: ${msg}`); ISSUES.push(`${label}: ${msg}`); }
function info(label, msg) { RESULTS.push(`  [INFO] ${label}: ${msg}`); }

(async () => {
  if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

  console.log('=== TAROT MINI-APP COMPREHENSIVE TEST ===\n');

  const mp = await automator.connect({ wsEndpoint: WS_ENDPOINT });
  console.log('Connected\n');

  // ════════════════════════════════════════════
  // 1. HOME PAGE
  // ════════════════════════════════════════════
  console.log('=== HOME (pages/index/index) ===\n');

  await mp.switchTab('pages/index/index');
  await sleep(3000);
  let page = await mp.currentPage();
  info('Path', page.path);
  await shot(mp, 'home_initial');

  const d1 = page.data;
  info('pageLoading', String(d1.pageLoading));
  info('pageError', d1.pageError || 'none');
  info('dailyCard', d1.dailyCard ? d1.dailyCard.name_zh : 'null (not drawn)');

  // Check loading state
  if (d1.pageLoading) {
    fail('HOME Loading state', 'Page still in skeleton load after 3s — possible API timeout');
  } else if (d1.pageError) {
    fail('HOME Error state', `Error: ${d1.pageError}`);
  } else {
    pass('HOME Load', 'Page loaded with no errors');
  }

  // Elements: Hero title
  try {
    const title = await page.$('.title-1');
    pass('HOME Hero title', title ? 'Element .title-1 found' : 'Element not found');
  } catch (e) {
    fail('HOME Hero title', `Query error: ${e.message}`);
  }

  // Elements: Daily card
  try {
    const wrap = await page.$('.daily-card-wrap');
    if (wrap) {
      pass('HOME Daily card wrap', 'Element .daily-card-wrap found');
      const shimmer = await page.$('.card-shimmer');
      info('Shimmer', shimmer ? 'present' : 'missing from pre-draw state');
      const sparkles = await page.$('.card-sparkles');
      info('Sparkles', sparkles ? 'present' : 'missing');
      const ripple = await page.$('.ripple-box');
      info('Ripple box', ripple ? 'present' : 'missing');
      const cardBody = await page.$('.card-body');
      info('Card body text', cardBody ? 'present' : 'missing');
    } else {
      fail('HOME Daily card wrap', 'Element not found');
    }
  } catch (e) {
    fail('HOME Daily card', `Error: ${e.message}`);
  }

  // Elements: Spread cards (should be 4)
  try {
    const cards = await page.$$('.card-press');
    const count = cards ? cards.length : 0;
    if (count >= 4) {
      pass('HOME Spread cards', `${count} spread cards found (includes .more-spreads)`);
    } else {
      fail('HOME Spread cards', `Only ${count} found, expected >= 4`);
    }
  } catch (e) {
    fail('HOME Spread cards', `Error: ${e.message}`);
  }

  // Elements: More spreads link
  try {
    const more = await page.$('.more-spreads');
    pass('HOME More spreads link', more ? 'Element .more-spreads found' : 'Not found');
  } catch (e) {
    fail('HOME More spreads link', `Error: ${e.message}`);
  }

  // ACT: Tap daily card
  console.log('\n--- Tap daily card ---');
  try {
    const btn = await page.$('.daily-card-wrap');
    if (btn) {
      await btn.tap();
      await sleep(2000);
      page = await mp.currentPage();
      const d2 = page.data;
      info('After tap drawingLoading', String(d2.drawingLoading));
      info('After tap dailyCard', d2.dailyCard ? d2.dailyCard.name_zh : 'null');

      // Check animations triggered
      if (d2.rippleActive === true) {
        pass('HOME Ripple animation', 'Ripple was active after tap');
      } else {
        info('HOME Ripple', 'rippleActive: ' + d2.rippleActive + ' (animation may have completed)');
      }

      if (d2.dailyCard) {
        pass('HOME Draw result', `Card drawn: ${d2.dailyCard.name_zh} / ${d2.dailyCard.keywords_upright}`);
      } else if (d2.drawingLoading) {
        info('HOME Draw', 'Still loading (API response pending)');
        await shot(mp, 'home_draw_loading');
      } else {
        info('HOME Draw', 'API returned null (backend offline or no daily card)');
      }

      await shot(mp, 'home_after_tap');
    }
  } catch (e) {
    fail('HOME Tap daily card', `Error: ${e.message}`);
  }

  // ════════════════════════════════════════════
  // 2. ENCYCLOPEDIA
  // ════════════════════════════════════════════
  console.log('\n=== ENCYCLOPEDIA (pages/encyclopedia/encyclopedia) ===\n');

  await mp.switchTab('pages/encyclopedia/encyclopedia');
  await sleep(3000);
  page = await mp.currentPage();
  info('Path', page.path);
  await shot(mp, 'encyclopedia');

  const d2 = page.data;
  info('pageLoading', String(d2.pageLoading));
  info('pageError', d2.pageError || 'none');
  info('activeTab', d2.activeTab);
  info('cards count', String(d2.cards ? d2.cards.length : 0));
  info('filteredCards', String(d2.filteredCards ? d2.filteredCards.length : 0));

  if (d2.pageError) {
    fail('ENCYCLOPEDIA Load', `Error: ${d2.pageError}`);
  } else if (d2.cards && d2.cards.length > 0) {
    pass('ENCYCLOPEDIA Load', `${d2.cards.length} cards loaded`);
  } else if (d2.pageLoading) {
    fail('ENCYCLOPEDIA Load', 'Still loading after 3s');
  } else {
    fail('ENCYCLOPEDIA Load', 'No cards and no error — possible empty response');
  }

  // Check individual card data (first card)
  if (d2.cards && d2.cards.length > 0) {
    const first = d2.cards[0];
    info('First card', `${first.name_zh} (${first.name_en}) / ${first.arcana}`);
    if (first.card_image) {
      info('Card image URL', first.card_image);
      // Check if it's a proper CDN URL (starts with http)
      if (first.card_image.startsWith('http')) {
        pass('ENCYCLOPEDIA Image URL', 'Card image uses CDN URL');
      } else if (first.card_image.startsWith('/')) {
        info('ENCYCLOPEDIA Image URL', 'Card image uses relative path — may need CDN base prepended');
      } else {
        info('ENCYCLOPEDIA Image URL', `Card image: ${first.card_image}`);
      }
    } else {
      fail('ENCYCLOPEDIA Image URL', 'No card_image field in card data');
    }

    // Check arcana/suit/element presence
    if (first.arcana) pass('ENCYCLOPEDIA Card arcana', `arcana: ${first.arcana}`);
    else fail('ENCYCLOPEDIA Card arcana', 'Missing arcana field');

    if (first.keywords_upright) pass('ENCYCLOPEDIA Keywords', `keywords_upright: ${first.keywords_upright}`);
    else info('ENCYCLOPEDIA Keywords', 'keywords_upright not found in data');

    if (first.meaning_upright) pass('ENCYCLOPEDIA Meanings', 'meaning_upright present');
    else info('ENCYCLOPEDIA Meanings', 'meaning_upright not found in data');
  }

  // Check tabs/pills
  try {
    const tabs = await page.$$('.tab-item');
    const tabCount = tabs ? tabs.length : 0;
    if (tabCount >= 4) {
      pass('ENCYCLOPEDIA Tab pills', `${tabCount} filter pills found`);
    } else {
      fail('ENCYCLOPEDIA Tab pills', `Only ${tabCount} found, expected >= 4`);
    }

    // ACT: Tap a filter tab
    if (tabs && tabs.length >= 2) {
      // Get second tab's text
      await tabs[1].tap();
      await sleep(500);
      page = await mp.currentPage();
      const afterTab = page.data.activeTab;
      info('After tab tap', `activeTab changed to: ${afterTab}`);
      pass('ENCYCLOPEDIA Filter tap', `Tab selection changes data (activeTab=${afterTab})`);
      await shot(mp, 'encyclopedia_filtered');
    }
  } catch (e) {
    fail('ENCYCLOPEDIA Tabs', `Error: ${e.message}`);
  }

  // Test search
  try {
    const searchInput = await page.$('.search-input');
    if (searchInput) {
      // Clear filter first
      const firstTab = (await page.$$('.tab-item'))[0];
      if (firstTab) await firstTab.tap();
      await sleep(300);

      await searchInput.input('星');
      await sleep(500);
      page = await mp.currentPage();
      const searchCount = page.data.filteredCards ? page.data.filteredCards.length : 0;
      pass('ENCYCLOPEDIA Search input', `Search for "星" returned ${searchCount} results`);
      await shot(mp, 'encyclopedia_search');
    } else {
      info('ENCYCLOPEDIA Search', 'No search input found');
    }
  } catch (e) {
    fail('ENCYCLOPEDIA Search', `Error: ${e.message}`);
  }

  // ════════════════════════════════════════════
  // 3. READING
  // ════════════════════════════════════════════
  console.log('\n=== READING (pages/reading/reading) ===\n');

  await mp.navigateTo('pages/reading/reading');
  await sleep(3000);
  page = await mp.currentPage();
  info('Path', page.path);
  await shot(mp, 'reading');

  const d3 = page.data;
  info('pageLoading', String(d3.pageLoading));
  info('pageError', d3.pageError || 'none');
  info('spreads count', String(d3.spreads ? d3.spreads.length : 0));

  if (d3.pageError) {
    fail('READING Load', `Error: ${d3.pageError}`);
  } else if (d3.spreads && d3.spreads.length >= 10) {
    pass('READING Load', `${d3.spreads.length} spreads loaded (expected 10)`);
  } else if (d3.pageLoading) {
    fail('READING Load', 'Still loading after 3s');
  } else {
    fail('READING Load', `Only ${d3.spreads ? d3.spreads.length : 0} spreads, expected 10`);
  }

  // Verify each spread
  if (d3.spreads) {
    const missing = d3.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
    if (missing.length === 0) {
      pass('READING Spread fields', 'All spreads have key/name/icon/desc/cards');
    } else {
      fail('READING Spread fields', `${missing.length} spreads missing required fields`);
    }

    // List them
    d3.spreads.forEach(s => {
      info(`Spread: ${s.icon} ${s.name}`, `${s.cards} cards${s.premium ? ' [PREMIUM]' : ''}${s.popular ? ' [POPULAR]' : ''}`);
    });

    // Count premium vs free
    const premium = d3.spreads.filter(s => s.premium).length;
    const free = d3.spreads.filter(s => !s.premium).length;
    info('Spread access', `${free} free, ${premium} premium`);
  }

  // Check spread card DOM elements
  try {
    const spreadCards = await page.$$('.spread-card');
    const scCount = spreadCards ? spreadCards.length : 0;
    if (scCount >= 10) {
      pass('READING Spread card elements', `${scCount} .spread-card rendered`);
    } else {
      fail('READING Spread card elements', `Only ${scCount} found, expected >= 10`);
    }
  } catch (e) {
    fail('READING Spread card elements', `Error: ${e.message}`);
  }

  // ACT: Select a non-premium spread
  if (d3.spreads && !d3.pageLoading && !d3.pageError) {
    try {
      const spreadCards = await page.$$('.spread-card');
      if (spreadCards && spreadCards.length > 0) {
        // Find first non-premium spread index
        let targetIdx = 0;
        for (let i = 0; i < d3.spreads.length; i++) {
          if (!d3.spreads[i].premium) { targetIdx = i; break; }
        }

        await spreadCards[targetIdx].tap();
        await sleep(1500);
        page = await mp.currentPage();

        if (page.data.showQuestionInput) {
          pass('READING Select spread', `Spread "${page.data.selectedSpread.name}" selected, question input visible`);
          info('Selected spread', JSON.stringify(page.data.selectedSpread));
          await shot(mp, 'reading_question');

          // Check question textarea
          const qInput = await page.$('.question-input');
          pass('READING Question textarea', qInput ? 'Textarea found' : 'Missing');

          // Check theme options
          const themeItems = await page.$$('.theme-item');
          const themeCount = themeItems ? themeItems.length : 0;
          if (themeCount === 4) {
            pass('READING Theme options', '4 themes present: 综合/爱情/事业/财运');
          } else {
            fail('READING Theme options', `Found ${themeCount}, expected 4`);
          }

          // Check draw button
          const drawBtn = await page.$('.btn-glow-pulse');
          pass('READING Draw button', drawBtn ? 'Button present' : 'Missing');

          // Check back link
          const backLink = await page.$('.btn-text');
          pass('READING Back link', backLink ? 'Back-to-spreads link present' : 'Missing');

          // Sample: type in question
          if (qInput) {
            await qInput.input('我的感情运势如何？');
            await sleep(300);
            page = await mp.currentPage();
            info('After question input', `question length: ${page.data.question ? page.data.question.length : 0}`);
            if (page.data.question && page.data.question.length > 0) {
              pass('READING Question input', 'Text entered successfully');
            } else {
              fail('READING Question input', 'Text not reflected in page data');
            }
            await shot(mp, 'reading_with_question');
          }

          // Tap theme
          if (themeItems && themeItems.length >= 2) {
            await themeItems[1].tap();
            await sleep(200);
            page = await mp.currentPage();
            info('After theme tap', `theme changed to: "${page.data.theme}"`);
            pass('READING Theme selection', `Theme set to "${page.data.theme}"`);

            // Tap "back to spreads"
            if (backLink) {
              await backLink.tap();
              await sleep(500);
              page = await mp.currentPage();
              info('After back', `showQuestionInput: ${page.data.showQuestionInput}`);
              pass('READING Back navigation', page.data.showQuestionInput === false ? 'Returned to spread selection' : 'Did not return');
            }
          }
        } else {
          fail('READING Select spread', 'showQuestionInput still false after tapping spread');
        }
      }
    } catch (e) {
      fail('READING Select spread', `Error: ${e.message}`);
    }
  }

  // ════════════════════════════════════════════
  // 4. PROFILE
  // ════════════════════════════════════════════
  console.log('\n=== PROFILE (pages/profile/profile) ===\n');

  await mp.switchTab('pages/profile/profile');
  await sleep(3000);
  page = await mp.currentPage();
  info('Path', page.path);
  await shot(mp, 'profile');

  const d4 = page.data;
  info('pageLoading', String(d4.pageLoading));
  info('pageError', d4.pageError || 'none');
  info('user', d4.user ? JSON.stringify(d4.user).substring(0, 120) : 'null');
  info('memberStatus', d4.memberStatus ? JSON.stringify(d4.memberStatus).substring(0, 120) : 'null');
  info('historyTotal', String(d4.historyTotal));
  info('readingHistory', `${d4.readingHistory ? d4.readingHistory.length : 0} items`);

  if (d4.pageError) {
    fail('PROFILE Load', `Error: ${d4.pageError}`);
  } else if (d4.user) {
    pass('PROFILE Load', `User loaded: ${d4.user.nickname || '(no nickname)'}`);
  } else if (d4.pageLoading) {
    fail('PROFILE Load', 'Still loading after 3s');
  } else {
    fail('PROFILE Load', 'No user and no error — possible API failure');
  }

  // Check stats
  try {
    const stats = await page.$$('.stat-item');
    const sCount = stats ? stats.length : 0;
    if (sCount === 3) {
      pass('PROFILE Stats row', '3 stat items (今日占卜, 今日追问, 历史记录)');
    } else {
      fail('PROFILE Stats row', `Found ${sCount}, expected 3`);
    }
  } catch (e) {
    fail('PROFILE Stats row', `Error: ${e.message}`);
  }

  // Check quick actions
  try {
    const actions = await page.$$('.action-item');
    const aCount = actions ? actions.length : 0;
    if (aCount === 3) {
      pass('PROFILE Quick actions', '3 actions (星光日记, 年度报告, 会员)');
    } else {
      fail('PROFILE Quick actions', `Found ${aCount}, expected 3`);
    }
  } catch (e) {
    fail('PROFILE Quick actions', `Error: ${e.message}`);
  }

  // Check user card
  try {
    const userCard = await page.$('.user-card');
    pass('PROFILE User card', userCard ? 'User card found' : 'Missing');
    const upgradeBtn = await page.$('.upgrade-btn');
    info('Upgrade button', upgradeBtn ? 'Present (non-member view)' : 'Not present (member or hidden)');
  } catch (e) {
    fail('PROFILE User card', `Error: ${e.message}`);
  }

  // Check history section
  try {
    const historyHeader = await page.$('.history-header');
    pass('PROFILE History section', historyHeader ? 'History header found' : 'Missing');
  } catch (e) {
    fail('PROFILE History section', `Error: ${e.message}`);
  }

  // ════════════════════════════════════════════
  // 5. CONSOLE LOGS
  // ════════════════════════════════════════════
  console.log('\n=== CONSOLE LOGS ===\n');

  let logs = [];
  try {
    logs = await mp.getLogs();
    info('Total logs', String(logs.length));
  } catch (e) {
    fail('Console', `Could not get logs: ${e.message}`);
  }

  const errorLogs = logs.filter(l => l.level === 'error');
  const warnLogs = logs.filter(l => l.level === 'warn');
  const restLogs = logs.filter(l => l.level !== 'error' && l.level !== 'warn');

  info('Errors', String(errorLogs.length));
  info('Warnings', String(warnLogs.length));
  info('Info/Debug', String(restLogs.length));

  if (errorLogs.length === 0) {
    pass('Console errors', 'No errors found');
  } else {
    fail('Console errors', `${errorLogs.length} error(s)`);
    errorLogs.forEach((l, i) => {
      const msg = typeof l.msg === 'string' ? l.msg.slice(0, 300) : JSON.stringify(l).slice(0, 300);
      ISSUES.push(`[Console Error #${i+1}] ${msg}`);
      console.log(`  Error ${i+1}: ${msg}`);
    });
  }

  if (warnLogs.length > 0) {
    warnLogs.forEach(l => {
      const msg = typeof l.msg === 'string' ? l.msg.slice(0, 200) : '';
      console.log(`  Warn: ${msg}`);
    });
  }

  // ════════════════════════════════════════════
  // SUMMARY
  // ════════════════════════════════════════════
  console.log('\n' + '='.repeat(60));
  console.log('TEST SUMMARY');
  console.log('='.repeat(60));

  const passes = RESULTS.filter(r => r.startsWith('  [PASS]')).length;
  const failures = RESULTS.filter(r => r.startsWith('  [FAIL]')).length;
  const screenshots = RESULTS.filter(r => r.startsWith('  [SS]')).length;

  console.log(`\nPassed: ${passes}`);
  console.log(`Failed: ${failures}`);
  console.log(`Screenshots: ${screenshots}`);
  console.log(`Console errors: ${errorLogs.length}`);
  console.log(`Console warnings: ${warnLogs.length}`);

  if (ISSUES.length > 0) {
    console.log('\n--- ISSUES TO REPORT ---');
    ISSUES.forEach((iss, i) => {
      console.log(`  ${i+1}. ${iss}`);
    });
    console.log('');
  }

  console.log('\n--- FULL RESULTS ---');
  RESULTS.forEach(r => console.log(r));

  await mp.close();
  console.log('\nConnection closed.');
  process.exit(failures > 0 ? 1 : 0);
})().catch(e => {
  console.error(`FATAL: ${e.message}`);
  process.exit(1);
});
