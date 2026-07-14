const { spawn } = require('child_process');
const a = require('miniprogram-automator');

(async () => {
  // Launch IDE
  const cli = spawn('cmd.exe', ['/c', 'E:\\微信web开发者工具\\cli.bat', 'auto', '--project', 'E:\\tarot-miniapp\\miniapp', '--auto-port', '9420'], {stdio: 'pipe'});
  await new Promise(r => { const t = setTimeout(() => r(), 25000); cli.stdout.on('data', d => { if (d.toString().includes('auto')) { clearTimeout(t); setTimeout(r, 2000); } }); });

  const mp = await a.connect({ wsEndpoint: 'ws://127.0.0.1:9420' });
  console.log('=== Full Function Test ===\n');
  let pass = 0, fail = 0;

  async function check(label, fn) {
    try {
      await fn();
      console.log('  [PASS] ' + label);
      pass++;
    } catch(e) {
      console.log('  [FAIL] ' + label + ' — ' + (e.message||'').substring(0, 100));
      fail++;
    }
  }

  // ── 1. HOME PAGE ──
  console.log('── Home ──');
  await mp.switchTab('/pages/index/index');
  await new Promise(r => setTimeout(r, 2000));
  let page = await mp.currentPage();
  await check('Home page loads', async () => {
    if (page.path !== 'pages/index/index') throw new Error('Wrong page: ' + page.path);
  });

  await check('Daily card area exists', async () => {
    const el = await page.$('.daily-card-wrap');
    if (!el) throw new Error('No daily card wrapper');
  });

  await check('Spread cards exist (>=4)', async () => {
    const cards = await page.$$('.card-press');
    if (!cards || cards.length < 4) throw new Error('Only ' + (cards?.length||0) + ' spread cards');
  });

  await check('More spreads link exists', async () => {
    const el = await page.$('.more-spreads');
    if (!el) throw new Error('No more-spreads link');
  });

  // ── 2. DIRECT SPREAD → QUESTION ──
  console.log('── Direct Spread → Question ──');
  const cards = await page.$$('.card-press');
  if (cards && cards.length > 0) {
    await cards[0].tap();
    await new Promise(r => setTimeout(r, 3000));
    page = await mp.currentPage();
    await check('Navigates to reading page', async () => {
      if (!page.path.includes('reading')) throw new Error('Went to ' + page.path);
    });

    let textarea = null;
    await check('Question input visible directly', async () => {
      textarea = await page.$('textarea');
      if (!textarea) throw new Error('Still on spread selection');
    });

    if (textarea) {
      await textarea.input('Test question');
      await new Promise(r => setTimeout(r, 500));

      let btn = await page.$('button');
      if (btn) {
        console.log('  [INFO] Starting AI reading (may take 15-20s)...');
        await btn.tap();
        await new Promise(r => setTimeout(r, 25000));
        page = await mp.currentPage();
        await check('AI result page loads', async () => {
          if (!page.path.includes('reading-result')) throw new Error('Went to ' + page.path);
        });
      }
    }
    await mp.navigateBack();
    await new Promise(r => setTimeout(r, 1000));
  }

  // ── 3. ENCYCLOPEDIA ──
  console.log('── Encyclopedia ──');
  await mp.switchTab('/pages/encyclopedia/encyclopedia');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Encyclopedia loads', async () => {
    if (!page.path.includes('encyclopedia')) throw new Error('Wrong page');
  });

  // ── 4. PROFILE ──
  console.log('── Profile ──');
  await mp.switchTab('/pages/profile/profile');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Profile loads', async () => {
    if (!page.path.includes('profile')) throw new Error('Wrong page');
  });

  // ── 5. MEMBERSHIP ──
  console.log('── Membership ──');
  await mp.navigateTo('/pages/membership/membership');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Membership loads', async () => {
    if (!page.path.includes('membership')) throw new Error('Wrong page');
  });
  await mp.navigateBack();
  await new Promise(r => setTimeout(r, 500));

  // ── 6. CARD DETAIL ──
  console.log('── Card Detail ──');
  await mp.navigateTo('/pages/card-detail/card-detail?id=1');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Card detail loads', async () => {
    if (!page.path.includes('card-detail')) throw new Error('Wrong page');
  });
  await mp.navigateBack();
  await new Promise(r => setTimeout(r, 500));

  // ── 7. DIARY ──
  console.log('── Diary ──');
  await mp.navigateTo('/pages/diary/diary');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Diary loads', async () => {
    if (!page.path.includes('diary')) throw new Error('Wrong page');
  });

  // ── 8. ANNUAL REPORT ──
  console.log('── Annual Report ──');
  await mp.navigateTo('/pages/annual-report/annual-report');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Annual report loads', async () => {
    if (!page.path.includes('annual')) throw new Error('Wrong page');
  });

  // ── 9. CHAT (if available) ──
  console.log('── Chat ──');
  await mp.navigateTo('/pages/chat/chat?id=test');
  await new Promise(r => setTimeout(r, 2000));
  page = await mp.currentPage();
  await check('Chat page accessible', async () => {
    if (!page.path.includes('chat')) throw new Error('Wrong page: ' + page.path);
  });

  console.log('\n========================================');
  console.log('  PASS: ' + pass + '  FAIL: ' + fail);
  console.log('  Total: ' + (pass + fail) + ' tests');
  console.log('========================================');

  await mp.close();
})().catch(e => console.log('FATAL: ' + (e.message||'').substring(0, 300)));
