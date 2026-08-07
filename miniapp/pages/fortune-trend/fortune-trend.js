// pages/fortune-trend/fortune-trend.js
// 牌运曲线 — 个人数据资产（留存功能第一批 · 功能 2）
const { request, getFriendlyError } = require('../../utils/api');

// 花色展示元数据（与后端 suit_dist 键一致）
const SUIT_META = [
  { key: 'wands', name: '权杖', emoji: '🔥' },
  { key: 'cups', name: '圣杯', emoji: '💧' },
  { key: 'swords', name: '宝剑', emoji: '🌬' },
  { key: 'pentacles', name: '星币', emoji: '⛰' },
];

Page({
  data: {
    loading: true,
    error: null,
    days: 30,
    totalReadings: 0,
    activeDays: 0,
    mood: '',
    topCards: [],
    majorCount: 0,
    minorCount: 0,
    majorPct: 0,
    suitList: [],
    trend: [],
    hasData: false,
    nickname: '星光旅人',
    // 分享海报
    showPoster: false,
    posterData: null,
    sharing: false,
  },

  onLoad() {
    this._load();
  },

  async _load() {
    this.setData({ loading: true, error: null });
    try {
      const data = await request('/readings/fortune-trend?days=30');

      const totalReadings = data.total_readings || 0;
      const majorCount = (data.arcana_dist && data.arcana_dist.major) || 0;
      const minorCount = (data.arcana_dist && data.arcana_dist.minor) || 0;
      const totalCards = majorCount + minorCount;
      const majorPct = totalCards > 0 ? Math.round((majorCount / totalCards) * 100) : 0;

      const suitList = SUIT_META.map(s => ({
        key: s.key,
        name: s.name,
        emoji: s.emoji,
        count: (data.suit_dist && data.suit_dist[s.key]) || 0,
      }));

      // 趋势 → 柱状图（高度按最大值归一化；无记录的天显示占位矮柱）
      const rawTrend = data.trend || [];
      const maxCount = rawTrend.reduce((m, t) => Math.max(m, t.count || 0), 0) || 1;
      // 30 根柱时日期标签只标首/中/末，避免重叠
      const labelEvery = rawTrend.length > 15 ? 5 : 1;
      const trend = rawTrend.map((t, i) => ({
        date: t.date || '',
        dayLabel: t.date ? t.date.slice(5) : '', // "MM-DD"
        showLabel: i % labelEvery === 0 || i === rawTrend.length - 1,
        count: t.count || 0,
        heightPct: Math.max(4, Math.round(((t.count || 0) / maxCount) * 100)),
      }));
      const activeDays = trend.filter(t => t.count > 0).length;

      const user = wx.getStorageSync('user') || {};
      this.setData({
        loading: false,
        days: data.days || 30,
        totalReadings,
        activeDays,
        mood: data.mood || '',
        topCards: (data.cards || []).slice(0, 3),
        majorCount,
        minorCount,
        majorPct,
        suitList,
        trend,
        hasData: totalReadings > 0,
        nickname: user.nickname || '星光旅人',
      });
    } catch (err) {
      this.setData({ loading: false, error: getFriendlyError(err) });
    }
  },

  onRetry() {
    this._load();
  },

  /** 生成牌运分享图 — 走现有 canvas-poster 机制（share-poster 组件 · fortune 模式） */
  onShareFortune() {
    if (this.data.sharing) return;
    if (!this.data.hasData) {
      wx.showToast({ title: '先来抽一次牌，牌运才有迹可循 ✦', icon: 'none', duration: 2500 });
      return;
    }
    this.setData({ sharing: true });
    const d = new Date();
    const dateText = `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
    this.setData({
      posterData: {
        dateText,
        totalReadings: this.data.totalReadings,
        activeDays: this.data.activeDays,
        mood: this.data.mood,
        cards: this.data.topCards,
        majorCount: this.data.majorCount,
        minorCount: this.data.minorCount,
        suitList: this.data.suitList,
        trend: this.data.trend,
      },
      showPoster: true,
      sharing: false,
    });
  },

  onClosePoster() {
    this.setData({ showPoster: false });
  },

  /** 分享牌运海报给朋友 */
  onSharePosterToFriend(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: '星光映照 · 我的牌运',
      });
    } catch (err) {
      wx.showToast({
        title: '请先保存海报，再从相册分享',
        icon: 'none',
        duration: 2000,
      });
    }
  },
});
