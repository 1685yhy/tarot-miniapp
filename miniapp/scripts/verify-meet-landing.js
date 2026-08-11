#!/usr/bin/env node
/**
 * verify-meet-landing.js —— 星辰相遇落地页 + 合盘海报（T2-5）逻辑测试（Node stub）
 *
 * 以 Node 运行时加载页面真实源码（wx/Page/require 打桩），覆盖：
 *   A. meet-landing scene 解析（m:{meet_id} 编码/裸值/畸形/直带 meet_id）
 *   B. 公开信息加载状态机（pending→invite / completed→done / 404→error / 降级文案）
 *   C. join 流程（未选星座拦截 / 登录引导 / payload 组装含出生信息 / 成功跳结果页 /
 *      奖励 toast / 400 弹层）
 *   D. 分享（落地页转发 scene 路径 / 标题来源）
 *   E. meet 页合盘海报（GET /meet/{id}/poster → posterData 归一化 / 失败降级 /
 *      分享打点 + /share/track + shareAppMessage 标题）
 *   F. meet-poster.js 绘制管线（canvas stub 全链路成图 / QR 拉取失败仍成图 /
 *      缺参报错）
 *
 * 运行：node miniapp/scripts/verify-meet-landing.js（无需微信 IDE / 后端）
 */
'use strict';

const fs = require('fs');
const path = require('path');

const MINIAPP = path.join(__dirname, '..');

// ============================================================
// 打桩：wx / Page / require
// ============================================================

let pageDefs = [];               // [path, config]
let requestImpl = null;          // (url, options) => Promise
let analyticsCalls = [];
let toastCalls = [];
let modalCalls = [];
let navigateCalls = [];          // {type: redirectTo|navigateTo|reLaunch, url}
let shareCalls = [];             // onShareAppMessage 返回
let shareAppMessages = [];
let downloadCalls = [];          // {url, handler 引用}
let storage = {};

const fakeRequire = (p) => {
  if (p.endsWith('utils/api') || p.endsWith('/api')) {
    return {
      request: (...args) => requestImpl(...args),
      getFriendlyError: (err) => {
        const msg = (err && err.message) || '';
        if (err && err.statusCode === 404) return '请求的资源不存在';
        if (msg && !/^[a-zA-Z]/.test(msg)) return msg;
        return '连接异常，请稍后重试';
      },
      BASE_URL: 'https://xingxiang.test/api',
    };
  }
  if (p.endsWith('utils/auth')) {
    return {
      // 真实 auth.js 登录成功会写 storage.token —— stub 同口径
      checkLogin: async () => {
        storage.token = 't-after-login';
        return { id: 'u-friend', nickname: '测试好友' };
      },
    };
  }
  if (p.endsWith('utils/analytics')) {
    return {
      trackEvent: (name, data) => analyticsCalls.push({ name, data }),
      trackShare: (channel, type) => analyticsCalls.push({ name: 'trackShare', channel, type }),
      funnel: (step, data) => analyticsCalls.push({ name: 'funnel', step, data }),
    };
  }
  if (p.endsWith('utils/config')) {
    return { DEV_LOGIN_KEY: 'dev-test-key' };
  }
  if (p.endsWith('utils/energy') || p.endsWith('utils/cards') ||
      p.endsWith('utils/canvas-poster') || p.endsWith('utils/meet-poster')) {
    // 真实模块（数据/绘制辅助）：其内部 require('./api') 被上面 stub 兜住
    let rel = p;
    while (rel.startsWith('../')) rel = rel.slice(3);
    rel = rel.replace(/^\.\//, '');
    return require(path.join(MINIAPP, rel));
  }
  throw new Error(`unexpected require: ${p}`);
};

// Proxy ctx：所有方法 noop、measureText 定宽、渐变对象可用
function makeCtx() {
  const store = {};
  return new Proxy(store, {
    get(t, prop) {
      if (prop === 'measureText') return () => ({ width: 10 });
      if (prop === 'createLinearGradient' || prop === 'createRadialGradient') {
        return () => ({ addColorStop: () => {} });
      }
      if (prop === 'canvas') return t._canvas;
      return () => {};
    },
    set(t, prop, v) { t[prop] = v; return true; },
  });
}

const canvasStub = { width: 0, height: 0 };

global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  getStorageSync: (k) => storage[k],
  setStorageSync: (k, v) => { storage[k] = v; },
  removeStorageSync: (k) => { delete storage[k]; },
  showLoading: (o) => { toastCalls.push({ type: 'showLoading', ...o }); },
  hideLoading: () => { toastCalls.push({ type: 'hideLoading' }); },
  showToast: (o) => { toastCalls.push({ type: 'showToast', ...o }); },
  showModal: (o) => { modalCalls.push(o); },
  redirectTo: (o) => { navigateCalls.push({ type: 'redirectTo', url: o.url }); },
  navigateTo: (o) => { navigateCalls.push({ type: 'navigateTo', url: o.url }); },
  reLaunch: (o) => { navigateCalls.push({ type: 'reLaunch', url: o.url }); },
  shareAppMessage: (o) => { shareAppMessages.push(o); },
  reportAnalytics: () => {},
  getSystemInfoSync: () => ({ screenWidth: 375, pixelRatio: 2 }),
  downloadFile: (o) => {
    downloadCalls.push({ url: o.url, handler: o });
    // 默认：模拟失败 → 海报走无码版式（不阻塞成图）
    (o.fail || o.complete) && o.fail && o.fail({ errMsg: 'downloadFile:fail test' });
  },
  canvasToTempFilePath: (o) => { o.success && o.success({ tempFilePath: '/tmp/meet-poster.png' }); },
  createSelectorQuery: () => ({
    in: () => ({
      select: () => ({
        fields: () => ({
          exec: (cb) => cb([{ node: canvasStub }]),
        }),
      }),
    }),
  }),
};

function loadPage(file) {
  const SRC = fs.readFileSync(path.join(MINIAPP, file), 'utf8');
  new Function('require', 'Page', 'wx', SRC)(fakeRequire, (def) => {
    pageDefs.push([file, def]);
  }, global.wx);
}

function makePage(file) {
  const [f, def] = pageDefs.find(([f0]) => f0 === file);
  if (!def) throw new Error(`page not loaded: ${file}`);
  const page = { ...def };
  page.data = JSON.parse(JSON.stringify(def.data));
  page.setData = function (patch) {
    Object.keys(patch).forEach((k) => { this.data[k] = patch[k]; });
  };
  return page;
}

// ============================================================
// 测试框架（极简）
// ============================================================

let passed = 0;
let failed = 0;
const failures = [];

function assert(cond, msg) {
  if (cond) {
    passed += 1;
  } else {
    failed += 1;
    failures.push(msg);
    console.log('  ✗ FAIL:', msg);
  }
}

async function run(name, fn) {
  console.log(`\n## ${name}`);
  try {
    await fn();
  } catch (err) {
    failed += 1;
    failures.push(`${name} threw: ${err && err.stack || err}`);
    console.log('  ✗ THREW:', err && err.message);
  }
}

// ============================================================
// 测试
// ============================================================

(async () => {
  loadPage('pages/meet-landing/meet-landing.js');
  loadPage('pages/meet/meet.js');

  // ---------- A. scene 解析 ----------
  await run('A. meet-landing scene 解析', async () => {
    const page = makePage('pages/meet-landing/meet-landing.js');
    assert(page._parseMeetId({ scene: 'm%3AMEET-001' }) === 'MEET-001', '编码 scene m%3A... 解码');
    assert(page._parseMeetId({ scene: 'm:MEET-001' }) === 'MEET-001', '裸 scene m:...');
    assert(page._parseMeetId({ scene: 'm:  ' }) === '', 'scene m: 空 meet_id → 空');
    assert(page._parseMeetId({ scene: '', meet_id: 'MT-9' }) === 'MT-9', '直带 meet_id');
    assert(page._parseMeetId({ scene: 'invite_code=STAR-1' }) === '', '旧版邀请码 scene → 空');
    assert(page._parseMeetId({ scene: '%zz' }) === '', '畸形 % 编码不抛异常');
    assert(page._parseMeetId({}) === '', '无参数 → 空');
  });

  // ---------- B. 公开信息状态机 ----------
  await run('B. 公开信息加载状态机', async () => {
    // pending → invite
    requestImpl = async (url) => {
      assert(url === '/meet/public/MEET-001', '请求公开接口路径');
      return { meet_id: 'MEET-001', nickname: '星星', zodiac_cn: '白羊座', star_tier_name: '星光', status: 'pending' };
    };
    let page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page.onLoad({ scene: 'm%3AMEET-001' });
    await new Promise((r) => setTimeout(r, 0));
    assert(page.data.step === 'invite', `pending → invite（实际 ${page.data.step}）`);
    assert(page.data.info.nickname === '星星', '昵称映射');
    assert(page.data.info.zodiacCn === '白羊座' && page.data.info.hasZodiac === true, '星座映射');
    assert(page.data.info.hasTier === true, '星阶映射');
    assert(page.data.loggedIn === true, '有 token → loggedIn');

    // completed → done
    requestImpl = async () => ({ meet_id: 'MEET-001', nickname: '星星', zodiac_cn: '白羊座', star_tier_name: '星光', status: 'completed' });
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = '';
    page.onLoad({ scene: 'm:MEET-001' });
    await new Promise((r) => setTimeout(r, 0));
    assert(page.data.step === 'done', `completed → done（实际 ${page.data.step}）`);
    assert(page.data.loggedIn === false, '无 token → loggedIn false');

    // 404 → error 优雅文案
    requestImpl = async () => { throw Object.assign(new Error('相遇记录不存在'), { statusCode: 404 }); };
    page = makePage('pages/meet-landing/meet-landing.js');
    page.onLoad({ scene: 'm:MEET-404' });
    await new Promise((r) => setTimeout(r, 0));
    assert(page.data.step === 'error', '404 → error');
    assert(page.data.errorMsg === '这场相遇不存在或已失效', '404 优雅文案');

    // 500 → 友好文案
    requestImpl = async () => { throw Object.assign(new Error('服务器繁忙，请稍后重试'), { statusCode: 500 }); };
    page = makePage('pages/meet-landing/meet-landing.js');
    page.onLoad({ scene: 'm:MEET-500' });
    await new Promise((r) => setTimeout(r, 0));
    assert(page.data.step === 'error' && page.data.errorMsg.includes('服务器繁忙'), '500 友好文案');

    // 无 meet_id → 直接错误态
    page = makePage('pages/meet-landing/meet-landing.js');
    page.onLoad({});
    assert(page.data.step === 'error' && page.data.errorMsg.includes('链接不完整'), '无参数 → 链接不完整');
  });

  // ---------- C. join 流程 ----------
  await run('C. join 流程（选星座/登录/payload/跳转/奖励/400）', async () => {
    // C1 未选星座拦截
    requestImpl = async () => { throw new Error('不应发起请求'); };
    let page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page._meetId = 'MEET-001';
    page.onLoad({ scene: 'm:MEET-001' });
    await page.onAccept();
    assert(toastCalls.some((t) => t.title && t.title.includes('先选一个星座')), '未选星座 → toast 拦截');
    assert(!navigateCalls.length, '未选星座不发请求不跳转');

    // C2 已登录 + 星座 → payload 组装 + 成功跳结果页
    let joinData = null;
    requestImpl = async (url, opts) => {
      if (url === '/meet/join') {
        joinData = opts.data;
        return { meet_id: 'MEET-001', score: 92, level_name: '星光相映', reward_granted: true, reward_note: null };
      }
      throw new Error('unexpected url ' + url);
    };
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page._meetId = 'MEET-001';
    page.onLoad({ scene: 'm:MEET-001' });
    page.onZodiacTap({ currentTarget: { dataset: { key: 'taurus' } } });
    assert(page.data.hasZodiac === true && page.data.zodiacKey === 'taurus', '选星座 → hasZodiac/zodiacKey');
    await page.onAccept();
    assert(joinData && joinData.meet_id === 'MEET-001' && joinData.zodiac_b === 'taurus', 'join payload 正确');
    assert(joinData.b_birth_date === undefined && joinData.b_birth_time === undefined, '无出生信息不发送');
    assert(toastCalls.some((t) => t.title && t.title.includes('相遇达成') && t.title.includes('奖励')), 'reward_granted → 奖励 toast');
    await new Promise((r) => setTimeout(r, 1000)); // 等 900ms 跳转定时器
    assert(navigateCalls.some((n) => n.type === 'redirectTo' && n.url === '/pages/meet/meet?meet_id=MEET-001'), 'join 成功 → redirectTo 结果页');

    // C3 带出生日期 + 时间 → payload 含 b_birth_*
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page._meetId = 'M2';
    page.onLoad({ scene: 'm:M2' });
    page.onZodiacTap({ currentTarget: { dataset: { key: 'cancer' } } });
    page.onDateChange({ detail: { value: '1995-07-20' } });
    page.onTimeChange({ detail: { value: '14:30' } });
    await page.onAccept();
    assert(joinData.b_birth_date === '1995-07-20' && joinData.b_birth_time === '14:30', '出生日期+时间进入 payload');

    // C4 未登录 → 先登录再 join（auth.checkLogin stub 恒成功）
    joinData = null;
    navigateCalls = [];
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = '';
    page._meetId = 'M3';
    page.onLoad({ scene: 'm:M3' });
    assert(page.data.loggedIn === false, '未登录初始态');
    page.onZodiacTap({ currentTarget: { dataset: { key: 'leo' } } });
    await page.onAccept();
    assert(joinData && joinData.zodiac_b === 'leo', '未登录 → 登录后仍完成 join');
    await new Promise((r) => setTimeout(r, 1000)); // 等 900ms 跳转定时器
    assert(navigateCalls.some((n) => n.type === 'redirectTo' && n.url === '/pages/meet/meet?meet_id=M3'), '登录后 join 成功跳结果页');

    // C5 join 400 → 弹层（后端 detail 文案）
    requestImpl = async () => { throw Object.assign(new Error('该相遇未在邀请中或已完成'), { statusCode: 400 }); };
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page._meetId = 'M4';
    page.onLoad({ scene: 'm:M4' });
    page.onZodiacTap({ currentTarget: { dataset: { key: 'pisces' } } });
    await page.onAccept();
    assert(modalCalls.some((m) => m.content && m.content.includes('未在邀请中')), 'join 400 → 弹层展示后端文案');
    assert(page.data.submitting === false && page.data.submitLabel === '接受相遇 ✦', '400 后按钮复位');

    // C6 join 网络错误 → toast + 复位
    requestImpl = async () => { throw new Error('网络连接异常，请检查网络后重试'); };
    page = makePage('pages/meet-landing/meet-landing.js');
    storage.token = 't1';
    page._meetId = 'M5';
    page.onLoad({ scene: 'm:M5' });
    page.onZodiacTap({ currentTarget: { dataset: { key: 'gemini' } } });
    await page.onAccept();
    assert(toastCalls.some((t) => t.title && t.title.includes('网络')), '网络错误 → toast');
    assert(page.data.submitting === false, '网络错误后按钮复位');

    // C7 已完成态跳转
    page = makePage('pages/meet-landing/meet-landing.js');
    navigateCalls = [];
    page.onViewResult();
    assert(navigateCalls.some((n) => n.type === 'redirectTo' && n.url === '/pages/meet/meet?meet_id='), 'onViewResult redirectTo 结果页');
    page.onGoCreate();
    assert(navigateCalls.some((n) => n.type === 'navigateTo' && n.url === '/pages/meet/meet'), 'onGoCreate navigateTo 发起页');
  });

  // ---------- D. 落地页分享 ----------
  await run('D. 落地页分享', async () => {
    const page = makePage('pages/meet-landing/meet-landing.js');
    page._meetId = 'MEET-001';
    page.setData({ info: { nickname: '星星' }, hasInfo: true });
    const msg = page.onShareAppMessage();
    assert(msg.title.includes('星星') && msg.title.includes('邀请你进行星辰相遇'), '分享标题含昵称');
    assert(msg.path === '/pages/meet-landing/meet-landing?scene=m%3AMEET-001', '分享路径带 scene=m:{id}');
    const tl = page.onShareTimeline();
    assert(tl.query === 'scene=m%3AMEET-001', '朋友圈 query 带 scene');
  });

  // ---------- E. meet 页合盘海报 ----------
  await run('E. meet 页合盘海报（poster 数据流）', async () => {
    // E1 成功：归一化 + showPoster
    requestImpl = async (url) => {
      if (url === '/meet/MEET-001/poster') {
        return {
          meet_id: 'MEET-001', relation: 'friend',
          a: { zodiac: 'aries', name_zh: '白羊座', nickname: '星星' },
          b: { zodiac: 'taurus', name_zh: '金牛座' },
          score: 92, level_name: '星光相映',
          cards: [
            { position: '过去', name_zh: '星币八' },
            { position: '现在', name_zh: '恋人' },
            { position: '未来', name_zh: '太阳' },
            { position: 'extra', name_zh: '愚者' },
          ],
          share_text: '我和 TA 的星辰共鸣度是 92 · 看看你和谁星光相映 ✦',
        };
      }
      if (url === '/share/track') return { success: true, rewarded: true };
      throw new Error('unexpected url ' + url);
    };
    const page = makePage('pages/meet/meet.js');
    page._meetId = 'MEET-001';
    await page.onSharePoster();
    assert(page.data.showPoster === true, 'posterData 就绪 → showPoster');
    assert(page.data.posterData.score === 92 && page.data.posterData.level_name === '星光相映', 'score/level 归一化');
    assert(page.data.posterData.cards.length === 4, 'cards 透传（绘制管线内部截取前 3）');
    assert(page.data.posterData.a.nickname === '星星', 'a 侧昵称透传');
    assert(page.data.posterLoading === false && page.data.posterLabel === '合盘海报', '按钮复位');
    assert(analyticsCalls.some((c) => c.name === 'meet_poster'), 'meet_poster 事件打点');

    // E2 分享给朋友：shareAppMessage 标题用后端 share_text + 打点 + /share/track
    shareAppMessages = [];
    analyticsCalls = [];
    page.onShareMeetPosterToFriend({ detail: { imagePath: '/tmp/poster.png' } });
    await new Promise((r) => setTimeout(r, 0));
    assert(shareAppMessages.length === 1 && shareAppMessages[0].imageUrl === '/tmp/poster.png', 'shareAppMessage 带海报图');
    assert(shareAppMessages[0].title.includes('92'), '分享标题 = 后端 share_text');
    assert(analyticsCalls.some((c) => c.name === 'trackShare' && c.type === 'meet_poster'), 'trackShare 打点');

    // E3 imagePath 缺失防御
    shareAppMessages = [];
    page.onShareMeetPosterToFriend({ detail: {} });
    assert(shareAppMessages.length === 0, '无 imagePath → 不分享');

    // E4 失败降级：海报数据异常 → toast，按钮复位
    requestImpl = async () => { throw Object.assign(new Error('相遇记录不存在'), { statusCode: 404 }); };
    const page2 = makePage('pages/meet/meet.js');
    page2._meetId = 'MEET-X';
    page2.onSharePoster();
    await new Promise((r) => setTimeout(r, 20)); // 等异步 catch 落地
    assert(page2.data.showPoster === false, '失败 → 不弹层');
    assert(page2.data.posterLoading === false && page2.data.posterLabel === '合盘海报', '失败 → 按钮复位');
    assert(toastCalls.some((t) => t.title && t.title.includes('不存在')), '失败 → toast 提示');
  });

  // ---------- F. meet-poster.js 绘制管线 ----------
  await run('F. meet-poster.js 绘制管线（canvas stub 全链路）', async () => {
    const { drawMeetPoster } = fakeRequire('utils/meet-poster');

    // F1 缺参报错
    let errMsg = '';
    drawMeetPoster('c1', null, { onError: (e) => { errMsg = e.message; } });
    assert(errMsg.includes('Missing required params'), '缺 pageContext → onError');

    // F2 全链路成图（QR 下载失败 → 无码版式仍成图）
    const poster = {
      meet_id: 'MEET-001',
      a: { zodiac: 'aries', name_zh: '白羊座', nickname: '星星' },
      b: { zodiac: 'taurus', name_zh: '金牛座' },
      score: 92,
      level_name: '星光相映',
      cards: [
        { position: '过去', name_zh: '星币八' },
        { position: '现在', name_zh: '恋人' },
        { position: '未来', name_zh: '太阳' },
      ],
      share_text: '我和 TA 的星辰共鸣度是 92 · 看看你和谁星光相映 ✦',
    };
    const dlUrl = downloadCalls.length ? downloadCalls[downloadCalls.length - 1].url : '';
    downloadCalls = [];
    const got = await new Promise((resolve) => {
      const ctx = makeCtx();
      canvasStub.getContext = () => ctx;
      drawMeetPoster('c2', { _dummy: true }, {
        poster,
        onSuccess: (p) => resolve(p),
        onError: (e) => resolve('ERR:' + e.message),
      });
    });
    assert(got === '/tmp/meet-poster.png', 'QR 失败 → 无码版式仍成图');
    assert(downloadCalls.some((d) => d.url.includes('/share/wxa-code') &&
      d.url.includes('pages%2Fmeet-landing%2Fmeet-landing') &&
      d.url.includes('scene=m%3AMEET-001')), 'QR 请求带 meet-landing path + scene=m:{id}');

    // F3 score 缺失 → '--' 仍成图
    const got2 = await new Promise((resolve) => {
      canvasStub.getContext = () => makeCtx();
      drawMeetPoster('c3', {}, {
        poster: { meet_id: 'M', a: {}, b: {}, score: null, cards: [] },
        onSuccess: (p) => resolve(p),
        onError: (e) => resolve('ERR:' + e.message),
      });
    });
    assert(got2 === '/tmp/meet-poster.png', 'score 缺失 → 照常成图');
  });

  // ---------- 汇总 ----------
  console.log(`\n========== 结果：${passed} 通过 / ${failed} 失败 ==========`);
  if (failed > 0) {
    console.log('失败项：');
    failures.forEach((f) => console.log('  -', f));
    process.exit(1);
  }
  process.exit(0);
})();
