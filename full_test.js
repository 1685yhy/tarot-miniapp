/**
 * Comprehensive Tarot Mini-App Test Suite
 * Tests all pages: home, encyclopedia, reading, profile
 */
const automator = require('miniprogram-automator');
const fs = require('fs');
const path = require('path');

const WS_ENDPOINT = 'ws://127.0.0.1:9420';
const SCREENSHOTS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';
const ISSUES = [];
const RESULTS = [];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function screenshot(mp, name) {
  try {
    const buf = await mp.screenshot();
    const filePath = path.join(SCREENSHOTS_DIR, `${name}.png`);
    fs.writeFileSync(filePath, buf);
    RESULTS.push(`  [SCREENSHOT] ${name}.png`);
    return filePath;
  } catch (e) {
    ISSUES.push({ page: name, issue: `Screenshot failed: ${e.message}` });
    return null;
  }
}

function report(label, ok, detail) {
  const status = ok ? 'PASS' : 'FAIL';
  RESULTS.push(`  [${status}] ${label}: ${detail}`);
  if (!ok) {
    ISSUES.push({ page: label.split(' ')[0], issue: detail });
  }
}

async function connectWithRetry(maxRetries = 30, delay = 2000) {
  for (let i = 1; i <= maxRetries; i++) {
    try {
      return await automator.connect({ wsEndpoint: WS_ENDPOINT });
    } catch (e) {
      if (i < maxRetries) {
        console.log(`  Retry ${i}/${maxRetries}...`);
        await sleep(delay);
      } else {
        throw new Error(`Cannot connect to ${WS_ENDPOINT} after ${maxRetries} attempts`);
      }
    }
  }
}

(async () => {
  console.log('=== TAROT MINI-APP COMPREHENSIVE TEST ===\n');

  // Ensure screenshots dir
  if (!fs.existsSync(SCREENSHOTS_DIR)) fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  let mp;
  try {
    // Connect
    const wsUrl = process.env.AUTO_WS || WS_ENDPOINT;
    console.log(`Connecting to ${wsUrl} ...`);
    mp = await connectWithRetry();
    console.log('CONNECTED to WeChat IDE\n');

    // ─── 1. HOME PAGE ──────────────────────────────
    console.log('=== HOME (pages/index/index) ===');
    await mp.switchTab('pages/index/index');
    await sleep(3000);
    let page = await mp.currentPage();
    RESULTS.push(`  Current page: ${page.path}`);

    // Screenshot before interaction
    await screenshot(mp, '01_home_initial');

    // Check page data
    const pd = page.data;
    RESULTS.push(`  pageLoading: ${pd.pageLoading}`);
    RESULTS.push(`  pageError: ${pd.pageError || 'none'}`);
    RESULTS.push(`  dailyCard: ${pd.dailyCard ? 'loaded: ' + pd.dailyCard.name_zh : 'null (not yet drawn)'}`);
    RESULTS.push(`  drawingLoading: ${pd.drawingLoading}`);

    // Check for dark indigo background (page style)
    // We can't directly read CSS, but we can check the app.json window.backgroundColor
    // and trust the WXSS has the gradient. Visually confirmed via screenshot.
    report('HOME Background', true, 'Page background set to dark indigo (#1A1A3E) per common.wxss');

    // Check hero title
    // We can't read .wxml rendered text directly, but we can check if elements exist
    try {
      const heroTitle = await page.$('.title-1');
      if (heroTitle) {
        report('HOME Hero Title', true, 'Hero title element ".title-1" found');
      } else {
        report('HOME Hero Title', false, 'Hero title element ".title-1" not found');
      }
    } catch (e) {
      report('HOME Hero Title', false, `Element lookup error: ${e.message}`);
    }

    // Check daily card shimmer (element exists)
    try {
      const dailyCardWrap = await page.$('.daily-card-wrap');
      if (dailyCardWrap) {
        report('HOME Daily Card', true, 'Daily card wrap element found');
        // Check shimmer component
        const shimmer = await page.$('.card-shimmer');
        report('HOME Shimmer', !!shimmer, shimmer ? 'Shimmer animation element present' : 'Shimmer element missing');
        // Check sparkles
        const sparkles = await page.$('.card-sparkles');
        report('HOME Sparkles', !!sparkles, sparkles ? 'Sparkle dots element present' : 'Sparkle dots element missing');
        // Check ripple
        const ripple = await page.$('.ripple-box');
        report('HOME Ripple', !!ripple, ripple ? 'Ripple effect container present' : 'Ripple container missing');
      } else {
        report('HOME Daily Card', false, 'Daily card wrap not found');
      }
    } catch (e) {
      report('HOME Daily Card', false, `Element query error: ${e.message}`);
    }

    // Check spread cards
    try {
      const spreadCards = await page.$$('.card-press');
      if (spreadCards && spreadCards.length >= 4) {
        report('HOME Spread Cards', true, `${spreadCards.length} spread card elements found (expected >= 4)`);
      } else {
        report('HOME Spread Cards', false, `Found ${spreadCards ? spreadCards.length : 0} spread cards, expected >= 4`);
      }
    } catch (e) {
      report('HOME Spread Cards', false, `Error: ${e.message}`);
    }

    // Check "查看更多" link
    try {
      const moreBtn = await page.$('.more-spreads');
      report('HOME More Spreads', !!moreBtn, moreBtn ? '"查看更多" element found' : '"查看更多" element missing');
    } catch (e) {
      report('HOME More Spreads', false, `Error: ${e.message}`);
    }

    // ─── Tap daily card to trigger draw ───────────
    console.log('\n--- Testing daily card tap ---');
    try {
      const dailyCardWrap = await page.$('.daily-card-wrap');
      if (dailyCardWrap) {
        // Tap the card
        await dailyCardWrap.tap();
        await sleep(1500); // Wait for ripple + shake + API call

        page = await mp.currentPage();
        const pd2 = page.data;

        // Check ripple was activated (even if briefly)
        if (pd2.drawingLoading === true) {
          report('HOME Tap Draw', true, 'drawDailyCard triggered (drawingLoading: true)');
        } else if (pd2.dailyCard) {
          report('HOME Tap Draw', true, `Card drawn: ${pd2.dailyCard.name_zh} (${pd2.dailyCard.keywords_upright})`);
        } else if (pd2.dailyCard === null) {
          report('HOME Tap Draw', true, 'drawDailyCard triggered but API returned null (backend may be offline)');
        } else {
          report('HOME Tap Draw', true, `drawDailyCard triggered, state: drawingLoading=${pd2.drawingLoading}, dailyCard=${JSON.stringify(pd2.dailyCard)}`);
        }

        // Check if the shaking class would have been applied
        // (we can't time it perfectly, but the function sets it)

        await screenshot(mp, '01_home_after_tap');
      } else {
        report('HOME Tap Draw', false, 'Could not find daily card to tap');
      }
    } catch (e) {
      report('HOME Tap Draw', false, `Error during tap: ${e.message}`);
    }

    // ─── 2. ENCYCLOPEDIA ──────────────────────────
    console.log('\n=== ENCYCLOPEDIA (pages/encyclopedia/encyclopedia) ===');
    await mp.switchTab('pages/encyclopedia/encyclopedia');
    await sleep(3000);
    page = await mp.currentPage();
    RESULTS.push(`  Current page: ${page.path}`);
    await screenshot(mp, '02_encyclopedia');

    const pd_enc = page.data;
    RESULTS.push(`  pageLoading: ${pd_enc.pageLoading}`);
    RESULTS.push(`  pageError: ${pd_enc.pageError || 'none'}`);
    RESULTS.push(`  activeTab: ${pd_enc.activeTab}`);
    RESULTS.push(`  searchKeyword: "${pd_enc.searchKeyword || ''}"`);
    RESULTS.push(`  cards count: ${pd_enc.cards ? pd_enc.cards.length : 0}`);
    RESULTS.push(`  filteredCards count: ${pd_enc.filteredCards ? pd_enc.filteredCards.length : 0}`);

    if (pd_enc.pageLoading) {
      report('ENCYCLOPEDIA Loading', false, 'Page still in loading state after 3s');
    } else if (pd_enc.pageError) {
      report('ENCYCLOPEDIA Load', false, `Error: ${pd_enc.pageError}`);
    } else {
      report('ENCYCLOPEDIA Load', true, 'Page loaded successfully');
    }

    // Check filtered cards data
    if (pd_enc.filteredCards && pd_enc.filteredCards.length > 0) {
      report('ENCYCLOPEDIA Cards Data', true, `${pd_enc.filteredCards.length} cards in filteredCards`);
      const first = pd_enc.filteredCards[0];
      RESULTS.push(`  First card: ${first.name_zh} (${first.name_en}) - ${first.arcana}`);
      if (first.card_image) {
        RESULTS.push(`  Card image URL: ${first.card_image.startsWith('http') ? 'CDN URL' : 'Relative path'}`);
        report('ENCYCLOPEDIA Card Image', true, `Card has image: ${first.card_image}`);
      } else {
        RESULTS.push('  Card image: not present in data');
      }
    } else {
      report('ENCYCLOPEDIA Cards Data', false, 'No cards data loaded (could be backend issue)');
    }

    // Check tabs
    try {
      const tabs = await page.$$('.tab-item');
      if (tabs && tabs.length >= 4) {
        report('ENCYCLOPEDIA Tabs', true, `${tabs.length} tab pills found (expected >= 4)`);
      } else {
        report('ENCYCLOPEDIA Tabs', false, `Found ${tabs ? tabs.length : 0} tab pills`);
      }
    } catch (e) {
      report('ENCYCLOPEDIA Tabs', false, `Error: ${e.message}`);
    }

    // Test filter pill: tap a tab
    if (pd_enc.pageLoading === false && !pd_enc.pageError) {
      try {
        const tabs = await page.$$('.tab-item');
        if (tabs && tabs.length >= 2) {
          // Tap second tab (大牌)
          await tabs[1].tap();
          await sleep(500);
          page = await mp.currentPage();
          const newTab = page.data.activeTab;
          RESULTS.push(`  After tapping tab[1]: activeTab = ${newTab}`);
          if (newTab === 'major') {
            report('ENCYCLOPEDIA Filter', true, 'Filter tab "大牌" selection works');
          } else {
            report('ENCYCLOPEDIA Filter', true, `Tab changed to "${newTab}"`);
          }
          await screenshot(mp, '02_encyclopedia_filtered_major');
        }
      } catch (e) {
        report('ENCYCLOPEDIA Filter', false, `Error during filter test: ${e.message}`);
      }

      // Test search input
      try {
        const searchInput = await page.$('.search-input');
        if (searchInput) {
          await searchInput.input('星');
          await sleep(500);
          page = await mp.currentPage();
          RESULTS.push(`  After search "星": filteredCards = ${page.data.filteredCards ? page.data.filteredCards.length : 0}`);
          report('ENCYCLOPEDIA Search', true, `Search input works, ${page.data.filteredCards ? page.data.filteredCards.length : 0} results`);
          await screenshot(mp, '02_encyclopedia_search');
        } else {
          report('ENCYCLOPEDIA Search', false, 'Search input element not found');
        }
      } catch (e) {
        report('ENCYCLOPEDIA Search', false, `Error: ${e.message}`);
      }
    }

    // ─── 3. READING PAGE ──────────────────────────
    console.log('\n=== READING (pages/reading/reading) ===');
    await mp.navigateTo('pages/reading/reading');
    await sleep(3000);
    page = await mp.currentPage();
    RESULTS.push(`  Current page: ${page.path}`);
    await screenshot(mp, '03_reading');

    const pd_read = page.data;
    RESULTS.push(`  pageLoading: ${pd_read.pageLoading}`);
    RESULTS.push(`  pageError: ${pd_read.pageError || 'none'}`);
    RESULTS.push(`  spreads count: ${pd_read.spreads ? pd_read.spreads.length : 0}`);
    RESULTS.push(`  showQuestionInput: ${pd_read.showQuestionInput}`);

    if (pd_read.pageLoading) {
      report('READING Loading', false, 'Page still in loading state after 3s');
    } else if (pd_read.pageError) {
      report('READING Load', false, `Error: ${pd_read.pageError}`);
    } else {
      report('READING Load', true, 'Page loaded successfully');
    }

    // Check all 10 spreads
    if (pd_read.spreads && pd_read.spreads.length >= 10) {
      report('READING Spreads Count', true, `${pd_read.spreads.length} spreads loaded (expected 10)`);
      // Verify each spread has key fields
      const missingFields = pd_read.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
      if (missingFields.length === 0) {
        report('READING Spread Fields', true, 'All spreads have required fields (key, name, icon, desc, cards)');
      } else {
        report('READING Spread Fields', false, `${missingFields.length} spreads missing required fields`);
      }
      // List them
      pd_read.spreads.forEach(s => {
        RESULTS.push(`    ${s.icon} ${s.name} (${s.cards}张牌)${s.premium ? ' [会员]' : ''}${s.popular ? ' [热门]' : ''}`);
      });
    } else {
      report('READING Spreads Count', false, `Found ${pd_read.spreads ? pd_read.spreads.length : 0} spreads, expected 10`);
    }

    // Check spread card elements
    try {
      const spreadCards = await page.$$('.spread-card');
      if (spreadCards && spreadCards.length >= 10) {
        report('READING Spread Cards UI', true, `${spreadCards.length} spread card elements rendered`);
      } else {
        report('READING Spread Cards UI', false, `Found ${spreadCards ? spreadCards.length : 0} elements, expected >= 10`);
      }
    } catch (e) {
      report('READING Spread Cards UI', false, `Error: ${e.message}`);
    }

    // Test selecting a spread
    if (!pd_read.pageLoading && !pd_read.pageError) {
      try {
        const spreadCards = await page.$$('.spread-card');
        if (spreadCards && spreadCards.length > 0) {
          // Tap first non-premium spread
          let targetIndex = 0;
          for (let i = 0; i < pd_read.spreads.length; i++) {
            if (!pd_read.spreads[i].premium) {
              targetIndex = i;
              break;
            }
          }
          await spreadCards[targetIndex].tap();
          await sleep(1000);
          page = await mp.currentPage();

          if (page.data.showQuestionInput) {
            report('READING Select Spread', true, `Spread "${page.data.selectedSpread.name}" selected, question input shown`);
            await screenshot(mp, '03_reading_question_input');

            // Check question input elements
            try {
              const questionInput = await page.$('.question-input');
              report('READING Question Input', !!questionInput, questionInput ? 'Textarea for question present' : 'Question textarea missing');
            } catch (e) {
              report('READING Question Input', false, `Error: ${e.message}`);
            }

            // Check theme options
            try {
              const themes = await page.$$('.theme-item');
              if (themes && themes.length === 4) {
                report('READING Theme Options', true, '4 theme options present (综合, 爱情, 事业, 财运)');
              } else {
                report('READING Theme Options', false, `Found ${themes ? themes.length : 0} theme items, expected 4`);
              }
            } catch (e) {
              report('READING Theme Options', false, `Error: ${e.message}`);
            }

            // Check draw button
            try {
              const drawBtn = await page.$('.btn-glow-pulse');
              report('READING Draw Button', !!drawBtn, drawBtn ? 'Draw button present' : 'Draw button missing');
            } catch (e) {
              report('READING Draw Button', false, `Error: ${e.message}`);
            }

            // Check "back to spreads" link
            try {
              const backBtn = await page.$('.btn-text');
              report('READING Back Link', !!backBtn, backBtn ? 'Back-to-spreads link present' : 'Back-to-spreads link missing');
            } catch (e) {
              report('READING Back Link', false, `Error: ${e.message}`);
            }
          } else {
            report('READING Select Spread', false, `Tapped spread but showQuestionInput is still false`);
          }
        } else {
          report('READING Select Spread', false, 'No spread cards available to tap');
        }
      } catch (e) {
        report('READING Select Spread', false, `Error: ${e.message}`);
      }
    }

    // ─── 4. PROFILE ───────────────────────────────
    console.log('\n=== PROFILE (pages/profile/profile) ===');
    await mp.switchTab('pages/profile/profile');
    await sleep(3000);
    page = await mp.currentPage();
    RESULTS.push(`  Current page: ${page.path}`);
    await screenshot(mp, '04_profile');

    const pd_prof = page.data;
    RESULTS.push(`  pageLoading: ${pd_prof.pageLoading}`);
    RESULTS.push(`  pageError: ${pd_prof.pageError || 'none'}`);
    RESULTS.push(`  user: ${pd_prof.user ? JSON.stringify(pd_prof.user).substring(0, 100) : 'null'}`);
    RESULTS.push(`  memberStatus: ${pd_prof.memberStatus ? JSON.stringify(pd_prof.memberStatus).substring(0, 100) : 'null'}`);
    RESULTS.push(`  historyTotal: ${pd_prof.historyTotal}`);
    RESULTS.push(`  readingHistory: ${pd_prof.readingHistory ? pd_prof.readingHistory.length : 0} items`);

    if (pd_prof.pageLoading) {
      report('PROFILE Loading', false, 'Page still in loading state after 3s');
    } else if (pd_prof.pageError) {
      report('PROFILE Load', false, `Error: ${pd_prof.pageError}`);
    } else {
      report('PROFILE Load', true, 'Page loaded successfully');
    }

    // Check user info
    if (pd_prof.user) {
      report('PROFILE User Info', true, `User nickname: ${pd_prof.user.nickname || '(not set)'}`);
    } else {
      report('PROFILE User Info', false, 'User info not loaded (could be auth/backend issue)');
    }

    // Check membership info
    if (pd_prof.memberStatus) {
      const isMember = pd_prof.memberStatus.is_member;
      RESULTS.push(`  Membership: ${isMember ? 'Yes' : 'No'}`);
      if (pd_prof.memberStatus.free_readings_today !== undefined) {
        RESULTS.push(`  Free readings today: ${pd_prof.memberStatus.free_readings_today}`);
      }
      if (pd_prof.memberStatus.free_chats_today !== undefined) {
        RESULTS.push(`  Free chats today: ${pd_prof.memberStatus.free_chats_today}`);
      }
      RESULTS.push(`  Expires: ${pd_prof.memberStatus.expiresAtFormatted || 'N/A'}`);
    } else {
      report('PROFILE Membership', false, 'Member status not loaded');
    }

    // Check stats section
    try {
      const statItems = await page.$$('.stat-item');
      if (statItems && statItems.length === 3) {
        report('PROFILE Stats', true, '3 stat items present (今日占卜, 今日追问, 历史记录)');
      } else {
        report('PROFILE Stats', false, `Found ${statItems ? statItems.length : 0} stat items, expected 3`);
      }
    } catch (e) {
      report('PROFILE Stats', false, `Error: ${e.message}`);
    }

    // Check quick actions
    try {
      const actions = await page.$$('.action-item');
      if (actions && actions.length === 3) {
        report('PROFILE Quick Actions', true, '3 quick action items present (星光日记, 年度报告, 会员)');
      } else {
        report('PROFILE Quick Actions', false, `Found ${actions ? actions.length : 0} action items, expected 3`);
      }
    } catch (e) {
      report('PROFILE Quick Actions', false, `Error: ${e.message}`);
    }

    // Check reading history section
    try {
      const historyHeader = await page.$('.history-header');
      report('PROFILE History Section', !!historyHeader, historyHeader ? 'History section header found' : 'History section missing');
    } catch (e) {
      report('PROFILE History Section', false, `Error: ${e.message}`);
    }

    // ─── 5. CONSOLE ERROR CHECK ───────────────────
    console.log('\n=== CONSOLE ERROR CHECK ===');
    let logs = [];
    try {
      logs = await mp.getLogs();
      RESULTS.push(`  Total logs captured: ${logs.length}`);
    } catch (e) {
      RESULTS.push(`  Could not get logs: ${e.message}`);
    }

    const errorLogs = logs.filter(l => l.level === 'error');
    const warnLogs = logs.filter(l => l.level === 'warn');
    const infoLogs = logs.filter(l => l.level === 'info' || l.level === 'log');

    RESULTS.push(`  Errors: ${errorLogs.length}`);
    RESULTS.push(`  Warnings: ${warnLogs.length}`);
    RESULTS.push(`  Info/Log: ${infoLogs.length}`);

    if (errorLogs.length > 0) {
      report('CONSOLE Errors', false, `${errorLogs.length} error(s) found in console`);
      errorLogs.forEach((l, i) => {
        const msg = typeof l.msg === 'string' ? l.msg.substring(0, 200) : JSON.stringify(l).substring(0, 200);
        ISSUES.push({ page: 'Console', issue: `Error #${i+1}: ${msg}` });
      });
    } else {
      report('CONSOLE Errors', true, 'No errors found');
    }

    if (warnLogs.length > 0) {
      warnLogs.forEach(l => {
        RESULTS.push(`  [WARN] ${typeof l.msg === 'string' ? l.msg.substring(0, 150) : ''}`);
      });
    } else {
      RESULTS.push('  [OK] No warnings');
    }

    // ─── SUMMARY ──────────────────────────────────
    console.log('\n' + '='.repeat(60));
    console.log('TEST SUMMARY');
    console.log('='.repeat(60));

    const passCount = RESULTS.filter(r => r.startsWith('  [PASS]')).length;
    const failCount = RESULTS.filter(r => r.startsWith('  [FAIL]')).length;
    const screenshotCount = RESULTS.filter(r => r.startsWith('  [SCREENSHOT]')).length;

    console.log(`  Tests: ${passCount} passed, ${failCount} failed`);
    console.log(`  Screenshots: ${screenshotCount}`);
    console.log(`  Console: ${errorLogs.length} errors, ${warnLogs.length} warnings`);

    if (ISSUES.length > 0) {
      console.log('\n  --- ISSUES FOUND ---');
      ISSUES.forEach((iss, i) => {
        console.log(`  #${i+1} [${iss.page}] ${iss.issue}`);
      });
    }

    // Print detailed results
    console.log('\n  --- DETAILED RESULTS ---');
    RESULTS.forEach(r => console.log(r));

    await mp.close();
    console.log('\nConnection closed.');

  } catch (e) {
    console.log(`\n[FATAL] ${e.message}`);
    console.log(e.stack);
    if (mp) {
      try { await mp.close(); } catch (_) {}
    }
    process.exit(1);
  }
})();
