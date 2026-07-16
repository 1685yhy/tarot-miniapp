// pages/encyclopedia/encyclopedia.js
const { request } = require('../../utils/api');

// ---- Image path computation (mirrors tarot-card component logic) ----
const IMAGE_BASE = (() => {
  try {
    const info = wx.getAccountInfoSync();
    const env = info.miniProgram ? info.miniProgram.envVersion : 'release';
    return env === 'develop' ? 'http://xingxiang.chat/images/cards_thumb' : 'https://xingxiang.chat/images/cards_thumb';
  } catch {
    return 'https://xingxiang.chat/images/cards_thumb';
  }
})();
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

// Suit English → Chinese map
const SUIT_ZH = { wands: '权杖', cups: '圣杯', swords: '宝剑', pentacles: '星币' };

Page({
  data: {
    cards: [],
    filteredCards: [],
    activeTab: 'all', // all / major / wands / cups / swords / pentacles
    searchKeyword: '',
    pageLoading: true,
    pageError: null,
    tabs: [
      { key: 'all', label: '全部' },
      { key: 'major', label: '大牌' },
      { key: 'wands', label: '权杖' },
      { key: 'cups', label: '圣杯' },
      { key: 'swords', label: '宝剑' },
      { key: 'pentacles', label: '星币' },
    ],
    suitZh: SUIT_ZH,
  },

  async onLoad() {
    await this.loadCards();
  },

  async loadCards() {
    this.setData({ pageLoading: true });
    try {
      const data = await request('/cards');
      const rawCards = Array.isArray(data) ? data : (data.cards || []);
      const cards = rawCards.map(c => ({
        ...c,
        imagePath: computeImagePath(c),
        suitZh: SUIT_ZH[c.suit] || c.suit || '',
      }));
      this.setData({ cards, filteredCards: cards, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    }
  },

  onTabTap(e) {
    const tab = e.currentTarget.dataset.key;
    this.setData({ activeTab: tab });
    this.filterCards(tab, this.data.searchKeyword);
  },

  onSearchInput(e) {
    const keyword = e.detail.value;
    this.setData({ searchKeyword: keyword });
    // Debounce search to avoid filtering on every keystroke
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.filterCards(this.data.activeTab, keyword);
    }, 300);
  },

  filterCards(tab, keyword) {
    let cards = this.data.cards;

    // Filter by tab
    if (tab === 'major') {
      cards = cards.filter(c => c.arcana === 'major');
    } else if (tab === 'wands') {
      cards = cards.filter(c => c.suit === 'wands');
    } else if (tab === 'cups') {
      cards = cards.filter(c => c.suit === 'cups');
    } else if (tab === 'swords') {
      cards = cards.filter(c => c.suit === 'swords');
    } else if (tab === 'pentacles') {
      cards = cards.filter(c => c.suit === 'pentacles');
    }

    // Filter by keyword
    if (keyword) {
      const kw = keyword.toLowerCase();
      cards = cards.filter(c =>
        (c.name_zh && c.name_zh.includes(kw)) ||
        (c.name_en && c.name_en.toLowerCase().includes(kw)) ||
        (c.meaning_upright && c.meaning_upright.toLowerCase().includes(kw)) ||
        (c.meaning_reversed && c.meaning_reversed.toLowerCase().includes(kw)) ||
        (c.keywords_upright && c.keywords_upright.toLowerCase().includes(kw))
      );
    }

    this.setData({ filteredCards: cards });
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${id}` });
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadCards();
  },

  onUnload() {
    if (this._searchTimer) clearTimeout(this._searchTimer);
  },
});
