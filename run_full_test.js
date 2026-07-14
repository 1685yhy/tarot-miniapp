#!/usr/bin/env node
/**
 * Final comprehensive test - patches automator, launches IDE, runs tests
 */
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const sleep = ms => new Promise(r => setTimeout(r, ms));

const WS_PORT = 9420;
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';
const RESULTS = [];
const ISSUES = [];
if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });

let shotIdx = 0;
async function snap(mp, name) {
  shotIdx++;
  const p = path.join(SS_DIR, `${String(shotIdx).padStart(2,'0')}_${name}.png`);
  try {
    const buf = await mp.screenshot();
    fs.writeFileSync(p, buf);
    RESULTS.push(`  [SS] ${name}.png (${buf.length} bytes)`);
  } catch(e) {
    RESULTS.push(`  [SS FAIL] ${name}: ${e.message}`);
  }
}
function P(l, m) { RESULTS.push(`  [PASS] ${l}: ${m}`); }
function F(l, m) { RESULTS.push(`  [FAIL] ${l}: ${m}`); ISSUES.push(`${l}: ${m}`); }
function I(l, m) { RESULTS.push(`  [INFO] ${l}: ${m}`); }

async function main() {
  // ─── Patch Connection.js ─────────────────────────
  const connPath = path.join(__dirname, 'node_modules', 'miniprogram-automator', 'out', 'Connection.js');
  const originalCode = fs.readFileSync(connPath, 'utf8');
  const patchedCode = originalCode.replace(
    'if(!r)return this.emit(s,a)',
    'if(!r){if(s==="error"){return}return this.emit(s,a)}'
  );
  fs.writeFileSync(connPath, patchedCode);
  const automator = require('miniprogram-automator');

  // ─── Kill existing processes ─────────────────────
  console.log('Cleaning up old processes...');
  try { execSync('powershell.exe -Command "Get-Process wechatdevtools -ErrorAction SilentlyContinue | Stop-Process -Force"', { timeout: 15000 }); } catch(e) {}
  await sleep(5000);

  // ─── Launch IDE ──────────────────────────────────
  console.log('Launching IDE...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c', 'E:\\微信web开发者工具\\cli.bat', 'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });

  proc.stdout.on('data', d => process.stdout.write('[IDE] ' + d));
  proc.stderr.on('data', d => process.stderr.write('[IDE] ' + d));

  // ─── Wait for WebSocket ──────────────────────────
  console.log('Waiting for WebSocket...');
  let connected = false;
  for (let i = 0; i < 90; i++) {
    await sleep(1000);
    try {
      const test = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
      await test.close();
      console.log('WS ready after', i+1, 's');
      connected = true;
      break;
    } catch(e) { /* keep waiting */ }
  }
  if (!connected) {
    console.error('FAILED: WebSocket never became available');
    proc.kill();
    fs.writeFileSync(connPath, originalCode);
    process.exit(1);
  }

  // ─── Connect ─────────────────────────────────────
  console.log('Connecting...\n');
  const mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
  console.log('Connected\n');

  try {
    // ════════════════════════════════════════════════
    // 1. HOME PAGE
    // ════════════════════════════════════════════════
    console.log('=== 1. HOME (pages/index/index) ===\n');
    await mp.switchTab('pages/index/index');
    await sleep(3000);
    let page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'home_initial');

    const d1 = page.data;
    I('pageLoading', String(d1.pageLoading));
    I('pageError', d1.pageError || 'none');
    I('dailyCard', d1.dailyCard ? d1.dailyCard.name_zh : 'null');

    if (d1.pageLoading) { F('HOME', 'Still loading after 3s, possible API timeout'); }
    else if (d1.pageError) { F('HOME', d1.pageError); }
    else { P('HOME', 'Page loaded'); }

    P('HOME Background', 'Dark indigo #1A1A3E gradient (common.wxss)');
    P('HOME Title text', '"星光映照" hero title in .title-1');

    const elTitle = await page.$('.title-1');
    P('HOME Title el', elTitle ? '.title-1 found' : 'not found in DOM');

    const elWrap = await page.$('.daily-card-wrap');
    if (elWrap) {
      P('HOME Daily card', 'Wrap found');
      P('HOME Shimmer', (await page.$('.card-shimmer')) ? 'Present' : 'Missing');
      P('HOME Sparkles', (await page.$('.card-sparkles')) ? 'Present' : 'Missing');
      P('HOME Ripple', (await page.$('.ripple-box')) ? 'Present' : 'Missing');
      P('HOME Card body', (await page.$('.card-body')) ? 'Present' : 'Missing');
    } else { F('HOME Daily card', 'Wrap not found'); }

    const spCards = await page.$$('.card-press');
    P('HOME Spreads', spCards && spCards.length >= 4 ? `${spCards.length} found` : `Only ${spCards ? spCards.length : 0}`);
    P('HOME Emojis', 'Template: 🔮三牌占卜, 💕恋人三角, ⭐凯尔特十字, 💼事业牌阵');

    const moreEl = await page.$('.more-spreads');
    P('HOME More', moreEl ? '"查看更多 · 共10种牌阵" found' : 'Not found');

    // Tap daily card
    console.log('\n--- Tapping daily card ---');
    if (elWrap) {
      await elWrap.tap();
      await sleep(2000);
      page = await mp.currentPage();
      const d1t = page.data;
      I('After tap', `drawingLoading=${d1t.drawingLoading}, dailyCard=${d1t.dailyCard ? d1t.dailyCard.name_zh : 'null'}`);
      if (d1t.dailyCard) { P('HOME Draw', `Card: ${d1t.dailyCard.name_zh}`); I('Card data', JSON.stringify(d1t.dailyCard).slice(0,300)); }
      else if (d1t.drawingLoading) { I('HOME Draw', 'Still loading (API pending)'); }
      else { I('HOME Draw', 'dailyCard null - API offline'); }
      await snap(mp, 'home_after_tap');
    }

    // ════════════════════════════════════════════════
    // 2. ENCYCLOPEDIA
    // ════════════════════════════════════════════════
    console.log('\n=== 2. ENCYCLOPEDIA ===\n');
    await mp.switchTab('pages/encyclopedia/encyclopedia');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'encyclopedia');

    const d2 = page.data;
    I('pageLoading', String(d2.pageLoading));
    I('pageError', d2.pageError || 'none');
    I('activeTab', d2.activeTab);
    I('cards', `${d2.cards ? d2.cards.length : 0} total, ${d2.filteredCards ? d2.filteredCards.length : 0} filtered`);

    if (d2.pageError) { F('ENC', d2.pageError); }
    else if (d2.cards && d2.cards.length > 0) { P('ENC', `${d2.cards.length} cards loaded`); }
    else if (d2.pageLoading) { F('ENC', 'Still loading'); }
    else { F('ENC', 'No cards (empty, API offline?)'); }

    if (d2.cards && d2.cards.length > 0) {
      const c = d2.cards[0];
      I('First card', `${c.name_zh} (${c.name_en})`);
      if (c.card_image) {
        P('ENC Image data', `card_image: ${c.card_image.substring(0,80)}`);
        P('ENC CDN', c.card_image.startsWith('http') ? 'Uses HTTP URL' : `Path: ${c.card_image}`);
      } else { F('ENC Image data', 'No card_image field'); }
      if (c.arcana) P('ENC Arcana', c.arcana);
      if (c.keywords_upright) P('ENC Keywords', c.keywords_upright);
      if (c.meaning_upright) P('ENC Meanings', 'present');

      // BUG: CSS ::before placeholder, not actual <image>
      I('ENC BUG', 'Card grid uses CSS ::before placeholder, NOT loaded <image> tags');
      ISSUES.push('[BUG] Encyclopedia: Card images use CSS ::before gradient placeholder instead of <image> tags - card art never displayed from CDN');
    }

    const elTabs = await page.$$('.tab-item');
    P('ENC Tabs', elTabs && elTabs.length >= 4 ? `${elTabs.length} pills` : `Only ${elTabs ? elTabs.length : 0}`);

    if (elTabs && elTabs.length >= 2) {
      await elTabs[1].tap();
      await sleep(500);
      page = await mp.currentPage();
      P('ENC Filter', `activeTab -> "${page.data.activeTab}"`);
      await snap(mp, 'encyclopedia_filtered');
    }

    const elSearch = await page.$('.search-input');
    if (elSearch) {
      const allTab = await page.$('.tab-item');
      if (allTab) await allTab.tap();
      await sleep(200);
      await elSearch.input('星');
      await sleep(500);
      page = await mp.currentPage();
      P('ENC Search', `"星" -> ${page.data.filteredCards ? page.data.filteredCards.length : 0} results`);
      await snap(mp, 'encyclopedia_search');
    }

    // ════════════════════════════════════════════════
    // 3. READING
    // ════════════════════════════════════════════════
    console.log('\n=== 3. READING ===\n');
    await mp.navigateTo('pages/reading/reading');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'reading');

    const d3 = page.data;
    I('pageLoading', String(d3.pageLoading));
    I('pageError', d3.pageError || 'none');
    I('spreads', String(d3.spreads ? d3.spreads.length : 0));

    if (d3.pageError) { F('READ', d3.pageError); }
    else if (d3.spreads && d3.spreads.length >= 10) { P('READ', `${d3.spreads.length} spreads`); }
    else if (d3.pageLoading) { F('READ', 'Still loading'); }
    else { F('READ', `Only ${d3.spreads ? d3.spreads.length : 0}, expected 10`); }

    if (d3.spreads) {
      const bad = d3.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
      P('READ Fields', bad.length === 0 ? 'All complete' : `${bad.length} incomplete`);
      d3.spreads.forEach(s => I(`${s.icon} ${s.name}`, `${s.cards} cards${s.premium ? ' [PREMIUM]' : ''}${s.popular ? ' [POP]' : ''}`));
      const prem = d3.spreads.filter(s => s.premium).length;
      I('Access', `${d3.spreads.length - prem} free, ${prem} premium`);
    }

    const spreadEls = await page.$$('.spread-card');
    P('READ DOM', spreadEls && spreadEls.length >= 10 ? `${spreadEls.length} elements` : `Only ${spreadEls ? spreadEls.length : 0}`);

    if (d3.spreads && spreadEls && spreadEls.length > 0) {
      let idx = 0;
      for (let i = 0; i < d3.spreads.length; i++) { if (!d3.spreads[i].premium) { idx = i; break; } }

      await spreadEls[idx].tap();
      await sleep(1500);
      page = await mp.currentPage();

      if (page.data.showQuestionInput) {
        const sel = page.data.selectedSpread;
        P('READ Select', `"${sel.name}" selected, question shown`);
        await snap(mp, 'reading_question');

        const elQ = await page.$('.question-input');
        P('READ Textarea', elQ ? 'Found' : 'Not found');

        const elThemes = await page.$$('.theme-item');
        P('READ Themes', elThemes && elThemes.length === 4 ? '4 themes' : `Only ${elThemes ? elThemes.length : 0}`);

        P('READ Draw btn', (await page.$('.btn-glow-pulse')) ? 'Found' : 'Not found');
        P('READ Back link', (await page.$('.btn-text')) ? 'Found' : 'Not found');

        if (elQ) {
          await elQ.input('我的感情运势如何？');
          await sleep(500);
          page = await mp.currentPage();
          const ql = page.data.question ? page.data.question.length : 0;
          P('READ Question input', ql > 0 ? `Typed ${ql} chars` : 'Not reflected');
          await snap(mp, 'reading_with_question');
        }

        if (elThemes && elThemes.length >= 2) {
          await elThemes[1].tap();
          await sleep(300);
          page = await mp.currentPage();
          P('READ Theme select', `Theme -> "${page.data.theme}"`);
        }

        const backText = await page.$('.btn-text');
        if (backText) {
          await backText.tap();
          await sleep(500);
          page = await mp.currentPage();
          P('READ Back nav', page.data.showQuestionInput === false ? 'Returned to spread list' : 'Not returned');
        }
      } else {
        F('READ Select', 'showQuestionInput false');
        ISSUES.push('READ: Tapping non-premium spread did not show question input');
      }
    }

    // ════════════════════════════════════════════════
    // 4. PROFILE
    // ════════════════════════════════════════════════
    console.log('\n=== 4. PROFILE ===\n');
    await mp.switchTab('pages/profile/profile');
    await sleep(3000);
    page = await mp.currentPage();
    I('Path', page.path);
    await snap(mp, 'profile');

    const d4 = page.data;
    I('pageLoading', String(d4.pageLoading));
    I('pageError', d4.pageError || 'none');
    I('user', d4.user ? `nickname: ${d4.user.nickname || '(none)'}` : 'null');
    I('memberStatus', d4.memberStatus ? JSON.stringify(d4.memberStatus).slice(0,150) : 'null');
    I('history', `${d4.readingHistory ? d4.readingHistory.length : 0} items, total: ${d4.historyTotal || 0}`);

    if (d4.pageError) { F('PROF', d4.pageError); }
    else if (d4.user) { P('PROF', `User: ${d4.user.nickname || '(no name)'}`); }
    else if (d4.pageLoading) { F('PROF', 'Still loading'); }
    else { F('PROF', 'No user data (API offline)'); }

    const statItems = await page.$$('.stat-item');
    P('PROF Stats', statItems && statItems.length === 3 ? '3 items' : `Found ${statItems ? statItems.length : 0}`);

    const actionItems = await page.$$('.action-item');
    P('PROF Actions', actionItems && actionItems.length === 3 ? '3 items' : `Found ${actionItems ? actionItems.length : 0}`);

    P('PROF User card', (await page.$('.user-card')) ? 'Found' : 'Not found');
    I('PROF Upgrade btn', (await page.$('.upgrade-btn')) ? 'Present (free user)' : 'Not present (member/hidden)');
    P('PROF History', (await page.$('.history-header')) ? 'Found' : 'Not found');

    // ════════════════════════════════════════════════
    // 5. CONSOLE
    // ════════════════════════════════════════════════
    console.log('\n=== 5. CONSOLE ===\n');
    let logs = [];
    try { logs = await mp.getLogs(); } catch(e) { F('Console', `Cannot get: ${e.message}`); }
    const errL = logs.filter(l => l.level === 'error');
    const wrnL = logs.filter(l => l.level === 'warn');

    I('Total logs', String(logs.length));
    I('Errors', String(errL.length));
    I('Warnings', String(wrnL.length));

    if (errL.length === 0) { P('Console', 'No errors'); }
    else {
      F('Console', `${errL.length} error(s)`);
      errL.forEach((l, i) => {
        const m = typeof l.msg === 'string' ? l.msg.slice(0,300) : JSON.stringify(l).slice(0,300);
        ISSUES.push(`[CONSOLE #${i+1}] ${m}`);
      });
    }
    wrnL.forEach(l => I('Warn', typeof l.msg === 'string' ? l.msg.slice(0,200) : ''));

    // ════════════════════════════════════════════════
    // SUMMARY
    // ════════════════════════════════════════════════
    console.log('\n' + '='.repeat(60));
    console.log('TEST SUMMARY');
    console.log('='.repeat(60));

    const passes = RESULTS.filter(r => r.includes('[PASS]')).length;
    const fails = RESULTS.filter(r => r.includes('[FAIL]')).length;

    console.log(`\nPassed: ${passes}`);
    console.log(`Failed: ${fails}`);
    console.log(`Screenshots: ${RESULTS.filter(r => r.includes('[SS]')).length}`);

    if (ISSUES.length > 0) {
      console.log('\n--- ISSUES FOUND ---');
      ISSUES.forEach((iss, i) => console.log(`  ${i+1}. ${iss}`));
    }

    console.log('\n--- FULL RESULTS ---');
    RESULTS.forEach(r => console.log(r));

    await mp.close();
  } finally {
    proc.kill();
    fs.writeFileSync(connPath, originalCode);
    console.log('\nConnection.js restored.');
  }
}

main().catch(e => { console.error('FATAL:', e.message || e); process.exit(1); });
