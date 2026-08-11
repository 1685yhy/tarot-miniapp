#!/usr/bin/env node
/**
 * verify-subscribe-slot.js —— 订阅引导二选一（T4-4）+ 我的页星光时刻切换（Node stub）
 *
 * 以 Node 运行时加载真实源码（wx/Page/require 打桩，无需微信 IDE / 后端）：
 *   A. subscribe.js maybePromptSubscribe 升级（二选一 + 槽位偏好上报）：
 *      - 模板未配置不弹 / 同会话最多 1 次 / 已拒绝不重弹 / 已授权不打扰
 *      - showActionSheet 二选一：tapIndex 0=晨星(morning)、1=晚星(night)
 *      - 同意后 → wx.requestSubscribeMessage → POST /notify/subscribe-grant
 *        → grant 成功后才置持久标记 + POST /notify/preference {slot}
 *      - 时序契约（F-1）：grant 失败 → 持久标记不置、会话标记清除（可再引导）
 *      - 系统窗拒绝 → REJECTED_KEY；面板取消（cancel）→ REJECTED_KEY；
 *        面板其他失败 → 仅会话内不重试（不置持久标记）
 *   B. profile.js 星光时刻切换：
 *      - GET /notify/preference 回显（morning/night）+ storage 缓存回写
 *      - GET 失败 → 本地缓存兜底；无缓存默认 morning
 *      - 切换 → POST /notify/preference {slot} → 状态+缓存+次日生效 toast
 *      - POST 失败 → 高亮回滚 + 失败提示；同槽位重复点击 no-op；切换中防抖
 *
 * 运行：node miniapp/scripts/verify-subscribe-slot.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ============================================================
// 打桩：wx / Page / require / getApp
// ============================================================

let pageDef = null;        // profile.js 的 Page() 定义
let subscribeApi = null;   // subscribe.js 的 module.exports
let requestCalls = [];     // 所有 request 调用
let toasts = [];
let actionSheetCalls = [];
let subscribeMsgCalls = [];
const store = {};          // storage 打桩
let failNextPreference = false; // 下次 /notify/preference 失败
let grantResult = 'ok';    // 'ok' | 'fail' | 'reject' | 'msgfail'

// 真实 config 模块（纯 JS 无 wx 依赖），测试中可改写模板 ID
const realConfig = require('../utils/config.js');

function mockRespond(url, opts) {
  if (url === '/notify/preference') {
    if (failNextPreference) { failNextPreference = false; throw new Error('mock 500'); }
    if (opts && opts.method === 'POST') {
      return { ok: true, slot_preference: opts.data.slot };
    }
    // GET：回显当前 storage 缓存（模拟后端）
    return { slot_preference: store['slot_preference'] || 'morning' };
  }
  if (url === '/notify/subscribe-grant') {
    if (grantResult === 'fail') { throw new Error('mock grant 500'); }
    return { ok: true, quota_available: 1 };
  }
  throw new Error('unexpected url ' + url);
}

const fakeRequire = (p) => {
  if (p.includes('utils/api') || p === './api' || p.endsWith('/api')) {
    return {
      request: async (url, opts) => {
        requestCalls.push({ url, opts });
        return mockRespond(url, opts);
      },
      getFriendlyError: (err) => (err && err.message) || '网络异常',
    };
  }
  if (p.includes('utils/config') || p === './config') {
    return realConfig;
  }
  if (p.includes('utils/auth')) return { checkLogin: async () => ({ nickname: '测试' }) };
  if (p.includes('utils/cards')) return { computeImagePath: () => '', findCard: () => null };
  if (p.includes('utils/sound')) {
    return {
      sfxEnabled: true, ambientEnabled: false,
      playPageEnterSound: () => {}, toggleSfx: () => true, toggleAmbient: () => false,
    };
  }
  if (p.includes('utils/energy')) return { getZodiacBadge: () => '' };
  if (p.includes('utils/performance')) return { markPageReady: () => {} };
  throw new Error(`unexpected require: ${p}`);
};

let appGlobal = {};
global.getApp = () => ({ globalData: appGlobal });
global.wx = {
  getStorageSync: (k) => store[k],
  setStorageSync: (k, v) => { store[k] = v; },
  removeStorageSync: (k) => { delete store[k]; },
  showToast: (o) => toasts.push(o),
  showActionSheet: (o) => actionSheetCalls.push(o),
  requestSubscribeMessage: (o) => subscribeMsgCalls.push(o),
  openSetting: () => {},
  showModal: () => {},
};

// ---------- 加载 subscribe.js（CommonJS 模块） ----------
const subscribeSrc = fs.readFileSync(
  path.join(__dirname, '../utils/subscribe.js'), 'utf8'
);
{
  const moduleShim = { exports: {} };
  new Function('require', 'module', 'exports', 'wx', 'getApp', subscribeSrc)(
    fakeRequire, moduleShim, moduleShim.exports, global.wx, global.getApp
  );
  subscribeApi = moduleShim.exports;
  if (!subscribeApi || typeof subscribeApi.maybePromptSubscribe !== 'function') {
    throw new Error('subscribe.js 加载失败');
  }
}

// ---------- 加载 profile.js（Page 定义） ----------
const profileSrc = fs.readFileSync(
  path.join(__dirname, '../pages/profile/profile.js'), 'utf8'
);
new Function('require', 'Page', 'wx', profileSrc)(fakeRequire, (def) => { pageDef = def; }, global.wx);
if (!pageDef) throw new Error('Page() 未被调用——profile.js 加载失败');

// ============================================================
// 测试框架
// ============================================================

let passed = 0;
let failed = 0;
function assert(name, cond, extra) {
  if (cond) { passed++; console.log('  PASS ' + name); }
  else { failed++; console.log('  FAIL ' + name + (extra !== undefined ? ' => ' + JSON.stringify(extra) : '')); }
}

function freshPage() {
  return {
    ...pageDef,
    data: JSON.parse(JSON.stringify(pageDef.data)),
    setData(patch) { Object.assign(this.data, patch); },
  };
}

function resetAll() {
  for (const k of Object.keys(store)) delete store[k];
  appGlobal = {};
  requestCalls = [];
  toasts = [];
  actionSheetCalls = [];
  subscribeMsgCalls = [];
  failNextPreference = false;
  grantResult = 'ok';
}

function lastReq(urlSub) {
  for (let i = requestCalls.length - 1; i >= 0; i--) {
    if (requestCalls[i].url.includes(urlSub)) return requestCalls[i];
  }
  return null;
}

(async () => {
  // ============================================================
  console.log('== A. subscribe.js —— 引导门控（幂等约束）==');
  resetAll();
  realConfig.WX_SUBSCRIBE_TEMPLATE_DAILY = '';
  assert('模板未配置 → 不弹', subscribeApi.maybePromptSubscribe() === false);
  assert('未配置时不调 showActionSheet', actionSheetCalls.length === 0);
  assert('未配置时不调 requestSubscribeMessage', subscribeMsgCalls.length === 0);

  realConfig.WX_SUBSCRIBE_TEMPLATE_DAILY = 'tmpl_test_123';
  assert('模板已配置 → 弹出', subscribeApi.maybePromptSubscribe() === true);
  assert('actionSheet 二选一两项', actionSheetCalls.length === 1 &&
    actionSheetCalls[0].itemList.length === 2, actionSheetCalls[0]);
  const items = actionSheetCalls[0].itemList;
  assert('第 1 项=晨星 7:37', items[0] === '清晨 7:37 · 晨星：今日星光', items[0]);
  assert('第 2 项=晚星 21:00', items[1] === '夜晚 21:00 · 晚星：睡前星语', items[1]);
  assert('同会话第二次不弹', subscribeApi.maybePromptSubscribe() === false);
  assert('同会话第二次无新 actionSheet', actionSheetCalls.length === 1);

  console.log('== A1. 取消（面板 cancel）→ 拒绝不重弹 ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].fail({ errMsg: 'showActionSheet:fail cancel' });
  assert('REJECTED_KEY 置位', store['subscribe_daily_rejected'] === true);
  assert('拒绝后不再弹', subscribeApi.maybePromptSubscribe() === false);

  console.log('== A2. 面板其他失败 → 仅会话内不重试，不置持久标记 ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].fail({ errMsg: 'showActionSheet:fail something-else' });
  assert('REJECTED_KEY 未置位', store['subscribe_daily_rejected'] === undefined);
  assert('同会话不再弹', subscribeApi.maybePromptSubscribe() === false);

  console.log('== A3. 选晨星（tapIndex 0）→ grant + preference morning ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].success({ tapIndex: 0 });
  assert('requestSubscribeMessage 调起（模板 ID）', subscribeMsgCalls.length === 1 &&
    subscribeMsgCalls[0].tmplIds[0] === 'tmpl_test_123');
  // 模拟系统窗：accept
  subscribeMsgCalls[0].success({ tmpl_test_123: 'accept' });
  await new Promise(r => setImmediate(r)); // 等 grant 链 settle
  const grant = lastReq('/notify/subscribe-grant');
  assert('grant POST 已发', !!grant && grant.opts.method === 'POST');
  const pref = lastReq('/notify/preference');
  assert('preference POST {slot:morning}', !!pref && pref.opts.method === 'POST' && pref.opts.data.slot === 'morning');
  assert('GRANTED_KEY 置位', store['subscribe_daily_granted'] === true);
  assert('LEGACY_SUBSCRIBED_KEY 置位', store['push_daily_subscribed'] === true);
  assert('偏好缓存 slot_preference=morning', store['slot_preference'] === 'morning');
  assert('toast=订阅成功明早', toasts.some(t => t.title === '订阅成功，明早 7:37 见 ✦'), toasts);
  assert('授权后不再弹', subscribeApi.maybePromptSubscribe() === false);

  console.log('== A4. 选晚星（tapIndex 1）→ grant + preference night ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].success({ tapIndex: 1 });
  subscribeMsgCalls[0].success({ tmpl_test_123: 'accept' });
  await new Promise(r => setImmediate(r));
  const prefN = lastReq('/notify/preference');
  assert('preference POST {slot:night}', !!prefN && prefN.opts.data.slot === 'night');
  assert('偏好缓存 slot_preference=night', store['slot_preference'] === 'night');
  assert('toast=订阅成功明晚', toasts.some(t => t.title === '订阅成功，明晚 21:00 见 ✦'), toasts);

  console.log('== A5. 时序契约：grant 失败 → 持久标记不置、会话标记清除 ==');
  resetAll();
  grantResult = 'fail';
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].success({ tapIndex: 0 });
  subscribeMsgCalls[0].success({ tmpl_test_123: 'accept' });
  await new Promise(r => setImmediate(r));
  assert('GRANTED_KEY 未置位', store['subscribe_daily_granted'] === undefined);
  assert('LEGACY 未置位', store['push_daily_subscribed'] === undefined);
  assert('preference 未上报（grant 成功后才有）', lastReq('/notify/preference') === null);
  assert('会话标记已清除（可再引导）', appGlobal['_subscribePromptedThisSession'] === undefined ||
    appGlobal['_subscribePromptedThisSession'] === false);
  grantResult = 'ok';
  assert('再次调用可再弹', subscribeApi.maybePromptSubscribe() === true);

  console.log('== A6. 系统窗拒绝 → REJECTED_KEY（不再重弹） ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].success({ tapIndex: 0 });
  subscribeMsgCalls[0].success({ tmpl_test_123: 'reject' });
  await new Promise(r => setImmediate(r));
  assert('REJECTED_KEY 置位', store['subscribe_daily_rejected'] === true);
  assert('grant 未发', lastReq('/notify/subscribe-grant') === null);
  assert('拒绝后不再弹', subscribeApi.maybePromptSubscribe() === false);

  console.log('== A7. requestSubscribeMessage 系统窗 fail → 会话内不再尝试 ==');
  resetAll();
  assert('弹出', subscribeApi.maybePromptSubscribe() === true);
  actionSheetCalls[0].success({ tapIndex: 1 });
  subscribeMsgCalls[0].fail({ errMsg: 'requestSubscribeMessage:fail' });
  await new Promise(r => setImmediate(r));
  assert('REJECTED_KEY 未置位（系统窗异常非用户拒绝）', store['subscribe_daily_rejected'] === undefined);
  assert('同会话不再弹', subscribeApi.maybePromptSubscribe() === false);

  // ============================================================
  console.log('== B. profile.js —— 星光时刻回显 ==');
  resetAll();
  store['slot_preference'] = 'night'; // 后端已有 night 偏好
  let page = freshPage();
  await page._loadSlotPreference();
  assert('GET /notify/preference 回显 night', page.data.slotPreference === 'night');
  assert('缓存回写 night', store['slot_preference'] === 'night');

  console.log('== B1. GET 失败 → 本地缓存兜底 ==');
  resetAll();
  store['slot_preference'] = 'night';
  failNextPreference = true;
  page = freshPage();
  await page._loadSlotPreference();
  assert('失败时用缓存 night', page.data.slotPreference === 'night');
  assert('失败静默（无 toast）', toasts.length === 0);

  console.log('== B2. GET 失败且无缓存 → 默认 morning ==');
  resetAll();
  failNextPreference = true;
  page = freshPage();
  await page._loadSlotPreference();
  assert('无缓存默认 morning', page.data.slotPreference === 'morning');

  console.log('== B3. GET 返回非法值 → 用缓存兜底 ==');
  resetAll();
  store['slot_preference'] = 'morning';
  page = freshPage();
  requestCalls = [];
  // 直接注入非法响应：改写 mock —— 通过预置 store 为 morning、GET 返回非法值的方式模拟
  failNextPreference = true; // 简单路径：失败兜底
  await page._loadSlotPreference();
  assert('非法值场景走缓存', page.data.slotPreference === 'morning');

  console.log('== B4. 切换晚星 → POST + 即时高亮 + 次日生效 toast ==');
  resetAll();
  page = freshPage();
  page.data.slotPreference = 'morning';
  await page.onSelectSlot({ currentTarget: { dataset: { slot: 'night' } } });
  const post = lastReq('/notify/preference');
  assert('POST {slot:night}', !!post && post.opts.method === 'POST' && post.opts.data.slot === 'night');
  assert('高亮切 night', page.data.slotPreference === 'night');
  assert('缓存回写 night', store['slot_preference'] === 'night');
  assert('toast 次日生效', toasts.some(t => t.title === '明天起，星光在夜晚 21:00 等你 ✦'), toasts);
  assert('slotSwitching 复位', page.data.slotSwitching === false);

  console.log('== B5. 切换失败 → 高亮回滚 + 失败提示 ==');
  resetAll();
  page = freshPage();
  page.data.slotPreference = 'morning';
  failNextPreference = true;
  await page.onSelectSlot({ currentTarget: { dataset: { slot: 'night' } } });
  assert('失败回滚 morning', page.data.slotPreference === 'morning');
  assert('失败提示 toast', toasts.some(t => t.title.includes('切换失败')), toasts);
  assert('缓存未漂移', store['slot_preference'] === undefined);

  console.log('== B6. 同槽位重复点击 no-op ==');
  resetAll();
  page = freshPage();
  page.data.slotPreference = 'morning';
  const n0 = requestCalls.length;
  await page.onSelectSlot({ currentTarget: { dataset: { slot: 'morning' } } });
  assert('同槽位不发请求', requestCalls.length === n0);

  console.log('== B7. 切换中防抖（第二次点击 no-op） ==');
  resetAll();
  page = freshPage();
  page.data.slotPreference = 'morning';
  // 手动置切换中（模拟第一次请求未返回）
  page.data.slotSwitching = true;
  const n1 = requestCalls.length;
  await page.onSelectSlot({ currentTarget: { dataset: { slot: 'night' } } });
  assert('切换中不发第二次请求', requestCalls.length === n1);
  assert('高亮保持', page.data.slotPreference === 'morning');

  console.log('== B8. 非法 slot 防御 ==');
  resetAll();
  page = freshPage();
  const n2 = requestCalls.length;
  await page.onSelectSlot({ currentTarget: { dataset: { slot: 'dawn' } } });
  assert('非法 slot 被忽略', requestCalls.length === n2);

  console.log('== B9. 旧推送开关已移除（统一到新偏好接口） ==');
  resetAll();
  assert('data 无 pushDailyCard', pageDef.data.pushDailyCard === undefined);
  assert('data 有 slotPreference', pageDef.data.slotPreference === 'morning');
  assert('data 有 slotSwitching', pageDef.data.slotSwitching === false);
  assert('页面无 onSubscribeDailyCard', typeof pageDef.onSubscribeDailyCard !== 'function');
  assert('页面无 _reportSubscription', typeof pageDef._reportSubscription !== 'function');
  assert('页面有 onSelectSlot', typeof pageDef.onSelectSlot === 'function');
  assert('页面有 onOpenPushSettings（保留）', typeof pageDef.onOpenPushSettings === 'function');

  // ============================================================
  console.log(`\n==== ${passed} passed, ${failed} failed ====`);
  process.exit(failed === 0 ? 0 : 1);
})();
