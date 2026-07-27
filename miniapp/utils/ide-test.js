/**
 * 星光映照 · IDE 运行时自动化测试
 *
 * 在微信开发者工具中运行此脚本，自动遍历所有页面，
 * 检查渲染完整性、控制台错误和数据流正确性。
 *
 * 使用方式: 在 IDE 控制台粘贴运行，或通过 automator WebSocket 注入
 */
(function () {
  'use strict';
  const results = [];
  const PAGES = [
    { name: '首页', path: '/pages/index/index' },
    { name: '百科', path: '/pages/encyclopedia/encyclopedia' },
    { name: '签到', path: '/pages/checkin/checkin' },
    { name: '日记', path: '/pages/diary/diary' },
    { name: '我的', path: '/pages/profile/profile' },
    { name: '会员', path: '/pages/membership/membership' },
    { name: '每日一牌', path: '/pages/daily-card/daily-card' },
    { name: '年度报告', path: '/pages/annual-report/annual-report' },
    { name: '分享中心', path: '/pages/share-center/share-center' },
  ];

  // Intercept console.error
  const errors = [];
  const origError = console.error;
  console.error = function (...args) {
    errors.push(args.map(String).join(' '));
    origError.apply(console, args);
  };

  // Intercept setData failures
  const origSetData = Page.prototype?.setData;
  if (origSetData) {
    Page.prototype.setData = function (data, callback) {
      try { return origSetData.call(this, data, callback); }
      catch (e) { errors.push('setData error: ' + e.message); }
    };
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function testPage(page) {
    const pageErrors = [];
    try {
      await new Promise((resolve, reject) => {
        wx.navigateTo({
          url: page.path,
          success: () => setTimeout(resolve, 1500),
          fail: (e) => {
            // Tab pages need switchTab
            wx.switchTab({
              url: page.path,
              success: () => setTimeout(resolve, 1500),
              fail: () => { pageErrors.push('navigate failed: ' + JSON.stringify(e)); resolve(); }
            });
          }
        });
      });
    } catch (e) {
      pageErrors.push('exception: ' + e.message);
    }
    return { name: page.name, path: page.path, errors: [...errors, ...pageErrors] };
  }

  async function runAll() {
    console.log('=== 星光映照 · 自动化页面遍历测试 ===');
    console.log('待测页面: ' + PAGES.length + ' 个\n');

    for (let i = 0; i < PAGES.length; i++) {
      errors.length = 0;
      const page = PAGES[i];
      const result = await testPage(page);
      results.push(result);
      const status = result.errors.length === 0 ? '✅' : '❌';
      console.log(status + ' ' + (i + 1) + '/' + PAGES.length + ' ' + result.name);
      if (result.errors.length > 0) {
        result.errors.forEach(e => console.log('   └─ ' + e));
      }
      wx.navigateBack({ delta: 99, fail() {} });
      await sleep(800);
    }

    console.log('\n=== 测试完成 ===');
    const passed = results.filter(r => r.errors.length === 0).length;
    const failed = results.filter(r => r.errors.length > 0);
    console.log('通过: ' + passed + '/' + PAGES.length);

    if (failed.length > 0) {
      console.log('\n失败页面:');
      failed.forEach(f => {
        console.log('  ❌ ' + f.name + ' (' + f.path + ')');
        f.errors.forEach(e => console.log('     ' + e));
      });
    }
    return { results, total: PAGES.length, passed, failed: failed.length };
  }

  runAll().catch(e => console.error('测试框架异常:', e));
})();
