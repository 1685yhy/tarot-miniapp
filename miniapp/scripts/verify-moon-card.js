#!/usr/bin/env node
/**
 * verify-moon-card.js —— 月光卡完整版（T4-5）逻辑测试（Node stub）
 *
 * 以 Node 运行时加载页面真实源码（wx/Page/require 打桩），覆盖：
 *   A. _load 数据加载（成功 → card/hasCard；失败 → pageError）
 *   B. onSharePoster 晚安卡海报链路（posterData 组装 dateText/card、showPoster、
 *      分享中防抖、analytics 打点）
 *   C. onShareMoonPosterToFriend 分享打点（/share/track share_type=moon_card、
 *      rewarded toast、imagePath 缺失防御）
 *   D. 沉淀引导 goWriteJournal（跳转 pages/journal/journal）
 *   E. formatDateText 日期格式化（'2026-08-11' → '2026年8月11日 · 晚安'、非法输入原样）
 *   F. onShareAppMessage
 *
 * 运行：node miniapp/scripts/verify-moon-card.js（无需微信 IDE / 后端）
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ============================================================
// 打桩：wx / Page / require
// ============================================================

let pageDef = null;
let requestImpl = null;
let analyticsCalls = [];
let toastCalls = [];
let navigateCalls = [];
let shareCalls = [];
let shareAppMessages = [];

const fakeRequire = (p) => {
  if (p.includes('utils/api')) {
    return {
      request: (...args) => requestImpl(...args),
      getFriendlyError: (err) => (err && err.message) || String(err),
    };
  }
  if (p.includes('utils/analytics')) {
    return {
      trackEvent: (name, data) => analyticsCalls.push({ name, data }),
      trackShare: (channel, type) => analyticsCalls.push({ name: 'trackShare', channel, type }),
    };
  }
  throw new Error(`unexpected require: ${p}`);
};

global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  showLoading: (o) => { toastCalls.push({ type: 'showLoading', ...o }); },
  hideLoading: () => { toastCalls.push({ type: 'hideLoading' }); },
  showToast: (o) => { toastCalls.push({ type: 'showToast', ...o }); },
  navigateTo: (o) => { navigateCalls.push(o); o.success && o.success(); },
  shareAppMessage: (o) => { shareAppMessages.push(o); },
  vibrateShort: (o) => (o && o.success && o.success(), { catch: () => {} }),
};

const SRC = fs.readFileSync(
  path.join(__dirname, '../pages/moon-card/moon-card.js'),
  'utf8'
);
new Function('require', 'Page', 'wx', SRC)(fakeRequire, (def) => { pageDef = def; }, global.wx);

if (!pageDef) throw new Error('Page() 未被调用——页面源码加载失败');

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
    console.error(`  ✗ ${msg}`);
  }
}

function assertEq(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) {
    passed += 1;
  } else {
    failed += 1;
    failures.push(`${msg}（期望 ${e}，实际 ${a}）`);
    console.error(`  ✗ ${msg}（期望 ${e}，实际 ${a}）`);
  }
}

const MOCK_CARD = {
  date: '2026-08-11',
  phase: { emoji: '🌕', label: '满月' },
  phrase: '把今天的疲惫，交给月亮收好。',
  star_color: '#E8B4A0',
  star_number: 3,
  source: 'ai',
};

function freshInstance() {
  analyticsCalls = [];
  toastCalls = [];
  navigateCalls = [];
  shareCalls = [];
  shareAppMessages = [];
  const inst = { data: JSON.parse(JSON.stringify(pageDef.data)) };
  for (const k of Object.keys(pageDef)) {
    if (typeof pageDef[k] === 'function') inst[k] = pageDef[k].bind(inst);
  }
  inst.setData = function (patch, cb) {
    Object.assign(this.data, patch);
    if (cb) cb();
  };
  return inst;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ============================================================
// 用例
// ============================================================

async function run() {
  // ---- A. _load 数据加载 ----
  {
    const inst = freshInstance();
    requestImpl = async () => MOCK_CARD;
    await inst._load();
    assertEq(inst.data.loading, false, 'A1 加载完成后 loading=false');
    assert(inst.data.hasCard === true, 'A2 成功加载后 hasCard=true');
    assertEq(inst.data.card.phase.emoji, '🌕', 'A3 月相 emoji 透传');
    assertEq(inst.data.pageError, null, 'A4 成功路径 pageError=null');
  }
  {
    const inst = freshInstance();
    requestImpl = async () => { throw new Error('月光暂时迷路了'); };
    await inst._load();
    assertEq(inst.data.loading, false, 'A5 失败路径 loading=false');
    assert(inst.data.hasCard === false, 'A6 失败路径 hasCard=false');
    assert(!!inst.data.pageError, 'A7 失败路径 pageError 有值');
  }
  {
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    inst.onRetry();
    requestImpl = async () => MOCK_CARD;
    await sleep(0);
    // onRetry 仅调用 _load——上面重新注入 request 后，等待微任务
    await sleep(10);
    assert(inst.data.loading === false, 'A8 onRetry 触发重新加载');
  }

  // ---- B. onSharePoster 晚安卡海报链路 ----
  {
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    inst.onSharePoster();
    await sleep(180);
    assert(inst.data.showPoster === true, 'B1 生成后 showPoster=true');
    const pd = inst.data.posterData;
    assert(!!pd, 'B2 posterData 已组装');
    assertEq(pd.dateText, '2026年8月11日 · 晚安', 'B3 dateText 格式化');
    assertEq(pd.card.date, '2026-08-11', 'B4 card 原样透传');
    assert(analyticsCalls.some((a) => a.name === 'moon_card_poster'), 'B5 海报打点 moon_card_poster');
  }
  {
    // 无 card 防御
    const inst = freshInstance();
    inst.onSharePoster();
    await sleep(180);
    assert(inst.data.showPoster === false, 'B6 无 card 不弹海报');
  }
  {
    // 分享中防抖
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    inst.onSharePoster();
    inst.data.showPoster = true;
    inst.onSharePoster();
    await sleep(180);
    const posts = analyticsCalls.filter((a) => a.name === 'moon_card_poster');
    assert(posts.length === 1, 'B7 sharing 防抖：仅一次生成');
  }

  // ---- C. onShareMoonPosterToFriend ----
  {
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    requestImpl = async () => ({ rewarded: true });
    inst.onShareMoonPosterToFriend({ detail: { imagePath: '/tmp/poster.png' } });
    await sleep(10);
    const track = analyticsCalls.find((a) => a.name === 'trackShare');
    assert(!!track && track.channel === 'wechat_friend' && track.type === 'moon_card', 'C1 分享打点 wechat_friend/moon_card');
    assert(shareAppMessages.length === 1, 'C2 wx.shareAppMessage 携带海报');
    assertEq(shareAppMessages[0].imageUrl, '/tmp/poster.png', 'C3 分享图=海报');
    assert(toastCalls.some((t) => t.title && t.title.includes('奖励已发放')), 'C4 rewarded 弹奖励 toast');
  }
  {
    // imagePath 缺失防御
    const inst = freshInstance();
    inst.onShareMoonPosterToFriend({ detail: {} });
    assert(shareAppMessages.length === 0, 'C5 无 imagePath 不分享');
  }
  {
    // shareAppMessage 抛错降级
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    const orig = global.wx.shareAppMessage;
    global.wx.shareAppMessage = () => { throw new Error('fail'); };
    inst.onShareMoonPosterToFriend({ detail: { imagePath: '/tmp/p.png' } });
    global.wx.shareAppMessage = orig;
    await sleep(10);
    assert(toastCalls.some((t) => t.title && t.title.includes('保存海报')), 'C6 shareAppMessage 失败 → 降级提示');
  }

  // ---- D. 沉淀引导 ----
  {
    const inst = freshInstance();
    inst.goWriteJournal();
    assertEq(navigateCalls[0] && navigateCalls[0].url, '/pages/journal/journal', 'D1 沉淀跳转 pages/journal/journal');
  }

  // ---- E. formatDateText（模块级导出，经页面 data 验证） ----
  {
    const inst = freshInstance();
    inst.data.card = MOCK_CARD;
    inst.onSharePoster();
    await sleep(180);
    assertEq(inst.data.posterData.dateText, '2026年8月11日 · 晚安', 'E1 标准日期');
  }
  {
    const inst = freshInstance();
    inst.data.card = { ...MOCK_CARD, date: '2026-1-2' };
    inst.onSharePoster();
    await sleep(180);
    assertEq(inst.data.posterData.dateText, '2026年1月2日 · 晚安', 'E2 个位月/日');
  }
  {
    const inst = freshInstance();
    inst.data.card = { ...MOCK_CARD, date: 'bad-date' };
    inst.onSharePoster();
    await sleep(180);
    assertEq(inst.data.posterData.dateText, 'bad-date', 'E3 非法日期原样透传');
  }

  // ---- F. onShareAppMessage ----
  {
    const inst = freshInstance();
    const msg = inst.onShareAppMessage();
    assertEq(msg.path, '/pages/moon-card/moon-card', 'F1 分享路径=月光卡');
  }

  // ============================================================
  console.log(`\n结果: ${passed} passed, ${failed} failed`);
  if (failed > 0) {
    console.error('失败项:');
    failures.forEach((f) => console.error('  - ' + f));
    process.exit(1);
  }
}

run().catch((e) => { console.error('测试框架异常:', e); process.exit(1); });
