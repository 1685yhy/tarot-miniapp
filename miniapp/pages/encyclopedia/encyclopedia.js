// pages/encyclopedia/encyclopedia.js
const { request } = require('../../utils/api');

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
  },

  async onLoad() {
    await this.loadCards();
  },

  async onShow() {
    // Refresh when coming back from card detail
  },

  async loadCards() {
    this.setData({ pageLoading: true });
    try {
      const data = await request('/cards');
      const cards = data.cards || [];
      this.setData({ cards, filteredCards: cards, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.errMsg || '加载失败' });
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
        c.name_zh.includes(kw) || c.name_en.toLowerCase().includes(kw)
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
