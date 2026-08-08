// pages/birthchart/birthchart.js
// 本命星盘页（开发 05）：三要素水彩卡（太阳/月亮/上升）+ 缺失提示 + 深度报告入口
// 数据：GET /user/birthchart（utils/birthchart 缓存层）
const { fetchBirthchart, getCachedChart, missingHint } = require('../../utils/birthchart');
const analytics = require('../../utils/analytics');

const ROLE_META = {
  sun: { icon: '☀', sub: '核心动力' },
  moon: { icon: '☽', sub: '情绪底色' },
  rising: { icon: '✦', sub: '他人眼中的我' },
};

Page({
  data: {
    loading: true,
    cards: [],          // [{key, icon, name, line, approx, detail}]
    lockedRising: null, // 未填出生时间时上升占位卡
    needBirth: false,   // 未填出生日期 → 引导
    hint: '',           // 缺失提示文案
    hasChart: false,
    sun: null,
    moon: null,
    rising: null,
    message: '',
  },

  async onLoad() {
    // 先渲染本地缓存，再异步刷新
    const cached = getCachedChart();
    if (cached && cached.birth && cached.birth.date) {
      this._render(cached, false);
    }
    this._load();
    analytics.trackEvent('birthchart_page_open', {});
  },

  onShow() {
    this._load();
  },

  async _load() {
    this.setData({ loading: true });
    const chart = await fetchBirthchart({ force: true });
    this._render(chart, true);
    this.setData({ loading: false });
  },

  _render(chart, fromApi) {
    const cards = [];
    ['sun', 'moon', 'rising'].forEach((role) => {
      const el = chart[role];
      if (!el) return;
      const meta = ROLE_META[role];
      cards.push({
        key: role,
        icon: el.icon || meta.icon,
        name: el.displayName || `${meta.sub} · —`,
        line: el.line || '',
        approx: !!el.approx,
        label: el.label || meta.sub,
        detail: el.detail || null,
      });
    });
    const hint = missingHint(chart);
    this.setData({
      cards,
      lockedRising: chart.rising ? null : { icon: '✦', text: hint.text || '补全出生时间解锁上升 ✦' },
      needBirth: !chart.birth || !chart.birth.date,
      hint: hint.text,
      message: chart.message || '',
      hasChart: !!(chart.sun || chart.moon),
      sun: chart.sun,
      moon: chart.moon,
      rising: chart.rising,
      _fromApi: fromApi,
    });
  },

  /** 要素卡 → 详解页（element-detail 复用） */
  onGoDetail(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    try { wx.vibrateShort({ type: 'light' }); } catch (err) { /* silent */ }
    analytics.trackEvent('birthchart_detail_open', { element: key });
    wx.navigateTo({ url: `/pages/element-detail/element-detail?key=${key}&from=birthchart` });
  },

  /** 缺失卡 / 引导 → 出生信息页 */
  onGoBirthInfo() {
    analytics.trackEvent('birthchart_to_birth_info', {});
    wx.navigateTo({ url: '/pages/birth-info/birth-info' });
  },

  /** 深度报告入口 */
  onDeepReport() {
    analytics.trackEvent('birthchart_deep_report_enter', {});
    wx.navigateTo({ url: '/pages/birthchart-report/birthchart-report' });
  },

  onShareAppMessage() {
    return {
      title: this.data.hasChart ? '我的本命星盘：日月升三要素 ✦' : '星光映照 · 看看你的本命星盘',
      path: '/pages/birthchart/birthchart',
    };
  },
});
