// pages/card-detail/card-detail.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath, pngFallbackPath } = require('../../utils/cards');
const analytics = require('../../utils/analytics');

// Full-size card images served via CDN (xingxiang.chat/images/cards_full/)
const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';

Page({
  data: {
    card: null,
    heroImgLoaded: false,
    heroImgError: false,
    teaching: null,
    activeTab: 'upright', // upright / reversed / teaching
    activeSection: '',    // love / career / finance / health —— 折叠分节（'' = 全部收起）
    prevCard: null,       // { id, name_zh } 上一张
    nextCard: null,       // { id, name_zh } 下一张
    isFirst: false,
    isLast: false,
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
    // Retry once with PNG fallback before giving up on the hero image
    const current = this.data.card && this.data.card.imagePath;
    if (current && current.endsWith('.webp') && !this.data.webpFallbackTried) {
      this.setData({ webpFallbackTried: true, 'card.imagePath': pngFallbackPath(current) });
      return;
    }
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
    this.setData({
      pageLoading: true,
      pageError: null,
      heroImgLoaded: false,
      heroImgError: false,
      webpFallbackTried: false,
      teaching: null,
    });
    try {
      const card = await request(`/cards/${id}`);
      // Guard: API may return null/array in unexpected formats
      if (!card || Array.isArray(card)) {
        throw new Error('卡牌数据异常');
      }
      card.imagePath = computeImagePath(card, IMAGE_BASE);
      // Preprocess keywords into arrays (WXML does not support .split()/.trim())
      // Guard against null/undefined keywords
      const splitKeywords = (raw) => {
        if (typeof raw === 'string' && raw.trim()) {
          return raw.split(',').map(s => s.trim()).filter(Boolean);
        }
        return [];
      };
      card.keywordsList = splitKeywords(card.keywords_upright);
      card.keywordsListRev = splitKeywords(card.keywords_reversed);
      if (this._destroyed) return;
      this.setData({ card, pageLoading: false });
      // 更新上一张/下一张导航信息（列表加载失败时降级为 id±1）
      this._updateCardNav();
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
    this.setData({ activeTab: e.currentTarget.dataset.tab, activeSection: '' });
  },

  /** 页内折叠分节：感情/事业/财运/健康 展开收起（再次点击收起） */
  onSectionTap(e) {
    const section = e.currentTarget.dataset.section;
    this.setData({
      activeSection: this.data.activeSection === section ? '' : section,
    });
  },

  /** 拉取全量卡牌列表一次，用于上一张/下一张的名称与顺序 */
  async _ensureCardOrder() {
    if (this._cardOrder) return this._cardOrder;
    try {
      const data = await request('/cards');
      const list = Array.isArray(data) ? data : (data.cards || []);
      this._cardOrder = list
        .map(c => ({ id: c.id, name_zh: c.name_zh }))
        .filter(c => c.id != null);
    } catch (err) {
      console.warn('[card-detail] 卡牌列表加载失败，降级为 id±1:', err.message);
      this._cardOrder = [];
    }
    return this._cardOrder;
  },

  async _updateCardNav() {
    const card = this.data.card;
    if (!card) return;
    const order = await this._ensureCardOrder();
    const idx = order.findIndex(c => c.id === card.id);
    if (idx === -1) {
      // 兜底：服务端 id 连续（1-78），按 id±1 导航
      this.setData({
        prevCard: card.id > 1 ? { id: card.id - 1, name_zh: '' } : null,
        nextCard: card.id < 78 ? { id: card.id + 1, name_zh: '' } : null,
        isFirst: card.id <= 1,
        isLast: card.id >= 78,
      });
      return;
    }
    this.setData({
      prevCard: idx > 0 ? order[idx - 1] : null,
      nextCard: idx < order.length - 1 ? order[idx + 1] : null,
      isFirst: idx <= 0,
      isLast: idx >= order.length - 1,
    });
  },

  onPrevCard() {
    const target = this.data.prevCard;
    if (!target || this.data.pageLoading) return;
    this._switchCard(target);
  },

  onNextCard() {
    const target = this.data.nextCard;
    if (!target || this.data.pageLoading) return;
    this._switchCard(target);
  },

  _switchCard(target) {
    wx.pageScrollTo({ scrollTop: 0, duration: 200 });
    this.setData({ activeTab: 'upright', activeSection: '' });
    this.loadCard(target.id);
  },

  onRetry() {
    const id = this.options?.id;
    if (id) this.loadCard(id);
  },

  onGoBack() {
    // 百科已改为普通页面（3 Tab 改造后）
    wx.navigateBack({ delta: 1 });
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
      /* UX 修复: 痛点#5 — 收藏为本地存储，toast 明确说明存放位置 */
      wx.showToast({ title: '已收藏（保存在本机）', icon: 'none' });
    }
    wx.setStorageSync('favorite_cards', favs);
  },

  /** Share card detail to friend */
  onShare() {
    // Handled by onShareAppMessage below
  },

  onShareAppMessage() {
    // Analytics: card detail share
    analytics.trackShare('wechat_friend', 'card_detail');
    const card = this.data.card;
    return {
      title: card ? `${card.name_zh} — 星光映照塔罗` : '星光映照 · 塔罗百科',
      path: `/pages/card-detail/card-detail?id=${card?.id || ''}`,
    };
  },
});
