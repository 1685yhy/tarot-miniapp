// pages/encyclopedia/encyclopedia.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');
const { SUIT_ZH } = require('../../utils/constants');

const BATCH_SIZE = 12;   // 首屏+预加载批量（6行×2列）
const CARD_ROW_HEIGHT = 320; // rpx — 估算每行高度（含gap）

Page({
  data: {
    cards: [],
    filteredCards: [],
    activeTab: 'all',
    searchKeyword: '',
    pageLoading: true,
    pageError: null,
    tabs: [
      { key: 'all', label: '全部' },
      { key: 'major', label: '主牌 (22张)' },
      { key: 'wands', label: '权杖·行动' },
      { key: 'cups', label: '圣杯·情感' },
      { key: 'swords', label: '宝剑·思维' },
      { key: 'pentacles', label: '星币·物质' },
    ],
    suitZh: SUIT_ZH,
    loadedCount: 0,        // 当前已激活的卡牌数
    allActive: false,      // 是否已全部激活
  },

  async onLoad() {
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
        _active: false,    // 分批激活
      }));
      this.setData({ cards, filteredCards: cards, pageLoading: false });

      // 首屏激活第一批
      this._activateBatch(BATCH_SIZE);
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  // ===================== 分批渐进加载 =====================

  /** 激活前 N 张卡牌（触发 image 渲染） */
  _activateBatch(targetCount) {
    const { filteredCards, loadedCount, allActive } = this.data;
    if (allActive) return;
    const total = filteredCards.length;
    const next = Math.min(targetCount, total);

    if (next <= loadedCount) return;

    // 批量 setData — 激活 [loadedCount, next) 范围的卡牌
    const updates = {};
    for (let i = loadedCount; i < next; i++) {
      updates[`filteredCards[${i}]._active`] = true;
    }
    updates.loadedCount = next;
    updates.allActive = next >= total;
    this.setData(updates);
  },

  /** 滚动事件 — 接近当前加载边界时自动激活下一批 */
  onPageScroll(e) {
    if (this.data.allActive) return;
    const { loadedCount } = this.data;
    const total = this.data.filteredCards.length;
    if (loadedCount >= total) return;

    // 估算：已加载行数 = loadedCount / 2（2列） 再 + 2 行预加载
    const loadedRows = Math.ceil(loadedCount / 2) + 2;
    const loadedBottom = loadedRows * CARD_ROW_HEIGHT; // rpx

    // 屏幕高度（rpx）
    const screenHeightRpx = (e.scrollHeight / e.scrollTop) > 0
      ? 0 : 0;
    // 用 scrollTop（px） 估算已滚动到的 rpx 位置
    const sysInfo = wx.getSystemInfoSync();
    const rpxRatio = 750 / sysInfo.windowWidth;
    const scrollTopRpx = e.scrollTop * rpxRatio;
    const screenRpx = sysInfo.windowHeight * rpxRatio;

    // 当滚动位置 + 一屏高度 接近 当前已加载底部时，加载下一批
    const viewBottom = scrollTopRpx + screenRpx;
    if (viewBottom >= loadedBottom * 0.7) {
      this._activateBatch(loadedCount + BATCH_SIZE);
    }
  },

  // ===================== Tab & 搜索 =====================

  onTabTap(e) {
    const tab = e.currentTarget.dataset.key;
    this.setData({ activeTab: tab, loadedCount: 0, allActive: false });
    this.filterCards(tab, this.data.searchKeyword);
  },

  onSearchInput(e) {
    const keyword = e.detail.value;
    this.setData({ searchKeyword: keyword });
    if (this._searchTimer) clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.filterCards(this.data.activeTab, keyword);
    }, 300);
  },

  filterCards(tab, keyword) {
    let cards = this.data.cards;

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

    // 重置激活状态 + 激活第一批
    cards = cards.map((c, i) => ({ ...c, _active: i < BATCH_SIZE }));
    this.setData({
      filteredCards: cards,
      loadedCount: Math.min(BATCH_SIZE, cards.length),
      allActive: cards.length <= BATCH_SIZE,
    });
  },

  // ===================== 导航 =====================

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${id}` });
  },

  onDailyCardTap() {
    const id = this.data.dailyCard && this.data.dailyCard.id;
    if (id) {
      wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${id}` });
    }
  },

  onDailyCardPromptTap() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true, loadedCount: 0, allActive: false });
    this.loadCards();
  },

  // —— Card image load/error events ——
  onCardImgLoad(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`filteredCards[${idx}]._imgLoaded`]: true });
    }
  },

  onCardImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`filteredCards[${idx}]._imgError`]: true });
    }
  },

  onDailyCardImgLoad() {
    this.setData({ dailyCardImgLoaded: true });
  },

  onDailyCardImgError() {
    this.setData({ dailyCardImgError: true });
  },

  onUnload() {
    if (this._searchTimer) clearTimeout(this._searchTimer);
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },
});
