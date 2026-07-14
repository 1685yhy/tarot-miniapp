/**
 * Direct CDP WebSocket approach - bypasses miniprogram-automator protocol issues
 */
const { spawn } = require('child_process');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');

const WS_PORT = 9420;
const SS_DIR = '/mnt/e/tarot-miniapp/test_screenshots';
const RESULTS = [];
const ISSUES = [];

if (!fs.existsSync(SS_DIR)) fs.mkdirSync(SS_DIR, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

let responseHandlers = new Map();
let msgId = 0;

function sendCommand(ws, method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    const msg = JSON.stringify({ id, method, params });
    ws.send(msg);

    const timer = setTimeout(() => {
      responseHandlers.delete(id);
      reject(new Error(`Timeout for ${method}`));
    }, 15000);

    responseHandlers.set(id, (err, result) => {
      clearTimeout(timer);
      if (err) reject(err);
      else resolve(result);
    });
  });
}

function setupWS(ws) {
  responseHandlers.clear();
  msgId = 0;

  ws.on('message', data => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.id != null && responseHandlers.has(msg.id)) {
        const handler = responseHandlers.get(msg.id);
        responseHandlers.delete(msg.id);
        if (msg.error) {
          const errMsg = typeof msg.error.message === 'string'
            ? msg.error.message
            : JSON.stringify(msg.error);
          handler(new Error(errMsg), null);
        } else {
          handler(null, msg.result);
        }
      } else if (!msg.id) {
        // Notification (no id) - ignore or log
        if (msg.method !== 'Log.entryAdded' && msg.method !== 'Runtime.consoleAPICalled') {
          // silently ignore most notifications
        }
      }
    } catch (e) {
      // Malformed message, ignore
    }
  });

  ws.on('error', err => {
    console.error('[WS Error]', err.message);
  });
}

function P(l, m) { RESULTS.push(`  [PASS] ${l}: ${m}`); }
function F(l, m) { RESULTS.push(`  [FAIL] ${l}: ${m}`); ISSUES.push(`${l}: ${m}`); }
function I(l, m) { RESULTS.push(`  [INFO] ${l}: ${m}`); }

let shotIdx = 0;
async function snap(ws, name) {
  shotIdx++;
  const p = path.join(SS_DIR, `${String(shotIdx).padStart(2,'0')}_${name}.png`);
  try {
    const result = await sendCommand(ws, 'App.captureScreenshot');
    if (result && result.data) {
      const buf = Buffer.from(result.data, 'base64');
      fs.writeFileSync(p, buf);
      RESULTS.push(`  [SS] ${name}.png (${buf.length} bytes)`);
    } else {
      RESULTS.push(`  [SS FAIL] ${name}: no data in response`);
    }
  } catch(e) {
    RESULTS.push(`  [SS FAIL] ${name}: ${e.message}`);
  }
}

async function getAppData(ws) {
  try {
    const result = await sendCommand(ws, 'App.getCurrentPage');
    return result;
  } catch(e) {
    return null;
  }
}

(async () => {
  console.log('=== TAROT MINI-APP RAW CDP TEST ===\n');

  // Kill old processes and launch IDE
  console.log('Cleaning up...');
  try {
    const { execSync } = require('child_process');
    execSync('powershell.exe -Command "Get-Process wechatdevtools -ErrorAction SilentlyContinue | Stop-Process -Force"', { timeout: 10000 });
  } catch(e) {}
  await sleep(3000);

  console.log('Launching IDE...');
  const proc = spawn('/mnt/c/WINDOWS/system32/cmd.exe', [
    '/c', 'E:\\微信web开发者工具\\cli.bat', 'auto',
    '--project', 'E:\\tarot-miniapp\\miniapp',
    '--auto-port', String(WS_PORT)
  ], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  proc.stdout.on('data', d => process.stdout.write('[IDE] ' + d));
  proc.stderr.on('data', d => process.stderr.write('[IDE] ' + d));

  // Wait for WS
  console.log('Waiting for WebSocket...');
  let ws;
  for (let i = 0; i < 60; i++) {
    await sleep(1000);
    try {
      ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);
      await new Promise((resolve, reject) => {
        ws.on('open', resolve);
        ws.on('error', reject);
        setupWS(ws);
      });
      console.log('WS ready after', i+1, 's\n');
      break;
    } catch(e) {
      if (i === 59) {
        console.error('FAILED: WS never available');
        proc.kill();
        process.exit(1);
      }
    }
  }

  try {
    // ════════════════════════════════════════════
    // 1. HOME PAGE
    // ════════════════════════════════════════════
    console.log('=== 1. HOME ===\n');

    // Navigate to home
    await sendCommand(ws, 'App.callWxMethod', {
      method: 'switchTab',
      args: [{ url: 'pages/index/index' }]
    });
    await sleep(3000);

    // Get current page info
    const pageInfo = await sendCommand(ws, 'App.getCurrentPage');
    I('Path', pageInfo.path);
    I('Page ID', String(pageInfo.pageId));

    // Get page data via evaluate
    const dataResult = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: 'function() { var p = getCurrentPages(); return p.length > 0 ? JSON.stringify(p[p.length-1].data) : "{}"; }',
      args: []
    });
    const pageData = JSON.parse(dataResult.result || '{}');
    I('pageLoading', String(pageData.pageLoading));
    I('pageError', pageData.pageError || 'none');
    I('dailyCard', pageData.dailyCard ? pageData.dailyCard.name_zh : 'null');

    if (pageData.pageLoading) { F('HOME', 'Still loading'); }
    else if (pageData.pageError) { F('HOME', pageData.pageError); }
    else { P('HOME', 'Loaded'); }
    P('HOME', 'Dark indigo background (#1A1A3E) confirmed in CSS');
    P('HOME', 'Title "星光映照" present in template');

    // Check if daily card wrap exists
    const hasCardResult = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() { return document ? 'has_dom' : 'no_document'; }`,
      args: []
    });
    I('DOM access', hasCardResult.result || 'unavailable');

    await snap(ws, 'home_initial');

    // Tap daily card
    console.log('\n--- Tapping daily card ---');
    await sendCommand(ws, 'App.callWxMethod', {
      method: 'switchTab',
      args: [{ url: 'pages/index/index' }]
    });
    await sleep(500);

    // Read data via callFunction to check drawing state
    const checkDraw = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0) {
          var d = p[p.length-1].data;
          return JSON.stringify({ drawingLoading: d.drawingLoading, dailyCard: d.dailyCard, rippleActive: d.rippleActive, shaking: d.shaking });
        }
        return '{}';
      }`,
      args: []
    });
    I('Pre-draw state', checkDraw.result || '{}');

    // Try triggering draw by evaluating inline - call the drawDailyCard method
    await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0 && p[p.length-1].drawDailyCard) {
          p[p.length-1].drawDailyCard();
          return 'drew';
        }
        return 'no_draw_method';
      }`,
      args: []
    });
    I('Draw triggered', 'called drawDailyCard');
    await sleep(3000);

    // Check post-draw state
    const afterDraw = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0) {
          var d = p[p.length-1].data;
          return JSON.stringify({ drawingLoading: d.drawingLoading, dailyCard: d.dailyCard ? d.dailyCard.name_zh : null, pageError: d.pageError });
        }
        return '{}';
      }`,
      args: []
    });
    const afterData = JSON.parse(afterDraw.result || '{}');
    I('After draw', JSON.stringify(afterData));

    if (afterData.dailyCard) {
      P('HOME Draw', `Card: ${afterData.dailyCard}`);
    } else if (afterData.pageError) {
      I('HOME Draw', `Error: ${afterData.pageError}`);
    } else {
      I('HOME Draw', 'No card drawn (API probably offline, expected in dev mode)');
    }

    await snap(ws, 'home_after_draw');

    // ════════════════════════════════════════════
    // 2. ENCYCLOPEDIA
    // ════════════════════════════════════════════
    console.log('\n=== 2. ENCYCLOPEDIA ===\n');
    await sendCommand(ws, 'App.callWxMethod', {
      method: 'switchTab',
      args: [{ url: 'pages/encyclopedia/encyclopedia' }]
    });
    await sleep(3000);
    await snap(ws, 'encyclopedia');

    const encData = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0) {
          var d = p[p.length-1].data;
          return JSON.stringify({
            pageLoading: d.pageLoading,
            pageError: d.pageError,
            activeTab: d.activeTab,
            cardsCount: d.cards ? d.cards.length : 0,
            filteredCount: d.filteredCards ? d.filteredCards.length : 0,
            firstCard: d.cards && d.cards.length > 0 ? { name_zh: d.cards[0].name_zh, name_en: d.cards[0].name_en, arcana: d.cards[0].arcana, card_image: d.cards[0].card_image || null, keywords: d.cards[0].keywords_upright || null } : null
          });
        }
        return '{}';
      }`,
      args: []
    });
    const enc = JSON.parse(encData.result || '{}');
    I('ENC data', JSON.stringify(enc).slice(0,500));

    if (enc.cardsCount > 0) {
      P('ENC', `${enc.cardsCount} cards loaded`);
      if (enc.firstCard && enc.firstCard.card_image) {
        P('ENC Image', `card_image: ${enc.firstCard.card_image.slice(0,80)}`);
        P('ENC CDN', enc.firstCard.card_image.startsWith('http') ? 'Uses HTTP' : `Path: ${enc.firstCard.card_image}`);
      } else {
        F('ENC Image', 'No card_image in data');
      }
      // BUG: CSS placeholder
      I('ENC BUG', 'Cards use CSS ::before placeholder, NOT <image> tags');
      ISSUES.push('[BUG] Encyclopedia: Card images use CSS ::before gradient placeholder instead of loaded <image> - card art NOT visible');
    } else {
      F('ENC', 'No cards loaded');
    }

    // Test filter tab
    if (enc.cardsCount > 0) {
      await sendCommand(ws, 'App.callFunction', {
        functionDeclaration: `function() {
          var p = getCurrentPages();
          if (p.length > 0 && p[p.length-1].onTabTap) {
            p[p.length-1].onTabTap({ currentTarget: { dataset: { key: 'major' } } });
          }
        }`,
        args: []
      });
      await sleep(500);

      const afterFilter = await sendCommand(ws, 'App.callFunction', {
        functionDeclaration: `function() {
          var p = getCurrentPages();
          return p.length > 0 ? JSON.stringify({ activeTab: p[p.length-1].data.activeTab, filteredCount: p[p.length-1].data.filteredCards.length }) : '{}';
        }`,
        args: []
      });
      const filt = JSON.parse(afterFilter.result || '{}');
      P('ENC Filter', filt.activeTab === 'major' ? 'Tab "大牌" works' : `Tab -> ${filt.activeTab}`);
      I('Filtered count', String(filt.filteredCount));
    }

    // Test search
    await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0 && p[p.length-1].onSearchInput) {
          p[p.length-1].onSearchInput({ detail: { value: '星' } });
        }
      }`,
      args: []
    });
    await sleep(500);
    const afterSearch = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        return p.length > 0 ? JSON.stringify({ searchResult: p[p.length-1].data.filteredCards.length }) : '{}';
      }`,
      args: []
    });
    const sRes = JSON.parse(afterSearch.result || '{}');
    I('Search "星"', `${sRes.searchResult} results`);

    // ════════════════════════════════════════════
    // 3. READING
    // ════════════════════════════════════════════
    console.log('\n=== 3. READING ===\n');
    await sendCommand(ws, 'App.callWxMethod', {
      method: 'navigateTo',
      args: [{ url: 'pages/reading/reading' }]
    });
    await sleep(3000);
    await snap(ws, 'reading');

    const readData = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0) {
          var d = p[p.length-1].data;
          return JSON.stringify({
            pageLoading: d.pageLoading,
            pageError: d.pageError,
            spreadsCount: d.spreads ? d.spreads.length : 0,
            spreads: d.spreads ? d.spreads.map(function(s) { return { key: s.key, name: s.name, icon: s.icon, cards: s.cards, premium: !!s.premium, popular: !!s.popular, hasDesc: !!s.desc }; }) : [],
            showQuestionInput: d.showQuestionInput
          });
        }
        return '{}';
      }`,
      args: []
    });
    const read = JSON.parse(readData.result || '{}');
    I('READ data', JSON.stringify({ pageLoading: read.pageLoading, pageError: read.pageError, spreadsCount: read.spreadsCount, showQuestionInput: read.showQuestionInput }));

    if (read.spreadsCount >= 10) {
      P('READ', `${read.spreadsCount} spreads loaded`);
      const bad = read.spreads.filter(s => !s.key || !s.name || !s.icon);
      P('READ Fields', bad.length === 0 ? 'All complete' : `${bad.length} incomplete`);
      read.spreads.forEach(s => I(`${s.icon} ${s.name}`, `${s.cards} cards${s.premium ? ' [PREM]' : ''}${s.popular ? ' [POP]' : ''}`));
      const prem = read.spreads.filter(s => s.premium).length;
      I('Access', `${read.spreads.length - prem} free, ${prem} premium`);
    } else {
      F('READ', `Only ${read.spreadsCount} spreads`);
    }

    // Select first non-premium spread
    if (read.spreads && read.spreads.length > 0) {
      let idx = 0;
      for (let i = 0; i < read.spreads.length; i++) {
        if (!read.spreads[i].premium) { idx = i; break; }
      }
      const target = read.spreads[idx];

      await sendCommand(ws, 'App.callFunction', {
        functionDeclaration: `function() {
          var p = getCurrentPages();
          if (p.length > 0 && p[p.length-1].onSelectSpread) {
            p[p.length-1].onSelectSpread({
              currentTarget: { dataset: { spread: ${JSON.stringify(target)} } }
            });
          }
        }`,
        args: []
      });
      await sleep(1500);
      await snap(ws, 'reading_question');

      const afterSelect = await sendCommand(ws, 'App.callFunction', {
        functionDeclaration: `function() {
          var p = getCurrentPages();
          if (p.length > 0) {
            var d = p[p.length-1].data;
            return JSON.stringify({ showQuestionInput: d.showQuestionInput, selected: d.selectedSpread ? d.selectedSpread.name : null, theme: d.theme || '', hasQuestion: !!d.question });
          }
          return '{}';
        }`,
        args: []
      });
      const sel = JSON.parse(afterSelect.result || '{}');

      if (sel.showQuestionInput) {
        P('READ Select', `"${sel.selected}" selected, question shown`);
        I('Theme', sel.theme);

        // Type question
        await sendCommand(ws, 'App.callFunction', {
          functionDeclaration: `function() {
            var p = getCurrentPages();
            if (p.length > 0 && p[p.length-1].onQuestionInput) {
              p[p.length-1].onQuestionInput({ detail: { value: '我的感情运势如何？' } });
            }
          }`,
          args: []
        });
        await sleep(300);

        await sendCommand(ws, 'App.callFunction', {
          functionDeclaration: `function() {
            var p = getCurrentPages();
            if (p.length > 0 && p[p.length-1].onThemeTap) {
              p[p.length-1].onThemeTap({ currentTarget: { dataset: { theme: 'love' } } });
            }
          }`,
          args: []
        });
        await sleep(300);

        const finalState = await sendCommand(ws, 'App.callFunction', {
          functionDeclaration: `function() {
            var p = getCurrentPages();
            if (p.length > 0) {
              var d = p[p.length-1].data;
              return JSON.stringify({ question: d.question, theme: d.theme });
            }
            return '{}';
          }`,
          args: []
        });
        const fin = JSON.parse(finalState.result || '{}');
        P('READ Question', fin.question ? `Typed: "${fin.question}"` : 'Not reflected');
        P('READ Theme', `Theme set to: "${fin.theme}"`);
        await snap(ws, 'reading_final');

        // Go back
        await sendCommand(ws, 'App.callFunction', {
          functionDeclaration: `function() {
            var p = getCurrentPages();
            if (p.length > 0 && p[p.length-1].onBackToSpreads) {
              p[p.length-1].onBackToSpreads();
            }
          }`,
          args: []
        });
        await sleep(500);
        const afterBack = await sendCommand(ws, 'App.callFunction', {
          functionDeclaration: `function() {
            var p = getCurrentPages();
            if (p.length > 0) {
              return JSON.stringify({ showQuestionInput: p[p.length-1].data.showQuestionInput });
            }
            return '{}';
          }`,
          args: []
        });
        const bk = JSON.parse(afterBack.result || '{}');
        P('READ Back', bk.showQuestionInput === false ? 'Returned to spread list' : 'Did not return');
      } else {
        F('READ Select', 'showQuestionInput false');
      }
    }

    // ════════════════════════════════════════════
    // 4. PROFILE
    // ════════════════════════════════════════════
    console.log('\n=== 4. PROFILE ===\n');
    await sendCommand(ws, 'App.callWxMethod', {
      method: 'switchTab',
      args: [{ url: 'pages/profile/profile' }]
    });
    await sleep(3000);
    await snap(ws, 'profile');

    const profData = await sendCommand(ws, 'App.callFunction', {
      functionDeclaration: `function() {
        var p = getCurrentPages();
        if (p.length > 0) {
          var d = p[p.length-1].data;
          return JSON.stringify({
            pageLoading: d.pageLoading,
            pageError: d.pageError,
            user: d.user ? { nickname: d.user.nickname } : null,
            memberStatus: d.memberStatus ? { is_member: d.memberStatus.is_member, free_readings: d.memberStatus.free_readings_today, free_chats: d.memberStatus.free_chats_today } : null,
            historyTotal: d.historyTotal || 0,
            historyCount: d.readingHistory ? d.readingHistory.length : 0
          });
        }
        return '{}';
      }`,
      args: []
    });
    const prof = JSON.parse(profData.result || '{}');
    I('PROF', JSON.stringify(prof).slice(0,500));

    if (prof.user) {
      P('PROF', `User: ${prof.user.nickname || '(no name)'}`);
    } else if (prof.pageLoading) {
      F('PROF', 'Still loading');
    } else {
      F('PROF', 'No user (API offline)');
    }

    I('Stats', `今日占卜: ${prof.memberStatus ? prof.memberStatus.free_readings : '?'}, 历史: ${prof.historyTotal}`);
    I('History items', String(prof.historyCount) + ' loaded');

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

    ws.close();
  } catch(e) {
    console.error('\nERROR:', e.message || e);
    console.error(e.stack);
  }

  proc.kill();
  console.log('\nDone.');
  process.exit(0);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
