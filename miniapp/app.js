const { checkLogin } = require('./utils/auth');
const { BASE_URL } = require('./utils/api');

/** 试用存储键名 */
const TRIAL_STORAGE_KEY = 'trial_expiry';
const TRIAL_MEMBER_KEY = 'is_trial_member';

App({
  onLaunch() {
    // === 上线前配置自检 ===
    if (BASE_URL.includes('your-domain') || BASE_URL.includes('example.com')) {
      console.warn(
        '[tarot] ⚠️ 上线前提醒：BASE_URL 仍包含占位符，发布正式版前请替换！\n' +
        `  当前 BASE_URL = "${BASE_URL}"\n` +
        '  修改位置：miniapp/utils/api.js → ENV_URLS.release'
      );
    }

    checkLogin().catch(() => {
      console.log('登录将在首次API请求时触发');
    });

    // 检查试用是否过期，过期自动撤销
    this._checkTrialExpiry();
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
  },
});
