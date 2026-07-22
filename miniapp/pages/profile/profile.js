// pages/profile/profile.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { computeImagePath, findCard } = require('../../utils/cards');
const sound = require('../../utils/sound');

// 牌阵英文键名到中文显示名的映射
const SPREAD_TYPE_NAMES = {
  three_card: '三牌占卜',
  triangle: '恋人三角',
  celtic_cross: '凯尔特十字',
  career: '事业牌阵',
  finance: '财运牌阵',
  decision: '二择一',
  life_cross: '人生十字',
  horseshoe: '马蹄牌阵',
  relationship: '关系牌阵',
  year_ahead: '年度运势',
  daily: '每日占卜',
  career_path: '事业路线',
  weekly_outlook: '周运势',
  love_reading: '爱情占卜',
  fortune_telling: '财运占卜',
};

function computeCardImage(firstCardName) {
  if (!firstCardName) return '';
  const found = findCard(firstCardName);
  return found && found.image ? found.image : '';
}

Page({
  data: {
    user: null,
    memberStatus: null,
    readingHistory: [],
    pageLoading: true,
    pageError: null,
    historyPage: 1,
    hasMore: true,
    loadingMore: false,
    historyTotal: 0,
    spreadTypeNames: SPREAD_TYPE_NAMES,

    // Saved readings
    savedReadings: [],
    savedReadingsLoading: false,

    // Favorites count
    favoriteCount: 0,

    // Sound settings
    soundEnabled: true,

    // Draw mode preference
    defaultDrawMode: 'immersive',
  },

  // —— History card image loading ——
  onHistoryImgLoad(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`readingHistory[${idx}]._imgLoaded`]: true });
    }
  },

  onHistoryImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`readingHistory[${idx}]._imgError`]: true });
    }
  },

  async onShow() {
    await this.loadData();
    // Sync sound state from sound module
    this.setData({
      soundEnabled: sound.sfxEnabled,
      defaultDrawMode: wx.getStorageSync('default_draw_mode') || 'immersive',
    });
  },

  async loadData() {
    this.setData({ pageLoading: true });
    try {
      const user = await checkLogin();
      const [status, history] = await Promise.all([
        request('/membership/status'),
        request('/readings/history?page=1&page_size=20'),
      ]);
      this.setData({
        user,
        memberStatus: status ? {
          ...status,
          expiresAtFormatted: status.expires_at ? status.expires_at.split('T')[0] : '',
        } : null,
        readingHistory: (history.items || []).map(item => ({
          ...item,
          spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
          firstCardImage: computeCardImage(item.first_card_name),
          createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
        })),
        historyTotal: history.total || (history.items ? history.items.length : 0),
        pageLoading: false,
        historyPage: 1,
        hasMore: history.items ? history.items.length >= 20 : false,
      });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }

    // Also load saved readings from local storage
    this._loadSavedReadings();
    this._loadFavoriteCount();
  },

  _loadFavoriteCount() {
    const favoriteIds = wx.getStorageSync('favorite_cards') || [];
    this.setData({ favoriteCount: favoriteIds.length });
  },

  async _loadSavedReadings() {
    const savedIds = wx.getStorageSync('saved_readings') || [];
    if (!savedIds.length) {
      this.setData({ savedReadings: [], savedReadingsLoading: false });
      return;
    }
    this.setData({ savedReadingsLoading: true });
    try {
      // Fetch each saved reading's detail from API (limit to 20 for perf)
      const batch = savedIds.slice(0, 20);
      const results = await Promise.allSettled(
        batch.map(id => request(`/readings/${id}`))
      );
      const readings = results
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value)
        .filter(Boolean)
        .map(item => ({
          ...item,
          spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type || '占卜',
          createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
        }));
      this.setData({ savedReadings: readings, savedReadingsLoading: false });
    } catch (err) {
      this.setData({ savedReadingsLoading: false });
    }
  },

  async onScrollToBottom() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    const nextPage = this.data.historyPage + 1;
    try {
      const history = await request(`/readings/history?page=${nextPage}&page_size=20`);
      this.setData({
        readingHistory: this.data.readingHistory.concat(
          (history.items || []).map(item => ({
            ...item,
            spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
            firstCardImage: computeCardImage(item.first_card_name),
            createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
          }))
        ),
        historyPage: nextPage,
        hasMore: history.items ? history.items.length >= 20 : false,
        loadingMore: false,
      });
    } catch (err) {
      this.setData({ loadingMore: false });
      wx.showToast({ title: '加载更多失败', icon: 'none' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadData();
  },

  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onGoToReading() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onViewReading(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/reading-result/reading-result?id=${id}` });
  },

  onGoFavorites() {
    // Use globalData to signal favorites filter since switchTab doesn't support query params
    const app = getApp();
    app.globalData.showCardFavorites = true;
    wx.switchTab({ url: '/pages/encyclopedia/encyclopedia' });
  },

  onGoDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  onGoAnnualReport() {
    wx.navigateTo({ url: '/pages/annual-report/annual-report' });
  },

  onGoAbout() {
    wx.showModal({
      title: '关于我们',
      content: '星光塔罗 — 用星辰的智慧指引你的前行之路。\n\n版本 1.0.0',
      showCancel: false,
    });
  },

  onToggleSound() {
    const newVal = sound.toggleSfx();
    this.setData({ soundEnabled: newVal });
    wx.showToast({
      title: newVal ? '音效已开启' : '音效已关闭',
      icon: 'none',
      duration: 1500,
    });
  },

  onToggleDrawMode() {
    const currentMode = this.data.defaultDrawMode;
    const newMode = currentMode === 'immersive' ? 'quick' : 'immersive';
    wx.setStorageSync('default_draw_mode', newMode);
    this.setData({ defaultDrawMode: newMode });
    wx.showToast({
      title: newMode === 'immersive' ? '已切换为沉浸解读' : '已切换为快速抽牌',
      icon: 'none',
      duration: 1500,
    });
  },

  async onClearHistory() {
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: '清除记录',
        content: '确定清除所有占卜历史记录吗？此操作不可恢复。',
        success: resolve,
      });
    });
    if (!res.confirm) return;

    try {
      await request('/readings/history', { method: 'DELETE' });
      this.setData({ readingHistory: [] });
      wx.showToast({ title: '已清除', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '清除失败', icon: 'none' });
    }
  },

  onClearSavedReadings() {
    wx.showModal({
      title: '清除收藏',
      content: '确定清除所有收藏的解读吗？',
      success: (res) => {
        if (!res.confirm) return;
        wx.setStorageSync('saved_readings', []);
        this.setData({ savedReadings: [] });
        wx.showToast({ title: '已清除', icon: 'success' });
      },
    });
  },
});
