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
    teaching: null,
    activeTab: 'upright', // upright / reversed / teaching
    pageLoading: true,
    pageError: null,
    teachingLoading: false,
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

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },

  async loadCard(id) {
    if (this._destroyed) return;
    this.setData({ pageLoading: true, pageError: null });
    try {
      const card = await request(`/cards/${id}`);
      // Guard: API may return null/array in unexpected formats
      if (!card || Array.isArray(card)) {
        throw new Error('卡牌数据异常');
      }
      card.imagePath = computeImagePath(card, IMAGE_BASE);
      // Preprocess keywords into array (WXML does not support .split()/.trim())
      // Guard against null/undefined keywords
      const keywordsRaw = card.keywords_upright;
      if (typeof keywordsRaw === 'string' && keywordsRaw.trim()) {
        card.keywordsList = keywordsRaw.split(',').map(s => s.trim()).filter(Boolean);
      } else {
        card.keywordsList = [];
      }
      if (this._destroyed) return;
      this.setData({ card, pageLoading: false });
      // Fetch teaching data after card loads
      this.loadTeachingData(id);
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  async loadTeachingData(cardId) {
    if (this._destroyed) return;
    this.setData({ teachingLoading: true });
    try {
      const teaching = await request(`/cards/${cardId}/teaching`);
      if (this._destroyed) return;
      this.setData({ teaching, teachingLoading: false });
    } catch (err) {
      if (this._destroyed) return;
      // Teaching data is non-critical; silently fail
      this.setData({ teachingLoading: false });
      console.warn('[card-detail] 教学数据加载失败:', err.message);
    }
  },

  onTabTap(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab });
  },

  onRetry() {
    const id = this.options?.id;
    if (id) this.loadCard(id);
  },

  onGoBack() {
    wx.switchTab({ url: '/pages/encyclopedia/encyclopedia' });
  },
});
