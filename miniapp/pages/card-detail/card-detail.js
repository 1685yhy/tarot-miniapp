// pages/card-detail/card-detail.js
const { request } = require('../../utils/api');

// ---- Image path computation (mirrors tarot-card component logic) ----
const IMAGE_BASE = 'https://xingxiang.chat/images/cards';
const RANK_MAP = {
  ace: 0, two: 1, three: 2, four: 3, five: 4,
  six: 5, seven: 6, eight: 7, nine: 8, ten: 9,
  page: 10, knight: 11, queen: 12, king: 13,
};

function computeImagePath(card) {
  if (!card || !card.name_en) return '';
  const enSnake = card.name_en.toLowerCase().replace(/\s+/g, '_');
  if (card.arcana === 'major') {
    const idx = String(card.card_number).padStart(2, '0');
    return `${IMAGE_BASE}/major_${idx}_${enSnake}.png`;
  }
  if (card.suit) {
    const firstWord = card.name_en.toLowerCase().split(' ')[0];
    const idx = RANK_MAP[firstWord] !== undefined ? RANK_MAP[firstWord] : 0;
    return `${IMAGE_BASE}/${card.suit}_${String(idx).padStart(2, '0')}_${enSnake}.png`;
  }
  return '';
}

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
      card.imagePath = computeImagePath(card);
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
