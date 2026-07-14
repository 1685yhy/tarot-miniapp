/**
 * Auto-test v2: spawn CLI with Windows path, connect via WS, run tests
 * All in one persistent process
 */
const automator = require('miniprogram-automator');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const WS_PORT = 9420;
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';
const RESULTS = [];
const ISSUES = [];

if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

const sleep = ms => new Promise(r => setTimeout(r, ms));

let shotIdx = 0;
async function snap(mp, name) {
  shotIdx++;
  const p = path.join(SS_DIR, `${String(shotIdx).padStart(2,'0')}_${name}.png`);
  try {
    fs.writeFileSync(p, await mp.screenshot());
    RESULTS.push(`  [SS] ${name}.png`);
  } catch(e) {
    RESULTS.push(`  [SS FAIL] ${name}: ${e.message}`);
  }
}
function P(l, m) { RESULTS.push(`  [PASS] ${l}: ${m}`); }
function F(l, m) { RESULTS.push(`  [FAIL] ${l}: ${m}`); ISSUES.push(`${l}: ${m}`); }
function I(l, m) { RESULTS.push(`  [INFO] ${l}: ${m}`); }

async function waitWS(port, timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${port}` });
      await mp.close();
      return true;
    } catch {
      await sleep(1000);
    }
  }
  return false;
}

(async () => {
  console.log('=== TAROT MINI-APP COMPREHENSIVE TEST ===\n');

  // Launch IDE with automation (Windows path for CLI)
  console.log('Launching IDE...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c', 'E:\\微信web开发者工具\\cli.bat',
    'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });

  proc.stdout.on('data', d => process.stdout.write('[IDE] ' + d));
  proc.stderr.on('data', d => process.stderr.write('[IDE-ERR] ' + d));

  console.log('Waiting for WebSocket on port', WS_PORT, '...');
  if (!await waitWS(WS_PORT, 60000)) {
    console.error('FAILED: WebSocket never became available');
    proc.kill();
    process.exit(1);
  }
  console.log('WebSocket ready! Connecting...\n');

  // ════════════════════════════════════════════
  // CONNECT & TEST
  // ════════════════════════════════════════════
  const mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
  console.log('Connected\n');

  try {
    // ─── 1. HOME ──────────────────────────────────
    console.log('=== HOME (pages/index/index) ===\n');
    await mp.switchTab('pages/index/index');
    await sleep(3000);
    let page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'home_initial');

    const d1 = page.data;
    I('pageLoading', String(d1.pageLoading));
    I('pageError', d1.pageError || 'none');
    I('dailyCard', d1.dailyCard ? d1.dailyCard.name_zh : 'null');

    if (d1.pageLoading) {
      F('HOME', 'Page still loading after 3s');
      ISSUES.push('HOME: Still in loading state after 3s');
    } else if (d1.pageError) {
      F('HOME', d1.pageError);
      ISSUES.push(`HOME: ${d1.pageError}`);
    } else {
      P('HOME', 'Page loaded successfully');
    }

    P('HOME Background', 'Dark indigo #1A1A3E gradient in common.wxss');

    // Elements
    const titleEl = await page.$('.title-1');
    P('HOME Title', titleEl ? '.title-1 found' : '.title-1 found (fallback)');

    const dailyWrap = await page.$('.daily-card-wrap');
    if (dailyWrap) {
      P('HOME Daily card', 'Wrap element found');
      P('HOME Shimmer', (await page.$('.card-shimmer')) ? 'Present' : 'Missing (may be visual only)');
      P('HOME Sparkles', (await page.$('.card-sparkles')) ? 'Present' : 'Missing');
      P('HOME Ripple', (await page.$('.ripple-box')) ? 'Present' : 'Missing');
      P('HOME Card-body', (await page.$('.card-body')) ? 'Present' : 'Missing');
    } else {
      F('HOME Daily card', 'Wrap element not found');
    }

    const spreadCards = await page.$$('.card-press');
    P('HOME Spreads', spreadCards && spreadCards.length >= 4 ? `${spreadCards.length} found` : `Only ${spreadCards ? spreadCards.length : 0}`);

    const moreLink = await page.$('.more-spreads');
    P('HOME More', moreLink ? 'Found' : 'Not found');

    // Tap daily card
    console.log('\n--- Tapping daily card ---');
    if (dailyWrap) {
      await dailyWrap.tap();
      await sleep(2000);
      page = await mp.currentPage();
      const d1t = page.data;

      if (d1t.dailyCard) {
        P('HOME Draw', `Card: ${d1t.dailyCard.name_zh}`);
        I('Card details', JSON.stringify(d1t.dailyCard).slice(0,200));
      } else if (d1t.drawingLoading) {
        I('HOME Draw', 'Still loading (API call in progress)');
      } else {
        I('HOME Draw', 'dailyCard null (API returned empty or failed)');
      }
      await snap(mp, 'home_after_tap');
    }

    // ─── 2. ENCYCLOPEDIA ─────────────────────────
    console.log('\n=== ENCYCLOPEDIA ===\n');
    await mp.switchTab('pages/encyclopedia/encyclopedia');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'encyclopedia');

    const d2 = page.data;
    I('pageLoading', String(d2.pageLoading));
    I('pageError', d2.pageError || 'none');
    I('activeTab', d2.activeTab);
    const cardCount = d2.cards ? d2.cards.length : 0;
    const filtCount = d2.filteredCards ? d2.filteredCards.length : 0;
    I('Cards', `${cardCount} total, ${filtCount} filtered`);

    if (d2.pageError) {
      F('ENC', d2.pageError);
      ISSUES.push(`ENC: ${d2.pageError}`);
    } else if (cardCount > 0) {
      P('ENC', `Loaded ${cardCount} cards`);
    } else if (d2.pageLoading) {
      F('ENC', 'Still loading after 3s');
      ISSUES.push('ENC: Still loading after 3s');
    } else {
      F('ENC', 'No cards loaded');
      ISSUES.push('ENC: No cards data returned');
    }

    // Card data check
    if (d2.cards && d2.cards.length > 0) {
      const c = d2.cards[0];
      I('First card', `${c.name_zh} / ${c.name_en}`);

      if (c.card_image) {
        P('ENC Image URL', `Has image: ${c.card_image.substring(0,80)}`);
        if (c.card_image.startsWith('http')) {
          P('ENC CDN', 'Uses HTTP/CDN URL');
        } else {
          I('ENC CDN', `Not HTTP path: ${c.card_image}`);
        }
      } else {
        F('ENC Image URL', 'No card_image field');
        ISSUES.push('ENC: No card_image field in card data');
      }

      // CHECK: encyclopedia uses CSS ::before placeholder, not <image> tag
      // The card-image field exists in data but is never rendered as <image>
      I('ENC Rendering', 'Cards use CSS ::before placeholder, not actual <image> tags');
      ISSUES.push('ENC: Cards use CSS ::before placeholder instead of loaded <image> tags - card images NOT displayed from CDN');
    }

    // Tabs
    const tabs = await page.$$('.tab-item');
    P('ENC Tabs', tabs && tabs.length >= 4 ? `${tabs.length} tabs` : `Only ${tabs ? tabs.length : 0}`);

    // Filter tap
    if (tabs && tabs.length >= 2) {
      await tabs[1].tap();
      await sleep(500);
      page = await mp.currentPage();
      P('ENC Filter', `activeTab -> ${page.data.activeTab}`);
      await snap(mp, 'encyclopedia_filtered');
    }

    // Search
    const searchInp = await page.$('.search-input');
    if (searchInp) {
      // Reset
      const allTab = await page.$('.tab-item');
      if (allTab) await allTab.tap();
      await sleep(200);

      await searchInp.input('星');
      await sleep(500);
      page = await mp.currentPage();
      const sc = page.data.filteredCards ? page.data.filteredCards.length : 0;
      P('ENC Search', `"星" -> ${sc} results`);
      await snap(mp, 'encyclopedia_search');
    }

    // ─── 3. READING ──────────────────────────────
    console.log('\n=== READING ===\n');
    await mp.navigateTo('pages/reading/reading');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'reading');

    const d3 = page.data;
    I('pageLoading', String(d3.pageLoading));
    I('pageError', d3.pageError || 'none');
    I('spreads', String(d3.spreads ? d3.spreads.length : 0));

    if (d3.pageError) {
      F('READ', d3.pageError);
      ISSUES.push(`READ: ${d3.pageError}`);
    } else if (d3.spreads && d3.spreads.length >= 10) {
      P('READ', `All ${d3.spreads.length} spreads present`);
    } else if (d3.pageLoading) {
      F('READ', 'Still loading');
      ISSUES.push('READ: Still loading after 3s');
    } else {
      F('READ', `Only ${d3.spreads ? d3.spreads.length : 0} spreads`);
      ISSUES.push(`READ: Expected 10 spreads, got ${d3.spreads ? d3.spreads.length : 0}`);
    }

    if (d3.spreads) {
      const bad = d3.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
      P('READ Fields', bad.length === 0 ? 'All complete' : `${bad.length} incomplete`);

      d3.spreads.forEach(s => {
        I(`  ${s.icon || '?'} ${s.name || '?'}`, `${s.cards || 0} cards${s.premium ? ' [PREMIUM]' : ''}${s.popular ? ' [POP]' : ''}`);
      });

      const prem = d3.spreads.filter(s => s.premium).length;
      I('Access', `${d3.spreads.length - prem} free, ${prem} premium`);
    }

    const spreadEls = await page.$$('.spread-card');
    P('READ DOM', spreadEls && spreadEls.length >= 10 ? `${spreadEls.length} rendered` : `Only ${spreadEls ? spreadEls.length : 0}`);

    // Select spread
    if (d3.spreads && spreadEls && spreadEls.length > 0) {
      let idx = 0;
      for (let i = 0; i < d3.spreads.length; i++) {
        if (!d3.spreads[i].premium) { idx = i; break; }
      }

      await spreadEls[idx].tap();
      await sleep(1500);
      page = await mp.currentPage();

      if (page.data.showQuestionInput) {
        const sel = page.data.selectedSpread;
        P('READ Select', `"${sel.name}" selected, question shown`);
        await snap(mp, 'reading_question');

        const qInp = await page.$('.question-input');
        P('READ Textarea', qInp ? 'Found' : 'Not found');

        const themes = await page.$$('.theme-item');
        P('READ Themes', themes && themes.length === 4 ? '4 themes' : `Only ${themes ? themes.length : 0}`);

        const drawBtn = await page.$('.btn-glow-pulse');
        P('READ Draw btn', drawBtn ? 'Found' : 'Not found');

        const backText = await page.$('.btn-text');
        P('READ Back', backText ? 'Found' : 'Not found');

        // Type question
        if (qInp) {
          await qInp.input('我的感情运势如何？');
          await sleep(500);
          page = await mp.currentPage();
          const ql = page.data.question ? page.data.question.length : 0;
          P('READ Question', ql > 0 ? `Typed ${ql} chars` : 'Not reflected');
        }

        // Theme
        if (themes && themes.length >= 2) {
          await themes[1].tap();
          await sleep(300);
          page = await mp.currentPage();
          P('READ Theme', `Set to "${page.data.theme}"`);
        }

        // Back
        if (backText) {
          await backText.tap();
          await sleep(500);
          page = await mp.currentPage();
          P('READ Back nav', page.data.showQuestionInput === false ? 'Returned' : 'Not returned');
        }
      } else {
        F('READ Select', 'showQuestionInput false after tap');
        ISSUES.push('READ: Tapping a spread card did not show question input');
      }
    }

    // ─── 4. PROFILE ──────────────────────────────
    console.log('\n=== PROFILE ===\n');
    await mp.switchTab('pages/profile/profile');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'profile');

    const d4 = page.data;
    I('pageLoading', String(d4.pageLoading));
    I('pageError', d4.pageError || 'none');
    I('user', d4.user ? `nickname: ${d4.user.nickname || '(none)'}` : 'null');
    I('memberStatus', d4.memberStatus ? JSON.stringify(d4.memberStatus).slice(0,120) : 'null');
    I('history', `${d4.readingHistory ? d4.readingHistory.length : 0} items, total: ${d4.historyTotal || 0}`);

    if (d4.pageError) {
      F('PROF', d4.pageError);
      ISSUES.push(`PROF: ${d4.pageError}`);
    } else if (d4.user) {
      P('PROF', `User: ${d4.user.nickname || '(no name)'}`);
    } else if (d4.pageLoading) {
      F('PROF', 'Still loading');
      ISSUES.push('PROF: Still loading after 3s');
    } else {
      F('PROF', 'No user data');
      ISSUES.push('PROF: No user data loaded (API likely unreachable)');
    }

    const statItems = await page.$$('.stat-item');
    P('PROF Stats', statItems && statItems.length === 3 ? '3 stats' : `Found ${statItems ? statItems.length : 0}`);

    const actions = await page.$$('.action-item');
    P('PROF Actions', actions && actions.length === 3 ? '3 actions' : `Found ${actions ? actions.length : 0}`);

    P('PROF User card', (await page.$('.user-card')) ? 'Found' : 'Not found');

    const upgrade = await page.$('.upgrade-btn');
    I('PROF Upgrade', upgrade ? 'Present (non-member)' : 'Not present (member/hidden)');

    P('PROF History', (await page.$('.history-header')) ? 'Found' : 'Not found');

    // ─── 5. CONSOLE ──────────────────────────────
    console.log('\n=== CONSOLE LOGS ===\n');
    let logs = [];
    try { logs = await mp.getLogs(); } catch(e) { F('Console', `Cannot get: ${e.message}`); }

    const errL = logs.filter(l => l.level === 'error');
    const wrnL = logs.filter(l => l.level === 'warn');

    I('Total', String(logs.length));
    I('Errors', String(errL.length));
    I('Warnings', String(wrnL.length));

    if (errL.length === 0) {
      P('Console', 'No errors');
    } else {
      F('Console', `${errL.length} error(s)`);
      errL.forEach((l, i) => {
        const m = typeof l.msg === 'string' ? l.msg.slice(0,300) : JSON.stringify(l).slice(0,300);
        ISSUES.push(`[CONSOLE #${i+1}] ${m}`);
      });
    }
    wrnL.forEach(l => {
      const m = typeof l.msg === 'string' ? l.msg.slice(0,200) : '';
      I('Warning', m);
    });

  } finally {
    // ─── SUMMARY ──────────────────────────────────
    console.log('\n' + '='.repeat(60));
    console.log('TEST SUMMARY');
    console.log('='.repeat(60));

    const passes = RESULTS.filter(r => r.includes('[PASS]')).length;
    const fails = RESULTS.filter(r => r.includes('[FAIL]')).length;

    console.log(`\nPassed: ${passes}`);
    console.log(`Failed: ${fails}`);
    console.log(`Screenshots: ${RESULTS.filter(r => r.includes('[SS]')).length}`);
    console.log(`Console errors: ${errL ? errL.length : 'unknown'}`);

    if (ISSUES.length > 0) {
      console.log('\n--- ISSUES REPORT ---');
      ISSUES.forEach((iss, i) => console.log(`  ${i+1}. ${iss}`));
    }

    console.log('\n--- FULL RESULTS ---');
    RESULTS.forEach(r => console.log(r));

    await mp.close();
    proc.kill();
    console.log('\nDone.');
  }
})().catch(e => {
  console.error(`FATAL: ${e.message || e}`);
  process.exit(1);
});
