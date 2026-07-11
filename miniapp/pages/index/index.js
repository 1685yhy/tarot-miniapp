// pages/index/index.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    dailyCard: null,
    freeCount: 0,
    user: null,
  },

  async onLoad() {
    const user = await checkLogin();
    this.setData({ user, freeCount: user?.free_readings_today || 0 });
  },

  async drawDailyCard() {
    if (this.data.freeCount >= 1 && !this.data.user?.is_member) {
      wx.showToast({ title: '今日免费次数已用完', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '抽取中...' });
    try {
      const card = await request('/cards/daily');
      this.setData({ dailyCard: card, freeCount: this.data.freeCount + 1 });
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
    if (!this.data.user?.is_member) {
      wx.navigateTo({ url: `/pages/membership/membership?from=reading` });
      return;
    }
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },
});
