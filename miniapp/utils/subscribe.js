/**
 * 星光晨讯订阅引导（共享工具）
 * =========================================================
 * 三个触发点共用一个入口：
 *   - 抽牌结果页进入（reading-result）
 *   - 许愿成功（wish）
 *   - 每日一牌翻转后（daily-card）
 *
 * 行为约束（Task 6 / T4-4 简报）：
 *   - 模板未配置（config.WX_SUBSCRIBE_TEMPLATE_DAILY 为空）→ 不弹；
 *   - 用户拒绝 → 不再重弹（storage 持久标记）；
 *   - 同会话最多弹 1 次（wx.showActionSheet 每次调用都会弹系统面板，
 *     必须用全局标记限制——app.globalData 标记，页面销毁/重进不清除）；
 *   - T4-4 二选一：选「晨星 7:37」→ grant + POST /notify/preference {slot:"morning"}；
 *     选「晚星 21:00」→ grant + {slot:"night"}；面板取消 → 拒绝不重弹；
 *   - 同意 → wx.requestSubscribeMessage 成功后调 POST /notify/subscribe-grant
 *     （后端给订阅额度 +1，供次日对应槽位消费）。
 */
const { request } = require('./api');
const config = require('./config');

const SESSION_FLAG_KEY = '_subscribePromptedThisSession';
const REJECTED_KEY = 'subscribe_daily_rejected';       // 用户拒绝过：不重弹
const GRANTED_KEY = 'subscribe_daily_granted';         // 已授权过：不再打扰
const LEGACY_SUBSCRIBED_KEY = 'push_daily_subscribed'; // 兼容旧设置页开关状态
const PREFERENCE_CACHE_KEY = 'slot_preference';        // 设置页 GET 失败时的本地兜底

// 引导二选一（T4-4：选择星光降临的时刻——晨讯 / 星语）
const SLOT_PICK_ITEMS = [
  config.SLOT_INFO.morning.pickText,   // 清晨 7:37 · 晨星：今日星光
  config.SLOT_INFO.night.pickText,     // 夜晚 21:00 · 晚星：睡前星语
];

function _getSessionFlag() {
  try {
    const app = getApp();
    if (app && app.globalData) return !!app.globalData[SESSION_FLAG_KEY];
  } catch (_e) { /* app 不可用 */ }
  return false;
}

function _setSessionFlag() {
  // 仅内存标记：`_getSessionFlag` 只读 app.globalData，不读 storage，
  // 标记随 App 实例存活（页面销毁/重进不清除），符合「同会话最多弹 1 次」语义。
  // （此前 storage 写入无人读取，属死代码，已移除。）
  try {
    const app = getApp();
    if (app && app.globalData) app.globalData[SESSION_FLAG_KEY] = true;
  } catch (_e) { /* 标记失败不阻塞 */ }
}

function _clearSessionFlag() {
  // 仅内存标记：grant 上报失败时清除，允许本会话下一个触发点重试
  try {
    const app = getApp();
    if (app && app.globalData) app.globalData[SESSION_FLAG_KEY] = false;
  } catch (_e) { /* 标记失败不阻塞 */ }
}

function _getStorage(key) {
  try { return !!wx.getStorageSync(key); } catch (_e) { return false; }
}

function _setStorage(key, val) {
  try { wx.setStorageSync(key, val); } catch (_e) {}
}

/**
 * 授权成功后上报后端（一次性订阅额度 +1）。
 *
 * 时序契约（最终审查 F-1）：持久标记 GRANTED_KEY / LEGACY_SUBSCRIBED_KEY
 * 必须等 grant 请求成功后再置位——若先置位而 POST 失败，用户「以为订阅了
 * 却收不到」。失败静默（不弹错误提示），但清除会话标记，让本会话下一个
 * 触发点重新引导（storage 不置位，后续会话同样可再引导）。
 *
 * @param {Function} onSuccess - POST 成功（额度已发放）后回调
 * @param {Function} onFailure - POST 失败（静默）后回调
 */
function _reportGrant(onSuccess, onFailure) {
  request('/notify/subscribe-grant', { method: 'POST' })
    .then(() => {
      if (typeof onSuccess === 'function') onSuccess();
    })
    .catch(() => {
      if (typeof onFailure === 'function') onFailure();
    });
}

/**
 * 上报推送槽位偏好（T4-4）：grant 成功后才调用；失败静默。
 * 仅偏好未落库不阻塞订阅流程（后端默认 morning，用户可随时在
 * 我的-推送设置里重选）。
 * @param {string} slot - 'morning' | 'night'
 */
function _reportSlotPreference(slot) {
  request('/notify/preference', { method: 'POST', data: { slot } })
    .then(() => { /* 成功无需额外处理 */ })
    .catch(() => { /* 失败静默（见上注释） */ });
}

/**
 * 用户选定槽位后的订阅流程：requestSubscribeMessage → grant → preference。
 * @param {string} slot - 'morning'（晨星 7:37）| 'night'（晚星 21:00）
 */
function _requestSubscribe(slot) {
  const tmplId = config.WX_SUBSCRIBE_TEMPLATE_DAILY;
  wx.requestSubscribeMessage({
    tmplIds: [tmplId],
    success: (r) => {
      const accepted = r[tmplId] === 'accept';
      if (accepted) {
        const info = config.SLOT_INFO[slot] || config.SLOT_INFO.morning;
        try {
          wx.showToast({ title: info.grantToast, icon: 'none', duration: 2000 });
        } catch (_e) {}
        // 持久标记在 grant 成功后才置位（见 _reportGrant 时序契约）：
        // 失败时不清 GRANTED_KEY（本就未置）、清会话标记允许本会话重试
        _reportGrant(
          () => {
            _setStorage(GRANTED_KEY, true);
            // 兼容旧「我的-设置」开关（profile.js 读取该键显示状态）
            _setStorage(LEGACY_SUBSCRIBED_KEY, true);
            // 偏好缓存：我的-推送设置页 GET 失败时兜底显示本次选择
            _setStorage(PREFERENCE_CACHE_KEY, slot);
            // 槽位偏好上报：grant 成功后才调用（契约见 _reportSlotPreference）
            _reportSlotPreference(slot);
          },
          () => {
            _clearSessionFlag();
          }
        );
      } else {
        // 系统窗内选择「拒绝」/ 关闭：不再重弹
        _setStorage(REJECTED_KEY, true);
      }
    },
    fail: () => {
      // 系统窗未弹出/异常：本次会话不再尝试（避免反复打扰）
    },
  });
}

/**
 * 触发订阅引导（幂等，可安全地在多个触发点重复调用）
 *
 * 返回 true 表示本次真的弹出了引导（用于日志/埋点），
 * 未配置 / 已弹过 / 已拒绝 / 已授权时返回 false。
 *
 * T4-4 二选一（wx.showActionSheet）：
 *   - tapIndex 0 → 晨星（morning）→ grant + POST /notify/preference {slot:"morning"}
 *   - tapIndex 1 → 晚星（night）  → grant + POST /notify/preference {slot:"night"}
 *   - 面板取消（errMsg 含 cancel）→ 视为拒绝：置 REJECTED_KEY 不重弹
 *   - 其他异常（errMsg 不含 cancel）→ 仅本会话不再尝试，不置持久标记
 */
function maybePromptSubscribe() {
  const tmplId = config.WX_SUBSCRIBE_TEMPLATE_DAILY;
  if (!tmplId || typeof tmplId !== 'string') {
    return false; // 模板未配置：不弹
  }
  if (_getSessionFlag()) return false;          // 同会话最多 1 次
  if (_getStorage(REJECTED_KEY)) return false;  // 用户拒绝过：不重弹
  if (_getStorage(GRANTED_KEY)) return false;   // 已授权过：不再打扰

  // 先占位再弹窗，防止同一会话内多个触发点并发各弹一次
  _setSessionFlag();

  wx.showActionSheet({
    itemList: SLOT_PICK_ITEMS,
    success: (res) => {
      // 二选一：tapIndex 0 = 晨星（morning），1 = 晚星（night）
      const slot = res.tapIndex === 1 ? 'night' : 'morning';
      _requestSubscribe(slot);
    },
    fail: (err) => {
      // 用户点空白/取消（errMsg 含 cancel）→ 拒绝：不再重弹；
      // 面板异常等其他失败仅本会话不重试（会话标记保持置位）
      if (err && typeof err.errMsg === 'string' && err.errMsg.indexOf('cancel') !== -1) {
        _setStorage(REJECTED_KEY, true);
      }
    },
  });
  return true;
}

module.exports = { maybePromptSubscribe };
