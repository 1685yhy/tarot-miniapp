const { checkLogin } = require('./utils/auth');
const { BASE_URL } = require('./utils/api');
const perf = require('./utils/performance');
const analytics = require('./utils/analytics');

/** 试用存储键名 */
const TRIAL_STORAGE_KEY = 'trial_expiry';
const TRIAL_MEMBER_KEY = 'is_trial_member';

App({
  onLaunch() {
    // === Analytics: app launch ===
    analytics.pageView('app_launch');
    analytics.trackEvent('appLaunch');

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

    checkLogin().catch(() => {
      console.log('登录将在首次API请求时触发');
    });

    // 检查试用是否过期，过期自动撤销
    this._checkTrialExpiry();

    // === DEV: 自动化页面测试入口 ===
    this._initDevTestEntry();
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
