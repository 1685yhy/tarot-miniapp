// WeChat analytics wrapper
const analytics = {
  // Track page view
  pageView(pageName) {
    wx.reportAnalytics('page_view', { page: pageName, timestamp: Date.now() });
  },
  // Track button/CTA clicks
  trackEvent(eventName, data = {}) {
    wx.reportAnalytics(eventName, { ...data, timestamp: Date.now() });
  },
  // Track conversion funnel
  funnel(step, data = {}) {
    wx.reportAnalytics('conversion_funnel', { step, ...data, timestamp: Date.now() });
  }
};
module.exports = analytics;
