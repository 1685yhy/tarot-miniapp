const { checkLogin } = require('./utils/auth');
const { BASE_URL, request } = require('./utils/api');
const perf = require('./utils/performance');
const analytics = require('./utils/analytics');
const errorReport = require('./utils/error-report');

/** 试用存储键名 */
const TRIAL_STORAGE_KEY = 'trial_expiry';
const TRIAL_MEMBER_KEY = 'is_trial_member';

/** 裂变：已处理的邀请码存储键（同一邀请码只处理一次） */
const INVITE_PROCESSED_KEY = '_invite_processed_code';

App({
  onLaunch(options) {
    // === 裂变：好友送牌 —— 收到邀请码则登录后兑换 ===
    this._handleInvite(options);

    // === Analytics: app launch (scene + query params) ===
    analytics.trackAppLaunch(options);

    // === Performance monitoring: app start ===
    perf.mark('appLaunch');

    // === 上线前配置自检 ===
    if (BASE_URL.includes('your-domain') || BASE_URL.includes('example.com')) {
      console.warn(
        '[tarot] ⚠️ 上线前提醒：BASE_URL 仍包含占位符，发布正式版前请替换！\n' +
        `  当前 BASE_URL = "${BASE_URL}"\n` +
        '  修改位置：miniapp/utils/api.js → ENV_URLS.release'
      );
    }

    checkLogin()
      .catch(() => {
        console.log('登录将在首次API请求时触发');
      })
      .then(() => this._processPendingInvite());

    // 检查试用是否过期，过期自动撤销
    this._checkTrialExpiry();

    // === DEV: 自动化页面测试入口 ===
    this._initDevTestEntry();
  },

  // === 前端错误静默上报：script error / 未捕获的 Promise 拒绝 ===
  onError(err) {
    // 微信传入的是错误信息字符串（也可能带 message/stack）
    errorReport.reportError(err);
  },

  onUnhandledRejection(res) {
    // res = { reason }，reason 可能是 Error / string / object
    const reason = (res && res.reason) || '';
    errorReport.reportError(reason);
  },

  /** 开发环境自动化页面测试 */
  _initDevTestEntry() {
    try {
      const env = wx.getAccountInfoSync().miniProgram.envVersion;
      if (env === 'develop') {
        // 在首页添加测试入口
        const pages = getCurrentPages();
        if (pages.length === 0) {
          // App 刚启动，延迟跳转
          setTimeout(() => {
            const currentPages = getCurrentPages();
            if (currentPages.length > 0 && currentPages[0].route === 'pages/index/index') {
              wx.showToast({ title: 'DEV模式 · 测试页就绪', icon: 'none', duration: 2000 });
            }
          }, 3000);
        }
        console.log('[DEV] 自动化测试页: /pages/test-runner/test-runner');
      }
    } catch (e) { /* silent */ }
  },

  /* ---------------------------------------------------------------
     裂变：好友送牌 —— 处理进入小程序的邀请码
     - 扫码进入：wxacode 的 scene 形如 "invite_code=STAR-XXXX"
     - 普通链接：?invite_code=STAR-XXXX 或 ?invite=STAR-XXXX（兼容旧版分享）
     成功兑换后双方各得 +1 次免费深度解读（不是会员、不是现金）
     --------------------------------------------------------------- */

  /** 解析启动参数中的邀请码并暂存（登录完成后兑换） */
  _handleInvite(options) {
    const query = (options && options.query) || {};
    let code = query.invite_code || query.invite || '';
    if (!code && query.scene) {
      // 小程序码（wxacode.getUnlimited）扫码进入：scene 直接出现在 query 中
      const match = /invite_code=([A-Z0-9-]+)/i.exec(String(query.scene));
      if (match) code = match[1];
    }
    if (!code) return;
    this._pendingInviteCode = String(code).trim().toUpperCase();
  },

  /** 兑换邀请码：成功后 toast 提示；每个邀请码只处理一次 */
  async _processPendingInvite() {
    const code = this._pendingInviteCode;
    if (!code || this._inviteProcessing) return;
    this._pendingInviteCode = null;
    this._inviteProcessing = true;

    try {
      // 同一邀请码只兑换一次（本地去重，服务端另有唯一约束兜底）
      if (wx.getStorageSync(INVITE_PROCESSED_KEY) === code) return;

      await request('/share/invite', {
        method: 'POST',
        data: { invite_code: code },
      });

      wx.setStorageSync(INVITE_PROCESSED_KEY, code);
      wx.showToast({
        title: '好友送你一张牌！获得一次免费深度解读 ✦',
        icon: 'none',
        duration: 2500,
      });
    } catch (err) {
      // 静默失败：邀请码无效 / 已领取过 / 不能邀请自己
      console.warn('[invite] 邀请码处理失败:', err.message);
    } finally {
      this._inviteProcessing = false;
    }
  },

  /** 检查本地试用缓存是否过期 */
  _checkTrialExpiry() {
    try {
      const expiry = wx.getStorageSync(TRIAL_STORAGE_KEY);
      const isTrial = wx.getStorageSync(TRIAL_MEMBER_KEY);
      if (expiry && isTrial && Date.now() >= expiry) {
        wx.removeStorageSync(TRIAL_STORAGE_KEY);
        wx.removeStorageSync(TRIAL_MEMBER_KEY);
        console.log('[trial] 试用已过期，已自动撤销会员状态');
      }
    } catch (e) {
      // Storage 异常静默处理
    }
  },

  globalData: {
    user: null,
    dailyCard: null,
    onboardingCompleted: false,
    showCardFavorites: false,
  },
});
