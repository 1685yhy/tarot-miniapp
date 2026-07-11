const { checkLogin } = require('./utils/auth');

App({
  onLaunch() {
    checkLogin().catch(() => {
      console.log('登录将在首次API请求时触发');
    });
  },

  globalData: {
    user: null,
    dailyCard: null,
  },
});
