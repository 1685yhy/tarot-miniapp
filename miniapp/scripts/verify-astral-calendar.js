#!/usr/bin/env node
/**
 * verify-astral-calendar.js —— 星空时刻表页（astral-calendar）逻辑测试（Node stub）
 *
 * 以 Node 运行时加载页面真实源码（wx/Page/require 打桩），覆盖：
 *   A. _buildEventList 事件列表聚合回归（T3-4 逻辑测试关键路径保留）
 *   B. _prepareNextEvent 倒计时/日期防御（含 NaN 修复：days_until 缺失/非数字 → 「即将到来」）
 *   C. 请求序号守卫（T3-4 审查 Important 修复）：快速切月/静默刷新竞态——过期响应（成功/失败）
 *      一律丢弃，不覆盖最新月份数据
 *   D. 静默失败内联提示（T3-4 审查 Important 修复）：切月/onShow 失败 → silentError + 重试；
 *      onMonthChange 清空上月经数据，避免旧数据/空态文案错配
 *
 * 运行：node miniapp/scripts/verify-astral-calendar.js（无需微信 IDE / 后端）
 */
'use strict';

const fs = require('fs');
const path = require('path');

// ============================================================
// 打桩：wx / Page / require
// ============================================================

let pageDef = null;
let requestImpl = null; // 可替换的 request 实现（竞态测试用受控 Promise）
let analyticsCalls = [];

const fakeRequire = (p) => {
  if (p.includes('utils/api')) {
    return {
      request: (...args) => requestImpl(...args),
      getFriendlyError: (err) => (err && err.message) || String(err),
    };
  }
  if (p.includes('utils/analytics')) {
    return { trackEvent: (name, data) => analyticsCalls.push({ name, data }) };
  }
  throw new Error(`unexpected require: ${p}`);
};

global.wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
};

const SRC = fs.readFileSync(
  path.join(__dirname, '../pages/astral-calendar/astral-calendar.js'),
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

/** 构造页面实例：data 深拷贝 + setData 合并 + 方法绑定 */
function makePage() {
  const inst = { data: JSON.parse(JSON.stringify(pageDef.data)) };
  inst.setData = function (patch) {
    Object.assign(this.data, patch);
  };
  Object.keys(pageDef).forEach((k) => {
    if (typeof pageDef[k] === 'function') inst[k] = pageDef[k].bind(inst);
  });
  // 页面实例字段（Page 定义外的运行时状态）
  inst._calendarReqId = 0;
  inst._loadedOnce = false;
  return inst;
}

/** 受控 Promise（竞态测试）：resolve/reject 由测试代码择时触发 */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ============================================================
// 测试数据构造
// ============================================================

const pad = (n) => (n < 10 ? `0${n}` : `${n}`);

/** 生成某月全部日期（days 数组，可带 phase），eventsByDate: { 'YYYY-MM-DD': [{type,label}] } */
function mkMonthDays(year, month, eventsByDate) {
  const daysInMonth = new Date(year, month, 0).getDate();
  const out = [];
  for (let d = 1; d <= daysInMonth; d++) {
    const date = `${year}-${pad(month)}-${pad(d)}`;
    out.push({
      date,
      phase: { emoji: '🌘', label: '残月' },
      events: (eventsByDate && eventsByDate[date]) || [],
    });
  }
  return out;
}

/** 区间事件逐日展开（后端月视图口径：区间事件每天一行） */
function mkRange(year, month, startDay, endDay, ev) {
  const map = {};
  for (let d = startDay; d <= endDay; d++) {
    map[`${year}-${pad(month)}-${pad(d)}`] = [ev];
  }
  return map;
}

/** 月历接口响应：{days, next_event} */
function mkPayload(year, month, eventsByDate, nextEvent) {
  return {
    days: mkMonthDays(year, month, eventsByDate),
    next_event: nextEvent || null,
  };
}

// ============================================================
// A. _buildEventList 聚合回归（T3-4 关键路径）
// ============================================================

function testBuildEventList() {
  const p = makePage();
  p.data.year = 2026;
  p.data.month = 8;

  // A1. 8 月：立秋 8.8 / 新月+日食同日 8.12（两行）/ 处暑 8.23（solar_term 非连续各自成组）
  const augEvents = {
    '2026-08-08': [{ type: 'solar_term', label: '立秋' }],
    '2026-08-12': [
      { type: 'new_moon', label: '狮子座新月' },
      { type: 'solar_eclipse', label: '狮子座日全食' },
    ],
    '2026-08-23': [{ type: 'solar_term', label: '处暑' }],
  };
  const aug = p._buildEventList(mkMonthDays(2026, 8, augEvents));
  assertEq(aug.length, 4, 'A1 8月事件行数=4');
  assertEq(aug.map((r) => r.label), ['立秋', '狮子座新月', '狮子座日全食', '处暑'], 'A1 8月行序与标签');
  assertEq(aug[1].dateText, '8.12', 'A1 新月单日文本');
  assertEq(aug[1].isRange, false, 'A1 新月非区间');

  // A2. 9 月：水逆 9.18 起跨月（逐日展开）→ 区间止于月末「9.18 – 9.30…」
  p.data.year = 2026; p.data.month = 9;
  const sep = p._buildEventList(mkMonthDays(
    2026, 9,
    mkRange(2026, 9, 18, 30, { type: 'mercury_retrograde', label: '水星逆行' })
  ));
  assertEq(sep.length, 1, 'A2 9月水逆合并为 1 行');
  assertEq(sep[0].dateText, '9.18 – 9.30…', 'A2 区间跨月界后缀 …');
  assertEq(sep[0].isRange, true, 'A2 水逆为区间');

  // A3. 10 月：区间起于月初（跨月延续）→ 「…10.1 – 10.10」
  p.data.year = 2026; p.data.month = 10;
  const oct = p._buildEventList(mkMonthDays(
    2026, 10,
    mkRange(2026, 10, 1, 10, { type: 'mercury_retrograde', label: '水星逆行' })
  ));
  assertEq(oct.length, 1, 'A3 10月水逆合并为 1 行');
  assertEq(oct[0].dateText, '…10.1 – 10.10', 'A3 区间跨月界前缀 …');

  // A4. 区间同时起于月初止于月末（2 月金星逆行整月）→ 双侧 … 标记
  p.data.year = 2026; p.data.month = 2;
  const feb = p._buildEventList(mkMonthDays(
    2026, 2,
    mkRange(2026, 2, 1, 28, { type: 'venus_retrograde', label: '金星逆行' })
  ));
  assertEq(feb[0].dateText, '…2.1 – 2.28…', 'A4 整月区间双侧 … 标记');

  // A5. 空月 → 空数组
  p.data.year = 2026; p.data.month = 7;
  const empty = p._buildEventList(mkMonthDays(2026, 7, {}));
  assertEq(empty, [], 'A5 空月返回空数组');
}

// ============================================================
// B. _prepareNextEvent 倒计时/日期防御（NaN 修复）
// ============================================================

function testPrepareNextEvent() {
  const p = makePage();

  // B1. 常规三态：0=今夜 / 1=明天 / N天后
  let ne = p._prepareNextEvent({ type: 'new_moon', label: '狮子座新月', date: '2026-08-12', days_until: 0 });
  assertEq(ne.countdownText, '今夜', 'B1 days_until=0 → 今夜');
  assertEq(ne.dateLabel, '8月12日 · 周三', 'B1 日期星期标签');
  assertEq(ne.emoji, '🌑', 'B1 类型符号映射');

  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12', days_until: 1 });
  assertEq(ne.countdownText, '明天', 'B2 days_until=1 → 明天');

  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12', days_until: 5 });
  assertEq(ne.countdownText, '5 天后', 'B3 days_until=5 → 5 天后');

  // B4. 数字字符串正常解析
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12', days_until: '2' });
  assertEq(ne.countdownText, '2 天后', 'B4 数字字符串 → 2 天后');

  // B5. NaN 防御：days_until 缺失（undefined）→ 不出现 "NaN 天后"
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12' });
  assertEq(ne.countdownText, '即将到来', 'B5 days_until 缺失 → 即将到来');
  assertEq(ne.days_until, null, 'B5 days_until 回退为 null');

  // B6. NaN 防御：days_until = null → 不得误判为 0（"今夜"）
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12', days_until: null });
  assertEq(ne.countdownText, '即将到来', 'B6 days_until=null → 即将到来（非 今夜）');

  // B7. NaN 防御：非数字字符串
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-08-12', days_until: 'abc' });
  assertEq(ne.countdownText, '即将到来', 'B7 days_until=abc → 即将到来');

  // B8. 边界：next 为 null / 无 date → 返回 null（倒计时卡隐藏）
  assertEq(p._prepareNextEvent(null), null, 'B8 next=null → null');
  assertEq(p._prepareNextEvent({ type: 'new_moon', label: 'x', days_until: 1 }), null, 'B8 无 date → null');

  // B9. 非法日期防御：NaN 段/2月30日 → 不出现 "NaN月NaN日 · undefined"，回退原始串
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-13-99', days_until: 1 });
  assertEq(ne.dateLabel, '2026-13-99', 'B9 非法日期回退原始串');
  ne = p._prepareNextEvent({ type: 'new_moon', label: 'x', date: '2026-02-30', days_until: 1 });
  assertEq(ne.dateLabel, '2026-02-30', 'B9 2月30日回退原始串');
}

// ============================================================
// C. 请求序号守卫（竞态：过期响应丢弃）
// ============================================================

async function testRaceGuard() {
  // C1. 快速切月：旧月份响应后到 → 不覆盖新月份数据
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    const d1 = deferred();
    const d2 = deferred();
    let n = 0;
    requestImpl = () => (++n === 1 ? d1.promise : d2.promise);
    const augPayload = mkPayload(2026, 8, { '2026-08-12': [{ type: 'new_moon', label: '狮子座新月' }] });
    const sepPayload = mkPayload(2026, 9, { '2026-09-19': [{ type: 'solar_term', label: '秋分' }] });

    const p1 = p._loadCalendar(true); // 8 月请求（reqId 1）
    p.data.year = 2026; p.data.month = 9;
    const p2 = p._loadCalendar(true); // 9 月请求（reqId 2，最新）

    d2.resolve(sepPayload); // 9 月先到
    await p2;
    assertEq(p.data.calDays.length, 30, 'C1 9月数据先到 → 30 天渲染');
    assertEq(p.data.eventList[0].label, '秋分', 'C1 9月事件生效');

    d1.resolve(augPayload); // 8 月响应迟到 → 必须被丢弃
    await p1;
    assertEq(p.data.calDays.length, 30, 'C1 迟到 8 月响应被丢弃（天数仍为 9 月）');
    assertEq(p.data.eventList[0].label, '秋分', 'C1 迟到 8 月响应被丢弃（事件仍为 9 月）');
  }

  // C2. 切月中 onShow 静默刷新：新请求生效后，旧请求成功响应不得回滚数据
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    p._loadedOnce = true; // onShow 进入静默刷新分支
    const d1 = deferred();
    const d2 = deferred();
    let n = 0;
    requestImpl = () => (++n === 1 ? d1.promise : d2.promise);
    const augPayload = mkPayload(2026, 8, { '2026-08-08': [{ type: 'solar_term', label: '立秋' }] });
    const sepPayload = mkPayload(2026, 9, { '2026-09-19': [{ type: 'solar_term', label: '秋分' }] });

    p.onShow(); // onShow 静默刷新 8 月（reqId 1）
    p.data.year = 2026; p.data.month = 9;
    p.onMonthChange({ detail: { year: 2026, month: 9 } }); // 用户切月（reqId 2）

    d2.resolve(sepPayload); // 切月请求先落地
    await d2.promise;
    assertEq(p.data.calDays.length, 30, 'C2 切月数据生效（9 月 30 天）');

    d1.resolve(augPayload); // onShow 旧响应迟到 → 丢弃，不得回滚为 8 月
    await d1.promise;
    assert(p.data.month === 9, 'C2 月份保持最新（9 月）');
    assertEq(p.data.calDays.length, 30, 'C2 数据仍为 9 月（旧响应未回滚）');
    assertEq(p.data.eventList[0].label, '秋分', 'C2 事件仍为 9 月秋分');
  }

  // C3. 过期失败响应丢弃：旧请求失败不覆盖新请求结果 / 不产生误导性 silentError
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    const d1 = deferred();
    const d2 = deferred();
    let n = 0;
    requestImpl = () => (++n === 1 ? d1.promise : d2.promise);

    const p1 = p._loadCalendar(true); // reqId 1
    p.data.year = 2026; p.data.month = 10;
    const p2 = p._loadCalendar(true); // reqId 2

    d2.reject(new Error('最新请求失败'));
    await p2;
    assertEq(p.data.silentError, '最新请求失败', 'C3 最新请求失败 → silentError 提示');

    d1.reject(new Error('过期请求失败')); // 旧失败响应迟到
    await p1;
    assertEq(p.data.silentError, '最新请求失败', 'C3 过期失败响应被丢弃（提示未被覆盖）');
  }
}

// ============================================================
// D. 静默失败提示 + onMonthChange 清理 + 重试
// ============================================================

async function testSilentFailure() {
  // D1. 静默失败 → silentError 内联提示（loading 不闪、error 不动），与全屏错误态区分
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    p.data.loading = false; // 模拟页面已加载完成
    requestImpl = () => Promise.reject(new Error('网络异常'));
    await p._loadCalendar(true);
    assertEq(p.data.silentError, '网络异常', 'D1 静默失败 → silentError');
    assertEq(p.data.loading, false, 'D1 静默路径不动 loading');
    assertEq(p.data.error, null, 'D1 静默失败不进全屏错误态');
  }

  // D2. 非静默失败（onLoad/重试）→ 全屏错误态（既有行为回归）
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    requestImpl = () => Promise.reject(new Error('网络异常'));
    await p._loadCalendar(false);
    assertEq(p.data.error, '网络异常', 'D2 非静默失败 → 全屏错误态');
    assertEq(p.data.loading, false, 'D2 失败后 loading 关闭');
    assertEq(p.data.silentError, '', 'D2 非静默路径不置 silentError');
  }

  // D3. 成功响应清除 silentError（含静默成功路径）
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    requestImpl = () => Promise.resolve(mkPayload(2026, 8, {}));
    p.data.silentError = '旧的失败提示';
    await p._loadCalendar(true);
    assertEq(p.data.silentError, '', 'D3 静默成功 → silentError 清除');
  }

  // D4. onMonthChange：更新年月 + 清空上月经数据 + 触发新月份请求（URL 带新月份）；
  //     切月失败 → silentError（不误报"本月无事件"空态）
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    p.data.calDays = mkMonthDays(2026, 8, { '2026-08-08': [{ type: 'solar_term', label: '立秋' }] });
    p.data.eventList = [{ label: '立秋' }];
    p.data.hasMonthEvents = true;
    p.data.hasNoEvents = false;
    p.data.nextEvent = { label: 'x' };
    p.data.silentError = '旧的提示';

    const urls = [];
    requestImpl = (url) => {
      urls.push(url);
      return Promise.reject(new Error('本月加载失败'));
    };
    p.onMonthChange({ detail: { year: 2026, month: 9 } });
    assertEq(p.data.year, 2026, 'D4 year 更新');
    assertEq(p.data.month, 9, 'D4 month 更新');
    assertEq(p.data.calDays, [], 'D4 上月经数据已清空（不发旧月内容）');
    assertEq(p.data.eventList, [], 'D4 上月经事件列表已清空');
    assertEq(p.data.hasMonthEvents, false, 'D4 hasMonthEvents 复位');
    assertEq(p.data.hasNoEvents, false, 'D4 hasNoEvents 复位（空态文案不误报）');
    assertEq(p.data.nextEvent, null, 'D4 nextEvent 清空');
    assertEq(p.data.silentError, '', 'D4 silentError 先清空（结果再定）');
    assert(urls.length === 1 && urls[0].includes('month=9'), `D4 新月份请求已发出（${urls[0]}）`);
    await sleep(10); // 等失败落地
    assertEq(p.data.silentError, '本月加载失败', 'D4 切月失败 → silentError 提示可重试');
    assertEq(p.data.hasNoEvents, false, 'D4 失败态不展示"本月无事件"空态');
  }

  // D5. onRetry：清 silentError → 走完整加载 → 成功后恢复数据
  {
    const p = makePage();
    p.data.year = 2026;
    p.data.month = 8;
    p.data.silentError = '旧的提示';
    p.data.error = '旧的错误';
    p.data.loading = false;
    requestImpl = () => Promise.resolve(mkPayload(2026, 8, { '2026-08-12': [{ type: 'new_moon', label: '狮子座新月' }] }));
    p.onRetry();
    assertEq(p.data.loading, true, 'D5 重试进入加载');
    assertEq(p.data.error, null, 'D5 重试清错误态');
    assertEq(p.data.silentError, '', 'D5 重试清内联提示');
    await sleep(10);
    assertEq(p.data.loading, false, 'D5 重试成功后 loading 关闭');
    assertEq(p.data.silentError, '', 'D5 重试成功后提示保持为空');
    assertEq(p.data.eventList.length, 1, 'D5 重试成功后数据恢复');
  }
}

// ============================================================
// 主流程
// ============================================================

(async () => {
  const started = Date.now();
  console.log('▶ 星空时刻表页逻辑测试（Node stub 加载真实页面源码）\n');

  console.log('— A. _buildEventList 聚合回归 —');
  testBuildEventList();
  console.log(`  → 小计 ${passed} passed / ${failed} failed`);

  console.log('— B. _prepareNextEvent 倒计时/日期防御（NaN 修复） —');
  testPrepareNextEvent();
  console.log(`  → 小计 ${passed} passed / ${failed} failed`);

  console.log('— C. 请求序号守卫（竞态） —');
  await testRaceGuard();
  console.log(`  → 小计 ${passed} passed / ${failed} failed`);

  console.log('— D. 静默失败提示 + 切月清理 + 重试 —');
  await testSilentFailure();
  console.log(`  → 小计 ${passed} passed / ${failed} failed`);

  console.log(`\n总计：${passed} passed / ${failed} failed（${Date.now() - started}ms）`);
  if (failed > 0) {
    console.error('\n失败明细：');
    failures.forEach((f) => console.error(`  • ${f}`));
    process.exit(1);
  }
  console.log('✅ 全部通过');
})();
