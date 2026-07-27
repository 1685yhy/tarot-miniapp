// pages/card-detail/card-detail.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

// ---- Full-size image base (overrides default cards_thumb) ----
// Full-size card images — served via CDN (xingxiang.chat/images/cards_full/)
// Development: use local dev server images
const IMAGE_BASE = (() => {
  try {
    const env = wx.getAccountInfoSync().miniProgram.envVersion;
    if (env === 'develop' || env === 'trial') {
      return '/images/cards_thumb';
    }
  } catch(e) {}
  return 'https://xingxiang.chat/images/cards_full';
})();

Page({
  data: {
    card: null,
    heroImgLoaded: false,
    heroImgError: false,
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

  /** Toggle card favorite (local storage) */
  onCollect() {
    const card = this.data.card;
    if (!card) return;
    const favs = wx.getStorageSync('favorite_cards') || [];
    const idx = favs.indexOf(card.id);
    if (idx >= 0) {
      favs.splice(idx, 1);
      wx.showToast({ title: '已取消收藏', icon: 'none' });
    } else {
      favs.push(card.id);
      wx.showToast({ title: '已收藏 ✦', icon: 'none' });
    }
    wx.setStorageSync('favorite_cards', favs);
  },

  /** Share card detail to friend */
  onShare() {
    // Handled by onShareAppMessage below
  },

  onShareAppMessage() {
    const card = this.data.card;
    return {
      title: card ? `${card.name_zh} — 星光映照塔罗` : '星光映照 · 塔罗百科',
      path: `/pages/card-detail/card-detail?id=${card?.id || ''}`,
    };
  },
});
