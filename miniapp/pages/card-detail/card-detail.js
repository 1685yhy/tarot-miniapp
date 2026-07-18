// pages/card-detail/card-detail.js
const { request } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

// ---- Full-size image base (overrides default cards_thumb) ----
const IMAGE_BASE = (() => {
  try {
    const env = wx.getAccountInfoSync().miniProgram.envVersion;
    return env === 'develop' ? 'http://localhost:8000/images/cards' : 'https://xingxiang.chat/images/cards_full';
  } catch {
    return 'https://xingxiang.chat/images/cards_full';
  }
})();

Page({
  data: {
    card: null,
    activeTab: 'upright', // upright / reversed
    pageLoading: true,
    pageError: null,
    _destroyed: false,
  },

  async onLoad(options) {
    this.options = options;
    const { id } = options;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }
    await this.loadCard(id);
  },

  onUnload() {
    this.data._destroyed = true;
  },

  async loadCard(id) {
    if (this.data._destroyed) return;
    this.setData({ pageLoading: true, pageError: null });
    try {
      const card = await request(`/cards/${id}`);
      card.imagePath = computeImagePath(card, IMAGE_BASE);
      // Preprocess keywords into array (WXML does not support .split()/.trim())
      if (card.keywords_upright) {
        card.keywordsList = card.keywords_upright.split(',').map(s => s.trim());
      } else {
        card.keywordsList = [];
      }
      if (this.data._destroyed) return;
      this.setData({ card, pageLoading: false });
    } catch (err) {
      if (this.data._destroyed) return;
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
