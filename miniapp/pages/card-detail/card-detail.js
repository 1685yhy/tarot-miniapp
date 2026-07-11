// pages/card-detail/card-detail.js
const { request } = require('../../utils/api');

Page({
  data: {
    card: null,
    activeTab: 'upright', // upright / reversed
    pageLoading: true,
    pageError: null,
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
    this.setData({ pageLoading: true, pageError: null });
    try {
      const card = await request(`/cards/${id}`);
      // Preprocess keywords into array (WXML does not support .split()/.trim())
      if (card.keywords_upright) {
        card.keywordsList = card.keywords_upright.split(',').map(s => s.trim());
      } else {
        card.keywordsList = [];
      }
      this.setData({ card, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    }
  },

  onTabTap(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },

  onRetry() {
    const id = this.options?.id;
    if (id) this.loadCard(id);
  },
});
