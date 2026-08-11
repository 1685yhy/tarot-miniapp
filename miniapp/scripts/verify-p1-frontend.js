/**
 * T5-1 四功能串联验证 · 前端静态校验（SDD P1 任务22 Step3/4 的静态部分）。
 *
 * 模拟器不可用时的前端验证替代：对以下链路做静态断言（失败即非零退出）：
 *  1. 全页面导航链路：所有页面 navigateTo/redirectTo/reLaunch/switchTab
 *     目标必须在 app.json（pages + subPackages）注册且文件存在；
 *  2. 入口统一（T5-1 Step3）：
 *     - index foot-entry 三入口（星光手账/星辰相遇/星空时刻表）齐备且 handler
 *       指向正确页面；
 *     - 今日星光卡「今晚的星已点亮」角标：index.js 读 GET /journal/calendar
 *       当月今日有记录 → journalLitToday → wxml sg-lit-badge 渲染；
 *     - profile 星阶区三数据：手账连续（journal calendar stats.current_streak）
 *       + 本月节点（/astral/activity/summary）+ 推送偏好（/notify/preference）；
 *  3. 分享裂变 scene 约定（设计五-3）：
 *     - 相遇海报：/share/wxa-code 用 page= 参数 + scene=m:{meet_id} +
 *       pages/meet-landing/meet-landing（T5-1 修复：历史 path= 已废弃）；
 *     - 手账海报 / 月光卡海报：复用 /share/wxacode（scene=邀请码 → card-landing）；
 *     - 分享中心/星盘老海报：/share/wxa-code 用 page= 参数（同类一并修）；
 *  4. 合规统一（设计五-5）：P1 新结果页/海报全部含「仅供娱乐 · 星光映照」。
 *
 * 用法：node miniapp/scripts/verify-p1-frontend.js
 */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
let failed = 0;

function fail(msg) {
  failed += 1;
  console.error('FAIL: ' + msg);
}

function ok(msg) {
  console.log('ok: ' + msg);
}

function read(p) {
  return fs.readFileSync(path.join(ROOT, p), 'utf8');
}

function exists(p) {
  return fs.existsSync(path.join(ROOT, p));
}

// ── 页面注册表（app.json）──────────────────────────────────────────────
const appJson = JSON.parse(read('app.json'));
const pagePaths = new Set(appJson.pages);
const navTargets = new Set();
for (const sub of appJson.subPackages || []) {
  for (const p of sub.pages) navTargets.add(sub.root + p);
  if (sub.root.endsWith('/')) {
    for (const p of sub.pages) pagePaths.add(sub.root + p);
  } else {
    for (const p of sub.pages) pagePaths.add(sub.root + '/' + p);
  }
}

// ── 1. 全页面导航链路：目标存在性 ─────────────────────────────────────
const NAV_RE = /(?:navigateTo|redirectTo|reLaunch|switchTab|preloadPages)\(\s*\{\s*url:\s*['"]([^'"?]+)/g;
let navCount = 0;
let chainCount = 0;
const pageFiles = [];
function walk(dir) {
  for (const f of fs.readdirSync(path.join(ROOT, dir))) {
    const full = path.join(dir, f);
    if (fs.statSync(path.join(ROOT, full)).isDirectory()) walk(full);
    else if (f.endsWith('.js') && !f.endsWith('.config.js')) pageFiles.push(full);
  }
}
walk('pages');

for (const file of pageFiles) {
  const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
  let m;
  NAV_RE.lastIndex = 0;
  while ((m = NAV_RE.exec(src)) !== null) {
    navCount += 1;
    const target = m[1].replace(/^\//, '');
    if (!pagePaths.has(target)) {
      fail(`${file} 导航目标不存在: ${m[1]}`);
    } else {
      chainCount += 1;
    }
  }
}
ok(`全页面导航链路：${navCount} 处跳转，${chainCount} 处目标存在（已注册页面 ${pagePaths.size} 个）`);

// ── 2a. index foot-entry 三入口 + 角标 ─────────────────────────────────
const idxJs = read('pages/index/index.js');
const idxWxml = read('pages/index/index.wxml');

const entryChecks = [
  ['星光手账', 'onGoDiary', '/pages/journal/journal'],
  ['星辰相遇', 'onGoMeet', '/pages/meet/meet'],
  ['星空时刻表', 'onGoAstralCalendar', '/pages/astral-calendar/astral-calendar'],
];
for (const [label, handler, target] of entryChecks) {
  const hasLabel = idxWxml.includes(`foot-entry-label">${label}`) ||
    idxWxml.includes(`>${label}</text>`);
  const hasHandler = idxWxml.includes(`bindtap="${handler}"`) && idxJs.includes(handler);
  const handlerTargets = idxJs.includes(target.replace(/^\//, '').replace(/\//g, '\\/'));
  if (!hasLabel || !hasHandler || !idxJs.includes(`'${target}'`)) {
    fail(`index 入口「${label}」不齐备（label=${hasLabel} handler=${hasHandler} target=${handlerTargets}）`);
  } else {
    ok(`index 入口「${label}」→ ${target}`);
  }
}

if (!idxJs.includes('_loadJournalBadge') || !idxJs.includes('/journal/calendar')) {
  fail('index 角标：缺 _loadJournalBadge / GET /journal/calendar 读取');
} else {
  ok('index 角标：_loadJournalBadge 读 GET /journal/calendar');
}
if (!idxJs.includes('journalLitToday')) fail('index 角标：缺 journalLitToday 状态');
if (!idxWxml.includes('sg-lit-badge') || !idxWxml.includes('今晚的星已点亮')) {
  fail('index 角标：wxml 缺 sg-lit-badge /「今晚的星已点亮」');
} else {
  ok('index 角标：wxml sg-lit-badge「今晚的星已点亮」渲染（journalLitToday 驱动）');
}

// ── 2b. profile 星阶区三数据 ───────────────────────────────────────────
const pfJs = read('pages/profile/profile.js');
const pfWxml = read('pages/profile/profile.wxml');
for (const [dataKey, api, desc] of [
  ['journalStreak', '/journal/calendar', '手账连续记录天数'],
  ['nodeCompleted', '/astral/activity/summary', '本月节点完成数'],
  ['slotPreference', '/notify/preference', '推送偏好回显'],
]) {
  if (!pfJs.includes(dataKey)) fail(`profile 星阶区缺 ${dataKey}（${desc}）`);
  if (!pfJs.includes(api)) fail(`profile 星阶区缺接口调用 ${api}（${desc}）`);
}
if (!pfWxml.includes('record-p1-row') || !pfWxml.includes('journalStreak') || !pfWxml.includes('nodeCompleted')) {
  fail('profile 星阶区 wxml 缺 record-p1-row / journalStreak / nodeCompleted');
} else {
  ok('profile 星阶区三数据：手账连续 + 本月节点 + 推送偏好（_loadSlotPreference 回显）');
}

// ── 3. 分享裂变 scene 约定 ─────────────────────────────────────────────
const meetPoster = read('utils/meet-poster.js');
if (!meetPoster.includes("/share/wxa-code?page='")) {
  fail('相遇海报：未用 page= 参数（T5-1 修复项：历史 path= 已废弃）');
} else {
  ok('相遇海报：/share/wxa-code 用 page= 参数');
}
if (!meetPoster.includes("'m:' + meetId") && !meetPoster.includes("'m:'+meetId")) {
  fail('相遇海报：缺 scene=m:{meet_id}');
} else {
  ok('相遇海报：scene=m:{meet_id}');
}
if (!meetPoster.includes('pages/meet-landing/meet-landing')) {
  fail('相遇海报：目标页非 meet-landing');
} else {
  ok('相遇海报：落地页 pages/meet-landing/meet-landing（扫码 → 公开页 → join）');
}
const journalPoster = read('utils/journal-poster.js');
const moonPoster = read('utils/moon-card-poster.js');
for (const [name, src] of [['手账海报', journalPoster], ['月光卡海报', moonPoster]]) {
  if (!src.includes('/share/wxacode')) fail(`${name}：未复用 /share/wxacode（名片码）`);
  else ok(`${name}：复用 /share/wxacode（scene=邀请码 → card-landing）`);
}
const canvasPoster = read('utils/canvas-poster.js');
if (canvasPoster.includes("?path='")) {
  fail('canvas-poster：仍有 path= 残留（同类一并修）');
} else if (canvasPoster.includes("?page='")) {
  ok('canvas-poster：分享中心/星盘海报已用 page= 参数（同类一并修）');
} else {
  fail('canvas-poster：未检测到 page= 参数');
}
const weeklyReportPoster = read('components/weekly-report-poster/weekly-report-poster.js');
if (weeklyReportPoster.includes("?path='")) {
  fail('weekly-report-poster：仍有 path= 残留（同类一并修）');
} else if (weeklyReportPoster.includes("?page='")) {
  ok('weekly-report-poster：周报海报已用 page= 参数（同类一并修）');
} else {
  fail('weekly-report-poster：未检测到 page= 参数');
}

// ── 4. 合规统一：新结果页/海报含「仅供娱乐 · 星光映照」─────────────────
const COMPLIANCE = '仅供娱乐 · 星光映照';
const p1Pages = [
  'pages/journal-review/journal-review',
  'pages/meet/meet',
  'pages/astral-event/astral-event',
  'pages/moon-card/moon-card',
  'pages/card-landing/card-landing',
  'pages/meet-landing/meet-landing',
];
for (const page of p1Pages) {
  const okCompliance =
    (exists(page + '.wxml') && read(page + '.wxml').includes(COMPLIANCE)) ||
    (exists(page + '.js') && read(page + '.js').includes(COMPLIANCE)) ||
    (exists(page + '.json') && read(page + '.json').includes(COMPLIANCE));
  if (!okCompliance) fail(`合规：${page} 缺「${COMPLIANCE}」`);
  else ok(`合规：${page} 含「${COMPLIANCE}」`);
}
for (const [name, src] of [['手账海报', journalPoster], ['月光卡海报', moonPoster], ['相遇海报', meetPoster]]) {
  if (!src.includes(COMPLIANCE)) fail(`合规：${name} 缺「${COMPLIANCE}」`);
  else ok(`合规：${name} 含「${COMPLIANCE}」`);
}

// ── 情感主线：月光卡 → 手账跳转 ───────────────────────────────────────
const moonJs = read('pages/moon-card/moon-card.js');
if (!moonJs.includes('/pages/journal/journal')) {
  fail('情感主线：月光卡缺「给今天记一颗星 → 手账」跳转');
} else {
  ok('情感主线：月光卡 → /pages/journal/journal（沉淀引导）');
}
const journalJs = read('pages/journal/journal.js');
if (!journalJs.includes('/pages/journal-review/journal-review')) {
  fail('情感主线：手账缺「月度复盘」跳转');
} else {
  ok('情感主线：手账 → 月度复盘页跳转存在');
}

// ── 汇总 ───────────────────────────────────────────────────────────────
if (failed > 0) {
  console.error(`\nRESULT: ${failed} 项失败`);
  process.exit(1);
}
console.log('\nRESULT: 全部通过（导航链路 + 入口统一 + 海报 scene + 合规 + 情感主线）');
