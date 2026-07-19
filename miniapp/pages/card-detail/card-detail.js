// pages/card-detail/card-detail.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

// ---- Full-size image base (overrides default cards_thumb) ----
// Full-size card images — served via CDN (xingxiang.chat/images/cards_full/)
// Development: uses same CDN path; IDE urlCheck=false allows domain bypass
const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';

Page({
  data: {
    card: null,
    activeTab: 'upright', // upright / reversed
    pageLoading: true,
    pageError: null,
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

  onHeroImgLoad() {
    this.setData({ heroImgLoaded: true });
  },

  onHeroImgError() {
    this.setData({ heroImgError: true });
  },

  onUnload() {
    this._destroyed = true;
  },

  async loadCard(id) {
    if (this._destroyed) return;
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
      if (this._destroyed) return;
      this.setData({ card, pageLoading: false });
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
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
