// pages/about/about.js
Page({
  data: {},

  onReady() {
    // Performance monitoring
    if (typeof perf !== 'undefined') {
      perf.markPageReady('about');
    }
  },

  /**
   * 用户协议入口（P4-3）
   * 跳转 legal 页（?type=agreement）
   */
  onOpenAgreement() {
    wx.navigateTo({ url: '/pages/legal/legal?type=agreement' });
  },

  /**
   * 隐私政策入口（P4-3）
   * 跳转 legal 页（?type=privacy）
   */
  onOpenPrivacy() {
    wx.navigateTo({ url: '/pages/legal/legal?type=privacy' });
  },
});
