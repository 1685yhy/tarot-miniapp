const automator = require('miniprogram-automator');
const fs = require('fs');
const path = require('path');

const WS_ENDPOINT = 'ws://127.0.0.1:9420';

// Retry connection with timeout
async function connectWithRetry(maxRetries = 30, delayMs = 2000) {
  for (let i = 1; i <= maxRetries; i++) {
    try {
      const mp = await automator.connect({ wsEndpoint: WS_ENDPOINT });
      return mp;
    } catch (e) {
      if (i < maxRetries) {
        console.log(`  Connection attempt ${i}/${maxRetries} failed, retrying in ${delayMs}ms...`);
        await sleep(delayMs);
      } else {
        throw new Error(
          `Could not connect to ${WS_ENDPOINT} after ${maxRetries} attempts.\n` +
          `Make sure WeChat DevTools is running with this project open and automation enabled.\n` +
          `On Windows, launch the IDE first, then run: node test_app.js\n` +
          `If automation port differs from 9420, set env: AUTO_WS=ws://127.0.0.1:NEWPORT`
        );
      }
    }
  }
}

// Helper: wait for a given ms
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Helper: take screenshot and save to file
async function screenshot(mp, filePath) {
  try {
    const buf = await mp.screenshot();
    fs.writeFileSync(filePath, buf);
    console.log(`  [OK] Screenshot saved -> ${filePath}`);
  } catch (e) {
    console.log(`  [FAIL] Screenshot failed: ${e.message}`);
  }
}

// Helper: check page data field
async function checkPageData(page, field, expected, label) {
  try {
    const val = page.data[field];
    const pass = (typeof expected === 'function') ? expected(val) : (val === expected);
    if (pass) {
      console.log(`  [OK] ${label}: ${field} = ${JSON.stringify(val)}`);
    } else {
      console.log(`  [WARN] ${label}: ${field} = ${JSON.stringify(val)} (expected ${typeof expected === 'function' ? 'truthy' : JSON.stringify(expected)})`);
    }
  } catch (e) {
    console.log(`  [FAIL] ${label}: could not read ${field}: ${e.message}`);
  }
}

(async () => {
  let mp;
  try {
    console.log('=== Tarot Mini-App Verification Script ===\n');

    // 1. Connect to IDE automation
    const wsUrl = process.env.AUTO_WS || WS_ENDPOINT;
    console.log(`Connecting to ${wsUrl} ...`);
    mp = await connectWithRetry();
    console.log('[OK] Connected to WeChat IDE automation\n');

    // ──────────────────────────────────────────────
    // 1. Home page (pages/index/index)
    // ──────────────────────────────────────────────
    console.log('--- Step 1: Home Page (pages/index/index) ---');
    let page = await mp.currentPage();
    console.log(`  Current page: ${page.path}`);

    await screenshot(mp, '/tmp/verify_home.png');
    await checkPageData(page, 'pageLoading', val => val === false, 'Home');
    if (page.data.pageLoading === undefined) {
      console.log('  [INFO] Home: pageLoading field not found, checking alternatives...');
      // Check common loading indicators
      await checkPageData(page, 'loading', val => val === false, 'Home');
    }

    // ──────────────────────────────────────────────
    // 2. Navigate to encyclopedia
    // ──────────────────────────────────────────────
    console.log('\n--- Step 2: Encyclopedia (pages/encyclopedia/encyclopedia) ---');
    await mp.navigateTo('pages/encyclopedia/encyclopedia');
    await sleep(2000);
    page = await mp.currentPage();
    console.log(`  Current page: ${page.path}`);

    await screenshot(mp, '/tmp/verify_encyclopedia.png');

    // Check that cards are loaded
    if (page.data.filteredCards) {
      const count = Array.isArray(page.data.filteredCards)
        ? page.data.filteredCards.length
        : Object.keys(page.data.filteredCards).length;
      if (count > 0) {
        console.log(`  [OK] Encyclopedia: filteredCards has ${count} entries`);
      } else {
        console.log(`  [WARN] Encyclopedia: filteredCards is empty`);
      }
    } else if (page.data.cards) {
      const count = Array.isArray(page.data.cards)
        ? page.data.cards.length
        : Object.keys(page.data.cards).length;
      if (count > 0) {
        console.log(`  [OK] Encyclopedia: cards has ${count} entries`);
      } else {
        console.log(`  [WARN] Encyclopedia: cards is empty`);
      }
    } else {
      console.log('  [WARN] Encyclopedia: no filteredCards or cards field found in page data');
      // Show available keys for debugging
      const keys = Object.keys(page.data);
      console.log(`  [INFO] Available page data keys: ${keys.join(', ')}`);
    }

    // ──────────────────────────────────────────────
    // 3. Navigate to reading
    // ──────────────────────────────────────────────
    console.log('\n--- Step 3: Reading (pages/reading/reading) ---');
    await mp.navigateTo('pages/reading/reading');
    await sleep(2000);
    page = await mp.currentPage();
    console.log(`  Current page: ${page.path}`);

    await screenshot(mp, '/tmp/verify_reading.png');

    // ──────────────────────────────────────────────
    // 4. Navigate to membership
    // ──────────────────────────────────────────────
    console.log('\n--- Step 4: Membership (pages/membership/membership) ---');
    await mp.navigateTo('pages/membership/membership');
    await sleep(2000);
    page = await mp.currentPage();
    console.log(`  Current page: ${page.path}`);

    await screenshot(mp, '/tmp/verify_membership.png');

    // ──────────────────────────────────────────────
    // 5. Navigate to profile (tab page)
    // ──────────────────────────────────────────────
    console.log('\n--- Step 5: Profile (pages/profile/profile) ---');
    await mp.switchTab('pages/profile/profile');
    await sleep(2000);
    page = await mp.currentPage();
    console.log(`  Current page: ${page.path}`);

    await screenshot(mp, '/tmp/verify_profile.png');

    // ──────────────────────────────────────────────
    // 6. Check console for errors
    // ──────────────────────────────────────────────
    console.log('\n--- Step 6: Console Error Check ---');
    const logs = await mp.getLogs();
    const errorLogs = logs.filter(l => l.level === 'error');
    const warnLogs = logs.filter(l => l.level === 'warn');

    console.log(`  Total logs: ${logs.length}`);
    console.log(`  Error logs: ${errorLogs.length}`);
    console.log(`  Warning logs: ${warnLogs.length}`);

    if (errorLogs.length > 0) {
      console.log('  --- Errors ---');
      errorLogs.forEach((l, i) => {
        console.log(`  [${i + 1}] ${l.msg}`);
      });
    } else {
      console.log('  [OK] No errors found in console');
    }

    if (warnLogs.length > 0) {
      console.log('  --- Warnings ---');
      warnLogs.forEach((l, i) => {
        console.log(`  [${i + 1}] ${l.msg}`);
      });
    }

    // ──────────────────────────────────────────────
    // Summary
    // ──────────────────────────────────────────────
    console.log('\n=== VERIFICATION COMPLETE ===');
    console.log(`Screenshots:`);
    console.log(`  /tmp/verify_home.png`);
    console.log(`  /tmp/verify_encyclopedia.png`);
    console.log(`  /tmp/verify_reading.png`);
    console.log(`  /tmp/verify_membership.png`);
    console.log(`  /tmp/verify_profile.png`);
    console.log(`Errors: ${errorLogs.length}`);
    console.log(`Warnings: ${warnLogs.length}`);

    await mp.close();
    console.log('\n[OK] Connection closed.');

  } catch (e) {
    console.log(`\n[FATAL] ${e.message}`);
    console.log(e.stack);
    if (mp) {
      try { await mp.close(); } catch (_) {}
    }
    process.exit(1);
  }
})();
