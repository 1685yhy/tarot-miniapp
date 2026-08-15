// utils/nav-guard.js — 全站导航防抖守卫
// 修复：快速连点/双击导航入口时 wx.navigateTo 被调用两次 → 页面栈推入两份同页
//（返回需退两层）。此前多轮 review 均标记"全站无导航防抖模式"，本次统一收敛到本模块。
//
// 机制（互斥锁，选简单可靠方案，注释写明取舍）：
//  - guardTap(fn, ms)：handler 级锁。模块级 Map<fn, lastFireTime>，600ms 内
//    同一 handler 只放行第一次，其余直接丢弃。适合整体包一层即可的入口
//    （switchTab / 复杂 handler 无需逐行改）。
//  - navTo / redirectTo / switchTo：URL 级锁。模块级 Map<url, lastNavTime>，
//    600ms 内同一目标 URL 只发起一次跳转。适合把 handler 里裸的 wx.navigateTo
//    换成 navTo(url) 的最小 diff 替换（不动 handler 结构、不碰非导航逻辑）。
//  - 两种锁独立且互不干扰；锁仅存于模块内存，不落 storage，页面卸载后自动失效。
// 原则：只防"导航"；toggle/开关/弹窗/表单类 handler 一律不包。

const NAV_LOCK_MS = 600;

/** handler 级锁：fn -> 最近一次放行时间戳 */
const handlerLocks = new Map();
/** URL 级锁：url -> 最近一次跳转时间戳 */
const navLocks = new Map();

/**
 * 包装器：ms 内同一 handler 只放行第一次（防连点）。
 * 返回的函数作为页面方法被调用时 this/参数原样透传。
 */
function guardTap(fn, ms = NAV_LOCK_MS) {
  return function (...args) {
    const now = Date.now();
    if (now - (handlerLocks.get(fn) || 0) < ms) return;
    handlerLocks.set(fn, now);
    return fn.apply(this, args);
  };
}

/** 内部：对同一 URL 加锁后调用指定导航 API（锁命中直接丢弃本次调用） */
function guardedNav(api, url, opts, ms) {
  const now = Date.now();
  if (now - (navLocks.get(url) || 0) < ms) return;
  navLocks.set(url, now);
  return api(Object.assign({ url }, opts || {}));
}

/** wx.navigateTo 便捷包装（带 URL 级防抖锁） */
function navTo(url, opts, ms = NAV_LOCK_MS) {
  return guardedNav(wx.navigateTo, url, opts, ms);
}

/** wx.redirectTo 便捷包装（带 URL 级防抖锁） */
function redirectTo(url, opts, ms = NAV_LOCK_MS) {
  return guardedNav(wx.redirectTo, url, opts, ms);
}

/** wx.switchTab 便捷包装（带 URL 级防抖锁） */
function switchTo(url, opts, ms = NAV_LOCK_MS) {
  return guardedNav(wx.switchTab, url, opts, ms);
}

module.exports = { guardTap, navTo, redirectTo, switchTo };
