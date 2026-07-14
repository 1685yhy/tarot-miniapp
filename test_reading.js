const a = require('miniprogram-automator');

(async () => {
  const mp = await a.connect({ wsEndpoint: 'ws://127.0.0.1:9422' });
  console.log('OK');

  // Navigate directly to reading with spread type
  await mp.navigateTo('/pages/reading/reading?type=three_card');
  await new Promise(r => setTimeout(r, 3000));
  let page = await mp.currentPage();
  console.log('1. Reading:', page.path);

  // Type question
  let ta = await page.$('textarea');
  if (ta) {
    console.log('2. Typing question...');
    await ta.input('今天的工作运势怎么样');
    await new Promise(r => setTimeout(r, 500));

    // Find and click start button
    let btn = await page.$('button');
    if (btn) {
      console.log('3. Starting AI reading...');
      await btn.tap();

      // Wait for AI
      console.log('4. Waiting for deepseek-v4-pro (~20-30s)...');
      await new Promise(r => setTimeout(r, 35000));

      page = await mp.currentPage();
      console.log('5. Page:', page.path);

      if (page.path.includes('reading-result')) {
        console.log('SUCCESS! Result page.');
        await mp.screenshot({path: '/tmp/result_final.png'});
        let data = await page.data();
        console.log('Reading:', !!data.reading);
      } else if (page.path.includes('reading')) {
        console.log('Still on reading - AI may have failed');
        let data = await page.data();
        console.log('Error:', data.pageError || 'none');
        console.log('Drawing:', data.isDrawing);
      }
    } else {
      console.log('No button found');
    }
  } else {
    console.log('No textarea - onLoad auto-select not working');
  }

  await mp.close();
  console.log('DONE');
})().catch(e => console.log('FAIL:', (e.message||'').substring(0, 200)));
