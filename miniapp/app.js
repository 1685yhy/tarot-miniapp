const { checkLogin } = require('./utils/auth');
const { BASE_URL } = require('./utils/api');

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
  },

  globalData: {
    user: null,
    dailyCard: null,
    onboardingCompleted: false,
  },
});
