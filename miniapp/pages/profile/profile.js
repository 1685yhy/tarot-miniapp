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

  onClearHistory() {
    wx.showModal({
      title: '清除记录',
      content: '确定清除所有历史记录吗？',
      success: () => {
        this.setData({ readingHistory: [] });
        wx.showToast({ title: '已清除', icon: 'success' });
      },
    });
  },
});
