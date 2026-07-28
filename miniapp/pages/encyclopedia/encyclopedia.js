// pages/encyclopedia/encyclopedia.js
const perf = require('../../utils/performance');
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');
const { SUIT_ZH } = require('../../utils/constants');
const { playPageEnterSound } = require('../../utils/sound');

const BATCH_SIZE = 6;   // 首屏渐进加载（3行×2列，分批显示）
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
      { key: 'favorites', label: '收藏' },
      { key: 'major', label: '大牌 (22张)' },
      { key: 'wands', label: '权杖·行动' },
      { key: 'cups', label: '圣杯·情感' },
      { key: 'swords', label: '宝剑·思维' },
      { key: 'pentacles', label: '星币·物质' },
    ],
    suitZh: SUIT_ZH,
    loadedCount: 0,        // 当前已激活的卡牌数
    allActive: false,      // 是否已全部激活

    // Favorites
    favoriteIds: [],
    favoriteCount: 0,
    // Empty state type: 'search' (default) or 'favorites'
    emptyStateType: 'search',

    // Daily card context
    dailyCard: null,
    dailyCardImgLoaded: false,
    dailyCardImgError: false,

    // Daily tarot story (date-seeded random card with teaching)
    dailyStoryCard: null,
    dailyStoryLoading: false,
  },

  async onLoad(options) {
    const app = getApp();
    const dailyCard = app.globalData && app.globalData.dailyCard
      ? { ...app.globalData.dailyCard, imagePath: computeImagePath(app.globalData.dailyCard) }
      : null;
    this.setData({ dailyCard });

    await this.loadCards();

    // Load today's tarot story (date-seeded random card teaching)
    this._loadDailyStory();

    // If navigated from profile with favorites filter
    if (app.globalData && app.globalData.showCardFavorites) {
    if (app.globalData && app.globalData.showCardFavorites) {
      app.globalData.showCardFavorites = false;
      this.setData({ activeTab: 'favorites' });
      this.filterCards('favorites', this.data.searchKeyword);
    }
  },

  onShow() {
    // Refresh favorites data when switching tabs (e.g. user adds favorites from card-detail page)
    const favoriteIds = wx.getStorageSync('favorite_cards') || [];
    const favoriteSet = new Set(favoriteIds);
    const cards = this.data.cards.map(c => ({ ...c, favorited: favoriteSet.has(c.id) }));
    const filteredCards = this.data.filteredCards.map(c => ({ ...c, favorited: favoriteSet.has(c.id) }));
    // Refresh daily card reference from globalData (may have been updated on index page)
    const app = getApp();
    const dailyCard = app.globalData && app.globalData.dailyCard
      ? { ...app.globalData.dailyCard, imagePath: computeImagePath(app.globalData.dailyCard) }
      : this.data.dailyCard;
    this.setData({ cards, filteredCards, favoriteIds, favoriteCount: favoriteIds.length, dailyCard });

    // Re-apply favorites filter if currently viewing favorites tab
    if (this.data.activeTab === 'favorites') {
      this.filterCards('favorites', this.data.searchKeyword);
    } else if (this.data.activeTab === 'favorites' && this.data.filteredCards.length === 0) {
      this.setData({ emptyStateType: 'favorites' });
    }
  },

  async loadCards() {
    this.setData({ pageLoading: true });
    try {
      const data = await request('/cards');
      const rawCards = Array.isArray(data) ? data : (data.cards || []);

      // Load favorites from storage
      const favoriteIds = wx.getStorageSync('favorite_cards') || [];
      const favoriteSet = new Set(favoriteIds);

      const cards = rawCards.map(c => ({
        ...c,
        imagePath: computeImagePath(c),
        suitZh: SUIT_ZH[c.suit] || c.suit || '',
        _active: false,    // 分批激活
        favorited: favoriteSet.has(c.id),
      }));
      this.setData({
        cards,
        filteredCards: cards,
        pageLoading: false,
        favoriteIds,
        favoriteCount: favoriteIds.length,
      });

      // Entrance chime on first load
      playPageEnterSound();

      // 首屏激活第一批
      this._activateBatch(BATCH_SIZE);
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  // ===================== 分批渐进加载 =====================

  /** 激活前 N 张卡牌（触发 image 渲染），每张间隔 60ms 渐进出现 */
  _activateBatch(targetCount) {
    const { filteredCards, loadedCount, allActive } = this.data;
    if (allActive) return;
    const total = filteredCards.length;
    const next = Math.min(targetCount, total);

    if (next <= loadedCount) return;

    // 渐进式激活：每张卡牌间隔 60ms，避免一次性全部弹出
    const stagger = 60;
    for (let i = loadedCount; i < next; i++) {
      const delay = (i - loadedCount) * stagger;
      const timer = setTimeout(() => {
        this.setData({
          [`filteredCards[${i}]._active`]: true,
          [`filteredCards[${i}]._anim`]: true,
        });
        this._timers = this._timers.filter(t => t !== timer);
      }, delay);
      if (!this._timers) this._timers = [];
      this._timers.push(timer);
    }

    this.setData({
      loadedCount: next,
      allActive: next >= total,
    });
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
    } else if (tab === 'favorites') {
      cards = cards.filter(c => c.favorited);
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

    // Determine empty state message type
    const isEmptyFavorites = tab === 'favorites' && cards.length === 0 && !keyword;

    // 重置激活状态 + 激活第一批
    cards = cards.map((c, i) => ({ ...c, _active: i < BATCH_SIZE }));
    this.setData({
      filteredCards: cards,
      loadedCount: Math.min(BATCH_SIZE, cards.length),
      allActive: cards.length <= BATCH_SIZE,
      emptyStateType: isEmptyFavorites ? 'favorites' : 'search',
    });
  },

  // ===================== 收藏 =====================

  /** 切换收藏状态 */
  onToggleFavorite(e) {
    const cardId = e.currentTarget.dataset.cardId;
    const { cards, favoriteIds } = this.data;

    const idx = cards.findIndex(c => c.id === cardId);
    if (idx === -1) return;

    const wasFavorited = cards[idx].favorited;
    let newFavoriteIds;
    if (wasFavorited) {
      newFavoriteIds = favoriteIds.filter(id => id !== cardId);
    } else {
      newFavoriteIds = [...favoriteIds, cardId];
    }

    // Update cards array
    const favoritedKey = `cards[${idx}].favorited`;
    const updates = { [favoritedKey]: !wasFavorited };

    // Also update filteredCards if the card is visible
    const fIdx = this.data.filteredCards.findIndex(c => c.id === cardId);
    if (fIdx !== -1) {
      updates[`filteredCards[${fIdx}].favorited`] = !wasFavorited;
    }

    updates.favoriteIds = newFavoriteIds;
    updates.favoriteCount = newFavoriteIds.length;

    this.setData(updates);
    wx.setStorageSync('favorite_cards', newFavoriteIds);

    // If viewing favorites tab and unfavorited, remove from view
    if (this.data.activeTab === 'favorites' && wasFavorited) {
      this.filterCards('favorites', this.data.searchKeyword);
    }

    wx.showToast({
      title: wasFavorited ? '已取消收藏' : '已收藏',
      icon: 'none',
      duration: 1000,
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

  // ---- Daily Tarot Story (date-seeded random card teaching) ----

  /** Pick a deterministic card index based on today's date */
  _dailyStoryIndex(totalCards) {
    const d = new Date();
    const seed = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    return seed % totalCards;
  },

  async _loadDailyStory() {
    if (this._destroyed) return;
    const cards = this.data.cards;
    if (!cards || cards.length === 0) return;
    this.setData({ dailyStoryLoading: true });

    // Pick a card different from the daily card if possible
    const dailyCardId = this.data.dailyCard && this.data.dailyCard.id;
    let idx = this._dailyStoryIndex(cards.length);
    // If the selected card is the same as the daily card, shift by 1
    if (cards[idx] && cards[idx].id === dailyCardId && cards.length > 1) {
      idx = (idx + 1) % cards.length;
    }
    const storyCard = cards[idx];
    if (!storyCard) {
      this.setData({ dailyStoryLoading: false });
      return;
    }

    try {
      const teaching = await request(`/cards/${storyCard.id}/teaching`);
      if (this._destroyed) return;
      // Extract a story preview (~60 chars) for the hero card
      const storyRaw = teaching.story || '';
      const storyPreview = storyRaw.length > 60 ? storyRaw.slice(0, 60) : storyRaw;
      this.setData({
        dailyStoryCard: {
          id: storyCard.id,
          name_zh: storyCard.name_zh || storyCard.card_name || '',
          story_preview: storyPreview,
        },
        dailyStoryLoading: false,
      });
    } catch (err) {
      // Teaching data unavailable — silently degrade
      if (!this._destroyed) {
        this.setData({ dailyStoryLoading: false });
      }
    }
  },

  onGoCardDetail(e) {
    const id = e && e.currentTarget && e.currentTarget.dataset
      ? e.currentTarget.dataset.id
      : (this.data.dailyStoryCard && this.data.dailyStoryCard.id);
    if (id) {
      wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${id}` });
    }
  },

  onUnload() {
    if (this._searchTimer) clearTimeout(this._searchTimer);
    if (this._timers) this._timers.forEach(t => clearTimeout(t));
  },

  onReady() {
    // Performance monitoring: page ready timestamp
    perf.markPageReady('encyclopedia');
  },

  onHide() {
    if (this._timers) this._timers.forEach(t => clearTimeout(t));
  },
});
