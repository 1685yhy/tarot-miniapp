/**
 * 星光晨讯订阅引导（共享工具）
 * =========================================================
 * 三个触发点共用一个入口：
 *   - 抽牌结果页进入（reading-result）
 *   - 许愿成功（wish）
 *   - 每日一牌翻转后（daily-card）
 *
 * 行为约束（Task 6 简报）：
 *   - 模板未配置（config.WX_SUBSCRIBE_TEMPLATE_DAILY 为空）→ 不弹；
 *   - 用户拒绝 → 不再重弹（storage 持久标记）；
 *   - 同会话最多弹 1 次（wx.requestSubscribeMessage 每次调用都会弹系统窗，
 *     必须用全局标记限制——app.globalData 标记，页面销毁/重进不清除）；
 *   - 同意 → wx.requestSubscribeMessage 成功后调 POST /notify/subscribe-grant
 *     （后端给订阅额度 +1，供次日 7:37 星光晨讯消费）。
 */
const { request } = require('./api');
const config = require('./config');

const SESSION_FLAG_KEY = '_subscribePromptedThisSession';
const REJECTED_KEY = 'subscribe_daily_rejected';       // 用户拒绝过：不重弹
const GRANTED_KEY = 'subscribe_daily_granted';         // 已授权过：不再打扰
const LEGACY_SUBSCRIBED_KEY = 'push_daily_subscribed'; // 兼容旧设置页开关状态

// 引导文案（简报指定）
const PROMPT_TEXT = '订阅后，明早 7:37 收到你的今日星光';

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

function _getStorage(key) {
  try { return !!wx.getStorageSync(key); } catch (_e) { return false; }
}

function _setStorage(key, val) {
  try { wx.setStorageSync(key, val); } catch (_e) {}
}

/** 授权成功后上报后端（一次性订阅额度 +1）。失败静默——不打扰用户，下次授权会再发放。 */
function _reportGrant() {
  request('/notify/subscribe-grant', { method: 'POST' }).catch(() => {
    // 静默降级：额度发放失败不影响本流程，后端额度为空时晨讯不发
  });
}

/**
 * 触发订阅引导（幂等，可安全地在多个触发点重复调用）
 *
 * 返回 true 表示本次真的弹出了引导（用于日志/埋点），
 * 未配置 / 已弹过 / 已拒绝 / 已授权时返回 false。
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

  wx.showModal({
    title: '星光晨讯',
    content: PROMPT_TEXT,
    confirmText: '订阅',
    cancelText: '暂不',
    success: (res) => {
      if (!res.confirm) {
        // 用户拒绝：记录，不再重弹
        _setStorage(REJECTED_KEY, true);
        return;
      }
      wx.requestSubscribeMessage({
        tmplIds: [tmplId],
        success: (r) => {
          const accepted = r[tmplId] === 'accept';
          if (accepted) {
            _setStorage(GRANTED_KEY, true);
            // 兼容旧「我的-设置」开关（profile.js 读取该键显示状态）
            _setStorage(LEGACY_SUBSCRIBED_KEY, true);
            try {
              wx.showToast({ title: '订阅成功，明早见 ✦', icon: 'none', duration: 2000 });
            } catch (_e) {}
            _reportGrant();
          } else {
            // 系统窗内选择「拒绝」/ 关闭：不再重弹
            _setStorage(REJECTED_KEY, true);
          }
        },
        fail: () => {
          // 系统窗未弹出/异常：本次会话不再尝试（避免反复打扰）
        },
      });
    },
    fail: () => {
      // showModal 失败：本次会话不再尝试
    },
  });
  return true;
}

module.exports = { maybePromptSubscribe };
