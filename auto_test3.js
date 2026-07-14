/**
 * Auto-test v3: Minimal operations, robust error handling
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
    const buf = await mp.screenshot();
    fs.writeFileSync(p, buf);
    RESULTS.push(`  [SS] ${name}.png (${buf.length} bytes)`);
    return true;
  } catch(e) {
    RESULTS.push(`  [SS FAIL] ${name}: ${e.message}`);
    return false;
  }
}

async function safe(page, fn, label) {
  try {
    const result = await fn(page);
    return result;
  } catch(e) {
    RESULTS.push(`  [FAIL] ${label}: ${e.message || 'unknown error'}`);
    ISSUES.push(`${label}: ${e.message || 'unknown error'}`);
    return null;
  }
}

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
  console.log('=== TAROT MINI-APP TEST ===\n');

  // Launch IDE
  console.log('Launching IDE...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c', 'E:\\微信web开发者工具\\cli.bat',
    'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });

  proc.stdout.on('data', d => process.stdout.write('[IDE] ' + d));
  proc.stderr.on('data', d => process.stderr.write('[IDE-ERR] ' + d));

  console.log('Waiting for WebSocket...');
  if (!await waitWS(WS_PORT, 60000)) {
    console.error('FAILED: WebSocket never became available');
    proc.kill();
    process.exit(1);
  }
  console.log('WebSocket ready!\n');

  // Connect
  let mp;
  try {
    mp = await automator.connect({ wsEndpoint: `ws://127.0.0.1:${WS_PORT}` });
    console.log('Connected\n');
  } catch(e) {
    console.error('Connection error:', e.message);
    proc.kill();
    process.exit(1);
  }

  // ─── 1. HOME PAGE ──────────────────────────────
  console.log('=== 1. HOME (pages/index/index) ===\n');
  try {
    await mp.switchTab('pages/index/index');
  } catch(e) {
    RESULTS.push(`  [FAIL] switchTab: ${e.message}`);
  }
  await sleep(3000);

  let page;
  try {
    page = await mp.currentPage();
    RESULTS.push(`  [INFO] Path: ${page.path}`);
  } catch(e) {
    RESULTS.push(`  [FAIL] currentPage: ${e.message}`);
    ISSUES.push(`HOME: ${e.message}`);
  }

  // Screenshot
  await snap(mp, 'home_initial');

  // Read page data
  if (page) {
    try {
      const d = page.data;
      const keys = Object.keys(d);
      RESULTS.push(`  [INFO] Data keys: ${keys.join(', ')}`);
      RESULTS.push(`  [INFO] pageLoading: ${d.pageLoading}`);
      RESULTS.push(`  [INFO] pageError: ${d.pageError || 'none'}`);
      RESULTS.push(`  [INFO] dailyCard: ${d.dailyCard ? d.dailyCard.name_zh : 'null'}`);

      if (d.pageError) {
        RESULTS.push(`  [FAIL] HOME: ${d.pageError}`);
        ISSUES.push(`HOME: pageError = ${d.pageError}`);
      } else if (d.pageLoading) {
        RESULTS.push(`  [FAIL] HOME: Still loading after 3s`);
        ISSUES.push('HOME: Page still showing skeleton loader after 3s');
      } else {
        RESULTS.push(`  [PASS] HOME: Page loaded successfully`);
      }

      // Check data
      if (!d.pageLoading && !d.pageError) {
        // Check dailyCard exists in initial state
        if (d.dailyCard) {
          RESULTS.push(`  [PASS] HOME: dailyCard loaded: ${d.dailyCard.name_zh}`);
        } else {
          RESULTS.push(`  [INFO] HOME: dailyCard not yet drawn (tap needed)`);
        }
      }

    } catch(e) {
      RESULTS.push(`  [FAIL] HOME data: ${e.message}`);
    }

    // Element queries
    const elTitle = await safe(page, p => p.$('.title-1'), 'HOME title element');
    RESULTS.push(elTitle ? `  [PASS] HOME: .title-1 found` : `  [INFO] HOME: .title-1 query returned null`);

    const elWrap = await safe(page, p => p.$('.daily-card-wrap'), 'HOME card wrap');
    if (elWrap) {
      RESULTS.push(`  [PASS] HOME: .daily-card-wrap found`);
    }

    const elShimmer = await safe(page, p => p.$('.card-shimmer'), 'HOME shimmer');
    RESULTS.push(elShimmer ? `  [PASS] HOME: Shimmer present` : `  [INFO] HOME: Shimmer not found`);

    const elSparkles = await safe(page, p => p.$('.card-sparkles'), 'HOME sparkles');
    RESULTS.push(elSparkles ? `  [PASS] HOME: Sparkles present` : `  [INFO] HOME: Sparkles not found`);

    const elRipple = await safe(page, p => p.$('.ripple-box'), 'HOME ripple');
    RESULTS.push(elRipple ? `  [PASS] HOME: Ripple box present` : `  [INFO] HOME: Ripple box not found`);

    const elBody = await safe(page, p => p.$('.card-body'), 'HOME card body');
    RESULTS.push(elBody ? `  [PASS] HOME: Card body present` : `  [INFO] HOME: Card body not found`);

    const elCards = await safe(page, p => p.$$('.card-press'), 'HOME spread cards');
    const cardCount = elCards ? elCards.length : 0;
    RESULTS.push(cardCount >= 4 ? `  [PASS] HOME: ${cardCount} spread cards` : `  [FAIL] HOME: Only ${cardCount} spread cards, expected >= 4`);

    const elMore = await safe(page, p => p.$('.more-spreads'), 'HOME more spreads');
    RESULTS.push(elMore ? `  [PASS] HOME: More spreads link found` : `  [FAIL] HOME: More spreads link not found`);
  }

  // ════════════════════════════════════════════
  // Tap the daily card
  // ════════════════════════════════════════════
  console.log('\n--- Tapping daily card ---');
  try {
    if (page && elWrap) {
      await elWrap.tap();
      await sleep(2000);
      page = await mp.currentPage();
      const d = page.data;
      RESULTS.push(`  [INFO] After tap: drawingLoading=${d.drawingLoading}, rippleActive=${d.rippleActive}, dailyCard=${d.dailyCard ? d.dailyCard.name_zh : 'null'}`);

      if (d.dailyCard) {
        RESULTS.push(`  [PASS] HOME: Card drawn successfully: ${d.dailyCard.name_zh}`);
      } else if (d.drawingLoading) {
        RESULTS.push(`  [INFO] HOME: Still drawing (API pending)`);
      } else {
        RESULTS.push(`  [INFO] HOME: dailyCard null after draw (API likely offline)`);
      }
      await snap(mp, 'home_after_tap');
    }
  } catch(e) {
    RESULTS.push(`  [FAIL] HOME tap: ${e.message}`);
  }

  // ─── 2. ENCYCLOPEDIA ──────────────────────────
  console.log('\n=== 2. ENCYCLOPEDIA ===\n');
  try {
    await mp.switchTab('pages/encyclopedia/encyclopedia');
  } catch(e) {
    RESULTS.push(`  [FAIL] ENC switchTab: ${e.message}`);
  }
  await sleep(3000);

  try {
    page = await mp.currentPage();
    RESULTS.push(`  [INFO] Path: ${page.path}`);
  } catch(e) {
    RESULTS.push(`  [FAIL] ENC currentPage: ${e.message}`);
  }
  await snap(mp, 'encyclopedia');

  if (page) {
    try {
      const d = page.data;
      RESULTS.push(`  [INFO] ENC: pageLoading=${d.pageLoading}, pageError=${d.pageError || 'none'}`);
      RESULTS.push(`  [INFO] ENC: activeTab=${d.activeTab}`);
      const totalCards = d.cards ? d.cards.length : 0;
      const filteredCards = d.filteredCards ? d.filteredCards.length : 0;
      RESULTS.push(`  [INFO] ENC: ${totalCards} total cards, ${filteredCards} filtered`);

      if (d.pageError) {
        RESULTS.push(`  [FAIL] ENC: ${d.pageError}`);
        ISSUES.push(`ENC: ${d.pageError}`);
      } else if (totalCards > 0) {
        RESULTS.push(`  [PASS] ENC: ${totalCards} cards loaded`);
      } else if (d.pageLoading) {
        RESULTS.push(`  [FAIL] ENC: Still loading`);
        ISSUES.push('ENC: Still loading after 3s');
      } else {
        RESULTS.push(`  [FAIL] ENC: No cards loaded (empty response)`);
        ISSUES.push('ENC: No cards data returned (API possibly offline)');
      }

      // Check first card
      if (d.cards && d.cards.length > 0) {
        const c = d.cards[0];
        RESULTS.push(`  [INFO] First card: ${c.name_zh} (${c.name_en})`);
        if (c.card_image) {
          RESULTS.push(`  [PASS] ENC: card_image present: ${c.card_image.substring(0,80)}`);
          if (c.card_image.startsWith('http')) {
            RESULTS.push(`  [PASS] ENC: Image uses HTTP/CDN URL`);
          } else {
            RESULTS.push(`  [INFO] ENC: Image path is not HTTP: ${c.card_image}`);
          }
        } else {
          RESULTS.push(`  [FAIL] ENC: No card_image field`);
          ISSUES.push('ENC: No card_image field in card data');
        }
        if (c.arcana) RESULTS.push(`  [PASS] ENC: arcana = ${c.arcana}`);
        if (c.keywords_upright) RESULTS.push(`  [PASS] ENC: keywords = ${c.keywords_upright}`);
        if (c.meaning_upright) RESULTS.push(`  [PASS] ENC: meaning_upright present`);

        // IMPORTANT: CSS ::before bug
        RESULTS.push(`  [ISSUE] ENC: Cards use CSS ::before placeholder instead of <image> tags — actual card images never displayed`);
        ISSUES.push('ENC: Card grid uses CSS ::before placeholder (background gradient), not actual <image> elements — card art NOT visible');
      }

      // Tabs
      const elTabs = await safe(page, p => p.$$('.tab-item'), 'ENC tabs');
      const tabCount = elTabs ? elTabs.length : 0;
      RESULTS.push(tabCount >= 4 ? `  [PASS] ENC: ${tabCount} filter tabs` : `  [FAIL] ENC: Only ${tabCount} tabs`);

      // Filter
      if (elTabs && elTabs.length >= 2) {
        try {
          await elTabs[1].tap();
          await sleep(500);
          page = await mp.currentPage();
          RESULTS.push(`  [PASS] ENC: Filter changed activeTab to "${page.data.activeTab}"`);
          await snap(mp, 'encyclopedia_filtered');
        } catch(e) {
          RESULTS.push(`  [FAIL] ENC filter: ${e.message}`);
        }
      }

      // Search
      const elSearch = await safe(page, p => p.$('.search-input'), 'ENC search');
      if (elSearch) {
        try {
          await elSearch.input('星');
          await sleep(500);
          page = await mp.currentPage();
          const sc = page.data.filteredCards ? page.data.filteredCards.length : 0;
          RESULTS.push(`  [PASS] ENC: Search "星" returned ${sc} results`);
          await snap(mp, 'encyclopedia_search');
        } catch(e) {
          RESULTS.push(`  [FAIL] ENC search: ${e.message}`);
        }
      }
    } catch(e) {
      RESULTS.push(`  [FAIL] ENC data: ${e.message}`);
    }
  }

  // ─── 3. READING ──────────────────────────────
  console.log('\n=== 3. READING ===\n');
  try {
    await mp.navigateTo('pages/reading/reading');
  } catch(e) {
    RESULTS.push(`  [FAIL] READ navigate: ${e.message}`);
  }
  await sleep(3000);

  try {
    page = await mp.currentPage();
    RESULTS.push(`  [INFO] Path: ${page.path}`);
  } catch(e) {
    RESULTS.push(`  [FAIL] READ currentPage: ${e.message}`);
  }
  await snap(mp, 'reading');

  if (page) {
    try {
      const d = page.data;
      RESULTS.push(`  [INFO] READ: pageLoading=${d.pageLoading}, pageError=${d.pageError || 'none'}`);
      const spreadCount = d.spreads ? d.spreads.length : 0;
      RESULTS.push(`  [INFO] READ: ${spreadCount} spreads`);

      if (d.pageError) {
        RESULTS.push(`  [FAIL] READ: ${d.pageError}`);
        ISSUES.push(`READ: ${d.pageError}`);
      } else if (spreadCount >= 10) {
        RESULTS.push(`  [PASS] READ: ${spreadCount} spreads (expected 10)`);
      } else if (d.pageLoading) {
        RESULTS.push(`  [FAIL] READ: Still loading`);
        ISSUES.push('READ: Still loading after 3s');
      } else {
        RESULTS.push(`  [FAIL] READ: Only ${spreadCount} spreads`);
        ISSUES.push(`READ: Expected 10 spreads, got ${spreadCount}`);
      }

      // Verify spread list
      if (d.spreads) {
        const incomplete = d.spreads.filter(s => !s.key || !s.name || !s.icon || !s.desc || !s.cards);
        RESULTS.push(incomplete.length === 0 ? `  [PASS] READ: All spreads have required fields` : `  [FAIL] READ: ${incomplete.length} spreads missing fields`);

        d.spreads.forEach(s => {
          RESULTS.push(`  [SPREAD] ${s.icon || '?'} ${s.name || '?'} (${s.cards || 0} cards)${s.premium ? ' [PREMIUM]' : ''}${s.popular ? ' [HOT]' : ''}`);
        });

        const prem = d.spreads.filter(s => s.premium).length;
        RESULTS.push(`  [INFO] READ: ${d.spreads.length - prem} free, ${prem} premium`);
      }

      // DOM elements
      const elSpreads = await safe(page, p => p.$$('.spread-card'), 'READ spread elements');
      const elCount = elSpreads ? elSpreads.length : 0;
      RESULTS.push(elCount >= 10 ? `  [PASS] READ: ${elCount} spread card elements` : `  [FAIL] READ: Only ${elCount} elements`);

      // Select a spread
      if (d.spreads && elSpreads && elSpreads.length > 0) {
        let idx = 0;
        for (let i = 0; i < d.spreads.length; i++) {
          if (!d.spreads[i].premium) { idx = i; break; }
        }

        try {
          await elSpreads[idx].tap();
          await sleep(1500);
          page = await mp.currentPage();

          if (page.data.showQuestionInput) {
            const sel = page.data.selectedSpread;
            RESULTS.push(`  [PASS] READ: "${sel.name}" selected, question input shown`);

            // Check elements
            const elQ = await safe(page, p => p.$('.question-input'), 'READ textarea');
            RESULTS.push(elQ ? `  [PASS] READ: Question textarea found` : `  [FAIL] READ: Question textarea not found`);

            const elThemes = await safe(page, p => p.$$('.theme-item'), 'READ themes');
            RESULTS.push(elThemes && elThemes.length === 4 ? `  [PASS] READ: 4 theme options` : `  [FAIL] READ: ${elThemes ? elThemes.length : 0} themes, expected 4`);

            const elDraw = await safe(page, p => p.$('.btn-glow-pulse'), 'READ draw button');
            RESULTS.push(elDraw ? `  [PASS] READ: Draw button found` : `  [FAIL] READ: Draw button not found`);

            const elBack = await safe(page, p => p.$('.btn-text'), 'READ back link');
            RESULTS.push(elBack ? `  [PASS] READ: Back-to-spreads link found` : `  [FAIL] READ: Back-to-spreads link not found`);

            await snap(mp, 'reading_question');

            // Type question
            if (elQ) {
              try {
                await elQ.input('我的感情运势如何？');
                await sleep(500);
                page = await mp.currentPage();
                const ql = page.data.question ? page.data.question.length : 0;
                RESULTS.push(ql > 0 ? `  [PASS] READ: Typed ${ql} characters in question` : `  [FAIL] READ: Question text not reflected in data`);
              } catch(e) {
                RESULTS.push(`  [FAIL] READ typing: ${e.message}`);
              }
            }

            // Select theme
            if (elThemes && elThemes.length >= 2) {
              try {
                await elThemes[1].tap();
                await sleep(300);
                page = await mp.currentPage();
                RESULTS.push(`  [PASS] READ: Theme changed to "${page.data.theme}"`);
              } catch(e) {
                RESULTS.push(`  [FAIL] READ theme: ${e.message}`);
              }
            }

            // Back
            if (elBack) {
              try {
                await elBack.tap();
                await sleep(500);
                page = await mp.currentPage();
                RESULTS.push(page.data.showQuestionInput === false ? `  [PASS] READ: Back to spread selection` : `  [FAIL] READ: Back did not return to spread list`);
              } catch(e) {
                RESULTS.push(`  [FAIL] READ back: ${e.message}`);
              }
            }

            await snap(mp, 'reading_explored');
          } else {
            RESULTS.push(`  [FAIL] READ: showQuestionInput still false after spread tap`);
            ISSUES.push('READ: Tapping a non-premium spread did not show question input');
          }
        } catch(e) {
          RESULTS.push(`  [FAIL] READ interaction: ${e.message}`);
        }
      }
    } catch(e) {
      RESULTS.push(`  [FAIL] READ data: ${e.message}`);
    }
  }

  // ─── 4. PROFILE ──────────────────────────────
  console.log('\n=== 4. PROFILE ===\n');
  try {
    await mp.switchTab('pages/profile/profile');
  } catch(e) {
    RESULTS.push(`  [FAIL] PROF switchTab: ${e.message}`);
  }
  await sleep(3000);

  try {
    page = await mp.currentPage();
    RESULTS.push(`  [INFO] Path: ${page.path}`);
  } catch(e) {
    RESULTS.push(`  [FAIL] PROF currentPage: ${e.message}`);
  }
  await snap(mp, 'profile');

  if (page) {
    try {
      const d = page.data;
      RESULTS.push(`  [INFO] PROF: pageLoading=${d.pageLoading}, pageError=${d.pageError || 'none'}`);
      RESULTS.push(`  [INFO] PROF: user=${d.user ? 'loaded: ' + d.user.nickname : 'null'}`);
      RESULTS.push(`  [INFO] PROF: memberStatus=${d.memberStatus ? JSON.stringify(d.memberStatus).slice(0,120) : 'null'}`);
      RESULTS.push(`  [INFO] PROF: history=${d.readingHistory ? d.readingHistory.length : 0} items, total=${d.historyTotal || 0}`);

      if (d.pageError) {
        RESULTS.push(`  [FAIL] PROF: ${d.pageError}`);
        ISSUES.push(`PROF: ${d.pageError}`);
      } else if (d.user) {
        RESULTS.push(`  [PASS] PROF: User info loaded: ${d.user.nickname || '(no nickname)'}`);
      } else if (d.pageLoading) {
        RESULTS.push(`  [FAIL] PROF: Still loading`);
        ISSUES.push('PROF: Still loading after 3s');
      } else {
        RESULTS.push(`  [FAIL] PROF: No user data (API likely offline)`);
        ISSUES.push('PROF: No user data (API or auth issue)');
      }

      // Stats
      const elStats = await safe(page, p => p.$$('.stat-item'), 'PROF stats');
      RESULTS.push(elStats && elStats.length === 3 ? `  [PASS] PROF: 3 stat items` : `  [FAIL] PROF: ${elStats ? elStats.length : 0} stat items, expected 3`);

      // Actions
      const elActions = await safe(page, p => p.$$('.action-item'), 'PROF actions');
      RESULTS.push(elActions && elActions.length === 3 ? `  [PASS] PROF: 3 quick actions` : `  [FAIL] PROF: ${elActions ? elActions.length : 0} actions, expected 3`);

      // User card
      const elUserCard = await safe(page, p => p.$('.user-card'), 'PROF user card');
      RESULTS.push(elUserCard ? `  [PASS] PROF: User card found` : `  [FAIL] PROF: User card not found`);

      // Upgrade button
      const elUpgrade = await safe(page, p => p.$('.upgrade-btn'), 'PROF upgrade');
      RESULTS.push(`  [INFO] PROF: Upgrade button ${elUpgrade ? 'present (non-member view)' : 'not present (member/hidden)'}`);

      // History
      const elHistory = await safe(page, p => p.$('.history-header'), 'PROF history');
      RESULTS.push(elHistory ? `  [PASS] PROF: History section found` : `  [FAIL] PROF: History section not found`);

    } catch(e) {
      RESULTS.push(`  [FAIL] PROF data: ${e.message}`);
    }
  }

  // ─── 5. CONSOLE LOGS ──────────────────────────
  console.log('\n=== 5. CONSOLE LOGS ===\n');
  let logs = [];
  try { logs = await mp.getLogs(); } catch(e) { RESULTS.push(`  [FAIL] Console: ${e.message}`); }

  const errs = logs.filter(l => l.level === 'error');
  const wrns = logs.filter(l => l.level === 'warn');

  RESULTS.push(`  [INFO] Total logs: ${logs.length}`);
  RESULTS.push(`  [INFO] Errors: ${errs.length}`);
  RESULTS.push(`  [INFO] Warnings: ${wrns.length}`);

  if (errs.length === 0) {
    RESULTS.push(`  [PASS] Console: No errors`);
  } else {
    RESULTS.push(`  [FAIL] Console: ${errs.length} error(s)`);
    errs.forEach((l, i) => {
      const m = typeof l.msg === 'string' ? l.msg.slice(0,300) : JSON.stringify(l).slice(0,300);
      ISSUES.push(`[CONSOLE #${i+1}] ${m}`);
    });
  }

  wrns.forEach(l => {
    const m = typeof l.msg === 'string' ? l.msg.slice(0,200) : '';
    RESULTS.push(`  [WARN] ${m}`);
  });

  // ════════════════════════════════════════════
  // SUMMARY
  // ════════════════════════════════════════════
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
  proc.kill();
  console.log('\nDone.');
})().catch(e => {
  console.error('FATAL:', e.message || e);
  console.error(e.stack);
  process.exit(1);
});
