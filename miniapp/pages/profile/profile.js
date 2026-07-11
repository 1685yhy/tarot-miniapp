// pages/profile/profile.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    user: null,
    memberStatus: null,
    readingHistory: [],
    pageLoading: true,
    pageError: null,
  },

  async onShow() {
    await this.loadData();
  },

  async loadData() {
    this.setData({ pageLoading: true });
    try {
      const user = await checkLogin();
      const [status, history] = await Promise.all([
        request('/membership/status'),
        request('/readings/history'),
      ]);
      this.setData({
        user,
        memberStatus: status,
        readingHistory: history.items || [],
        pageLoading: false,
      });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.errMsg || '加载失败' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadData();
  },

  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onViewReading(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/reading-result/reading-result?id=${id}` });
  },

  onGoDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  onGoAnnualReport() {
    wx.navigateTo({ url: '/pages/annual-report/annual-report' });
  },

  async onClearHistory() {
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: '清除记录',
        content: '确定清除所有占卜历史记录吗？此操作不可恢复。',
        success: resolve,
      });
    });
    if (!res.confirm) return;

    try {
      await request('/readings/history', { method: 'DELETE' });
      this.setData({ readingHistory: [] });
      wx.showToast({ title: '已清除', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '清除失败', icon: 'none' });
    }
  },
});
