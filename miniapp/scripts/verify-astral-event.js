#!/usr/bin/env node
/**
 * verify-astral-event.js —— 星象节点活动页三形态（astral-event）逻辑测试（Node stub）
 *
 * 以 Node 运行时加载页面真实源码（wx/Page/require 打桩，无需微信 IDE / 后端），覆盖：
 *   A. 三形态路由：日历页跳转携带的**活动形态**（wish/review/mercury_guide）与
 *      订阅消息直达的**事件类型**（new_moon/full_moon/mercury_retrograde）双向映射
 *      → GET /astral/event/{事件类型} 请求正确；solar_term → info 兜底
 *   B. 渲染预计算：许愿窗口/慢行期区间文本、倒计时文案（days_left 0/1/N）、
 *      愿望状态计数与 hasAnyWish、慢行期清单 stars/litCount/allLit、
 *      range 空态（EMPTY_RETROGRADE_RANGE → rangeActive=false 按钮隐藏）
 *   C. 清单交互：勾选点亮/取消/重亮/非法 index 防御
 *   D. 打卡幂等：POST /astral/activity {event_key}；本地按日记录 → 同日重进
 *      展示完成态且不再发请求；重复点击无重复 toast
 *   E. 降级：后端 500 → 错误态 + 重试恢复；未知 type → 400 错误态
 *   F. onShow 静默刷新：wish/review 返回时刷新愿望计数；慢行期不刷新（保留勾选进度）
 *   G. T3-5 Fix 回归：wish/review 打卡「当天门控」（today === window.start，非当天
 *      点击不发请求 + 提示含日期）、慢行清单 7 条与后端裁剪对齐、分享携带原始事件
 *      类型（info 分享不再退化成 type=info）
 *
 * 运行：node miniapp/scripts/verify-astral-event.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ============================================================
// 打桩：wx / Page / require
// ============================================================

let pageDef = null;
let requestCalls = [];
let toasts = [];
let navigations = [];
const store = {};

const fakeRequire = (p) => {
  if (p.includes('utils/api')) {
    return {
      request: async (url, opts) => {
        requestCalls.push({ url, opts });
        return mockRespond(url, opts);
      },
      getFriendlyError: (err) => (err && err.message) || '网络异常',
    };
  }
  if (p.includes('utils/analytics')) {
    return { trackEvent: () => {} };
  }
  throw new Error(`unexpected require: ${p}`);
};

global.wx = {
  getStorageSync: (k) => store[k],
  setStorageSync: (k, v) => { store[k] = v; },
  removeStorageSync: (k) => { delete store[k]; },
  setNavigationBarTitle: () => {},
  showToast: (o) => toasts.push(o),
  vibrateShort: () => {},
  navigateTo: (o) => navigations.push(o),
  navigateBack: () => navigations.push({ __back: true }),
};
global.getApp = () => ({ globalData: {} });

const SRC = fs.readFileSync(
  path.join(__dirname, '../pages/astral-event/astral-event.js'),
  'utf8'
);
new Function('require', 'Page', 'wx', SRC)(fakeRequire, (def) => { pageDef = def; }, global.wx);
if (!pageDef) throw new Error('Page() 未被调用——页面源码加载失败');

// ============================================================
// 后端 mock：节点内容 + 打卡（幂等）
// ============================================================

const CONTENT = {
  new_moon: {
    type: 'wish', title: '许愿之夜',
    window: { start: '2026-08-12', end: '2026-08-14', days_left: 3 },
    content: '写给月亮的三行愿望', target_page: 'pages/wish/wish',
    wish_counts: { active: 2, grown: 1, answered: 0 },
  },
  full_moon: {
    type: 'review', title: '复盘之夜',
    // window.start = 满月日（后端 T3-5 Fix 新增：打卡当天门控比对依据）
    window: { start: '2026-08-28', end: '2026-08-28', days_left: 17 },
    wish_counts: { active: 0, grown: 1, answered: 0 }, target_page: 'pages/review/review',
  },
  mercury_retrograde: {
    type: 'mercury_guide', title: '慢行期',
    range: { start: '2026-08-14', end: '2026-09-04', days_left: 21 },
    // 7 条：与后端 MERCURY_CARE_ITEMS（8→7 裁剪后）对齐，「慢下来的 7 件小事」
    items: ['甲', '乙', '丙', '丁', '戊', '己', '庚'],
    daily_sentence: '慢一点，也是在前进。',
  },
  solar_term: { type: 'info', notes: ['立秋之后，暑气渐收。', '宜早睡。'] },
};
let failNext = false;

function mockRespond(url, opts) {
  if (failNext) { failNext = false; const e = new Error('mock 500'); e.statusCode = 500; throw e; }
  const m = url.match(/^\/astral\/event\/(.+)$/);
  if (m) {
    if (!CONTENT[m[1]]) { const e = new Error('未知的天象事件类型'); e.statusCode = 400; throw e; }
    return CONTENT[m[1]];
  }
  if (url === '/astral/activity') {
    return { ok: true, rewarded: true, stardust_total: 3 };
  }
  throw new Error('unexpected url ' + url);
}

// ============================================================
// 页面实例工厂（真实源码 + setData 打桩）
// ============================================================

function fresh() {
  const inst = {
    ...pageDef,
    data: JSON.parse(JSON.stringify(pageDef.data)),
    setData(patch) { Object.assign(this.data, patch); },
  };
  return inst;
}

// ============================================================
// 极简测试框架
// ============================================================

let passed = 0;
let failed = 0;
function assert(name, cond, extra) {
  if (cond) { passed++; console.log('  PASS ' + name); }
  else { failed++; console.log('  FAIL ' + name + (extra !== undefined ? ' => ' + JSON.stringify(extra) : '')); }
}

// 断行符等价比较（en-dash 编码无关）
const dash = (s) => s.replace(/–/g, '~');

(async () => {
  console.log('== A. wish 形态（日历页跳转 type=wish）==');
  let page = fresh();
  await page.onLoad({ type: 'wish' });
  page._today = '2026-08-13'; // 钉死窗口第 2 天（非新月当天）
  await page._loadContent(false);
  assert('请求事件类型 new_moon', requestCalls[0].url === '/astral/event/new_moon');
  assert('nodeType=wish', page.data.nodeType === 'wish');
  assert('windowText=8.12–8.14', dash(page.data.windowText) === '8.12 ~ 8.14', page.data.windowText);
  assert('windowDaysText=还有 3 天结束', page.data.windowDaysText === '还有 3 天结束');
  assert('hasAnyWish=true', page.data.hasAnyWish === true);
  assert('wishStatus 计数 [2,1,0]', JSON.stringify(page.data.wishStatus.map((s) => s.count)) === '[2,1,0]');
  assert('初始未打卡', page.data.checkedToday === false);

  console.log('== A1. 打卡当天门控（T3-5 Fix：仅新月当天可点亮）==');
  assert('窗口第 2 天 canCheckIn=false', page.data.canCheckIn === false, page.data.canCheckIn);
  assert('非当天提示含日期', page.data.checkinHint === '仅 8.12 当天可点亮 ✦', page.data.checkinHint);
  const reqs0 = requestCalls.length;
  await page.onCheckIn();
  assert('非当天点击不发请求', requestCalls.length === reqs0, requestCalls.length);
  page._today = '2026-08-12'; // 新月当天 = window.start
  await page._loadContent(false);
  assert('新月当天 canCheckIn=true', page.data.canCheckIn === true, page.data.canCheckIn);
  const toastsBefore = toasts.length;
  await page.onCheckIn();
  const reqsAfterPost = requestCalls.length;
  assert('POST event_key=wish', requestCalls[requestCalls.length - 1].opts.data.event_key === 'wish');
  assert('打卡后 checkedToday=true', page.data.checkedToday === true);
  assert('奖励 toast 星尘 +1', toasts.length === toastsBefore + 1 && toasts[toasts.length - 1].title.includes('星尘 +1'));
  await page.onCheckIn(); // 重复点击
  assert('重复打卡无新请求', requestCalls.length === reqsAfterPost, requestCalls.length);
  assert('重复打卡无新 toast', toasts.length === toastsBefore + 1);

  console.log('== A2. 同日重进 → 已打卡完成态 ==');
  page = fresh();
  await page.onLoad({ type: 'wish' });
  page._today = '2026-08-12'; // 与 A 段打卡日一致
  await page._loadContent(false);
  assert('重进 checkedToday=true', page.data.checkedToday === true);

  console.log('== B. review 形态（事件类型直达 type=full_moon）==');
  page = fresh();
  await page.onLoad({ type: 'full_moon' });
  assert('事件类型直达→nodeType=review', page.data.nodeType === 'review');
  assert('wishStatus 计数 [0,1,0]', JSON.stringify(page.data.wishStatus.map((s) => s.count)) === '[0,1,0]');
  await page.onGoReview();
  assert('跳转 /pages/review/review', navigations.some((n) => n.url === '/pages/review/review'));

  console.log('== B2. review 打卡当天门控（满月日 = 后端 window.start）==');
  page = fresh();
  await page.onLoad({ type: 'full_moon' });
  page._today = '2026-08-28'; // 满月当天（mock window.start）
  await page._loadContent(false);
  assert('满月当天 canCheckIn=true', page.data.canCheckIn === true, page.data.canCheckIn);
  await page.onCheckIn();
  assert('POST event_key=review', requestCalls[requestCalls.length - 1].opts.data.event_key === 'review');
  page = fresh();
  await page.onLoad({ type: 'full_moon' });
  page._today = '2026-08-11'; // 非满月日（隔天打开分享链接）
  await page._loadContent(false);
  assert('非满月日 canCheckIn=false', page.data.canCheckIn === false, page.data.canCheckIn);
  assert('review 非当天提示含日期', page.data.checkinHint === '仅 8.28 当天可点亮 ✦', page.data.checkinHint);
  const reqsR = requestCalls.length;
  await page.onCheckIn();
  assert('非当天点击不发请求', requestCalls.length === reqsR, requestCalls.length);

  console.log('== C. mercury_guide 形态 ==');
  page = fresh();
  requestCalls = [];
  await page.onLoad({ type: 'mercury_guide' });
  assert('请求事件类型 mercury_retrograde', requestCalls[0].url === '/astral/event/mercury_retrograde');
  assert('nodeType=mercury_guide', page.data.nodeType === 'mercury_guide');
  assert('rangeText=8.14–9.4', dash(page.data.rangeText) === '8.14 ~ 9.4', page.data.rangeText);
  assert('rangeDaysText=还有 21 天结束', page.data.rangeDaysText === '还有 21 天结束');
  assert('canCheckIn=false（8.11 不在区间内）', page.data.canCheckIn === false, page.data.canCheckIn);
  assert('totalItems=7（与后端 8→7 裁剪对齐）', page.data.totalItems === 7);
  assert('dailySentence 有值', page.data.dailySentence === '慢一点，也是在前进。');
  for (let i = 0; i < 7; i++) page.onToggleItem({ currentTarget: { dataset: { index: i } } });
  assert('7 项全点亮 allLit=true', page.data.allLit === true);
  assert('litCount=7 stars 全亮', page.data.litCount === 7 && page.data.stars.every((s) => s.lit));
  page.onToggleItem({ currentTarget: { dataset: { index: 3 } } });
  assert('取消一项 allLit=false', page.data.allLit === false && page.data.litCount === 6);
  page.onToggleItem({ currentTarget: { dataset: { index: 3 } } });
  assert('重新点亮 allLit=true', page.data.allLit === true);
  page.onToggleItem({ currentTarget: { dataset: { index: 99 } } });
  assert('非法 index 忽略', page.data.litCount === 7);

  console.log('== C2. 区间内（模拟 today=8.20）可打卡 ==');
  page = fresh();
  page._today = '2026-08-20';
  page._eventType = 'mercury_retrograde';
  await page._loadContent(false);
  assert('区间内 canCheckIn=true', page.data.canCheckIn === true, page.data.canCheckIn);
  for (let i = 0; i < 7; i++) page.onToggleItem({ currentTarget: { dataset: { index: i } } });
  await page.onCheckIn();
  assert('POST event_key=mercury_guide', requestCalls[requestCalls.length - 1].opts.data.event_key === 'mercury_guide');
  assert('打卡后 checkedToday=true', page.data.checkedToday === true);

  console.log('== C3. range 空态（EMPTY_RETROGRADE_RANGE）==');
  page = fresh();
  const realContent = CONTENT.mercury_retrograde;
  CONTENT.mercury_retrograde = { type: 'mercury_guide', title: '慢行期', range: { start: '', end: '', days_left: 0 }, items: ['甲'], daily_sentence: '' };
  await page.onLoad({ type: 'mercury_guide' });
  assert('空range rangeActive=false', page.data.rangeActive === false);
  assert('空range canCheckIn=false（按钮隐藏）', page.data.canCheckIn === false);
  CONTENT.mercury_retrograde = realContent;

  console.log('== D. info 兜底（type=solar_term）==');
  page = fresh();
  await page.onLoad({ type: 'solar_term' });
  assert('nodeType=info', page.data.nodeType === 'info');
  assert('hasInfoNotes=true', page.data.hasInfoNotes === true);

  console.log('== D1. 分享携带原始事件类型（T3-5 Fix：info 不再丢类型）==');
  page = fresh();
  await page.onLoad({ type: 'wish' });
  assert('wish 分享 type=new_moon', page.onShareAppMessage().path === '/pages/astral-event/astral-event?type=new_moon', page.onShareAppMessage().path);
  page = fresh();
  await page.onLoad({ type: 'full_moon' });
  assert('review 分享 type=full_moon', page.onShareAppMessage().path.endsWith('type=full_moon'));
  page = fresh();
  await page.onLoad({ type: 'mercury_guide' });
  assert('mercury 分享 type=mercury_retrograde', page.onShareAppMessage().path.endsWith('type=mercury_retrograde'));
  page = fresh();
  await page.onLoad({ type: 'solar_term' });
  assert('info 分享保留事件类型 solar_term', page.onShareAppMessage().path.endsWith('type=solar_term'), page.onShareAppMessage().path);
  // 接收方以事件类型打开 → 映射回原形态（wish 可复达、info 可复达）
  page = fresh();
  await page.onLoad({ type: 'new_moon' });
  assert('接收方 new_moon → nodeType=wish', page.data.nodeType === 'wish');
  page = fresh();
  await page.onLoad({ type: 'solar_term' });
  assert('接收方 solar_term → info 正常渲染', page.data.nodeType === 'info' && page.data.hasInfoNotes === true);

  console.log('== E. 降级：后端 500 → 错误态 + 重试 ==');
  page = fresh();
  failNext = true;
  await page.onLoad({ type: 'wish' });
  assert('500 → error 态', page.data.error !== null && page.data.loading === false);
  failNext = false;
  await page.onRetry();
  assert('重试成功恢复', page.data.error === null && page.data.nodeType === 'wish');

  console.log('== E2. 未知 type → 400 错误态 ==');
  page = fresh();
  await page.onLoad({ type: 'bogus' });
  assert('未知 type → error 态', page.data.error !== null);

  console.log('== F. onShow 静默刷新（wish/review）与慢行期保留 ==');
  page = fresh();
  await page.onLoad({ type: 'review' });
  const callsBefore = requestCalls.length;
  await page.onShow(); // 首屏 onShow 不重拉
  assert('首屏 onShow 不重拉', requestCalls.length === callsBefore, requestCalls.length);
  CONTENT.full_moon.wish_counts = { active: 5, grown: 1, answered: 1 };
  await page.onShow(); // 返回（第二次 onShow）静默重拉
  assert('返回 onShow 静默重拉', requestCalls.length === callsBefore + 1, requestCalls.length);
  assert('计数刷新 [5,1,1]', JSON.stringify(page.data.wishStatus.map((s) => s.count)) === '[5,1,1]');
  page = fresh();
  await page.onLoad({ type: 'mercury_guide' });
  page.onToggleItem({ currentTarget: { dataset: { index: 0 } } });
  const callsM = requestCalls.length;
  await page.onShow();
  await page.onShow();
  assert('慢行期 onShow 不重拉、进度保留', requestCalls.length === callsM && page.data.litCount === 1, requestCalls.length);

  console.log(`\n===== ${passed} passed, ${failed} failed =====`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('HARNESS ERROR', e); process.exit(1); });
