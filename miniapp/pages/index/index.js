// pages/index/index.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    dailyCard: null,
    freeCount: 0,
    user: null,
    pageLoading: true,
    pageError: null,
  },

  async onLoad() {
    try {
      const user = await checkLogin();
      this.setData({ user, freeCount: user?.free_readings_today || 0, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.errMsg || '加载失败' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  async drawDailyCard() {
    wx.showLoading({ title: '抽取中...' });
    try {
      const card = await request('/cards/daily');
      this.setData({ dailyCard: card });
      wx.hideLoading();
      // 保存到globalData供详情页使用
      getApp().globalData.dailyCard = card;
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '抽取失败，请重试', icon: 'none' });
    }
  },

  navigateToReading(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },
});
