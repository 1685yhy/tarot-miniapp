// pages/card-detail/card-detail.js
const { request } = require('../../utils/api');

Page({
  data: {
    card: null,
    activeTab: 'upright', // upright / reversed
    loading: true,
  },

  async onLoad(options) {
    const { id } = options;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }
    await this.loadCard(id);
  },

  async loadCard(id) {
    this.setData({ loading: true });
    try {
      const card = await request(`/cards/${id}`);
      this.setData({ card, loading: false });
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onTabTap(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },
});
