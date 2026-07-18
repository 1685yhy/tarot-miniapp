// pages/encyclopedia/encyclopedia.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');
const { SUIT_ZH } = require('../../utils/constants');

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
    // 读取今日之牌（由首页抽牌后存入）
    const app = getApp();
    const dailyCard = app.globalData && app.globalData.dailyCard
      ? { ...app.globalData.dailyCard, imagePath: computeImagePath(app.globalData.dailyCard) }
      : null;
    this.setData({ dailyCard });

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
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
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

  // 今日之牌 — 点击跳转卡牌详情
  onDailyCardTap() {
    const id = this.data.dailyCard && this.data.dailyCard.id;
    if (id) {
      wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${id}` });
    }
  },

  // 未抽牌 → 跳转首页抽牌
  onDailyCardPromptTap() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadCards();
  },

  onUnload() {
    if (this._searchTimer) clearTimeout(this._searchTimer);
  },
});
