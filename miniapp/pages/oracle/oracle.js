// pages/oracle/oracle.js
// 神谕主屏（简版）：星图三要素卡（真实星盘计算 · 开发 05）+ 深度报告入口 + 牌阵馆 + 百科
// 数据：GET /user/birthchart（utils/birthchart 缓存层）；缺失 → birth-info 引导
const { getZodiacBadge } = require('../../utils/energy');
const { fetchBirthchart, getCachedChart, missingHint } = require('../../utils/birthchart');
const analytics = require('../../utils/analytics');

/**
 * 牌阵馆 6 卡（与 reading.js SPREADS 的 key 一一对应，点击直达提问页）。
 * 三牌/恋人三角/事业/财运 4 卡网格 + 二择一/凯尔特十字 2 行宽卡（与原型页 07 一致）。
 */
const SPREADS = [
  { type: 'three_card', name: '三牌占卜', ic: '🕯️', desc: '过去 · 现在 · 未来', tag: '免费', wide: false },
  { type: 'triangle', name: '恋人三角', ic: '💕', desc: '感情关系深度分析', tag: '爱情', wide: false },
  { type: 'career', name: '事业牌阵', ic: '💼', desc: '职业发展方向指引', tag: '事业', wide: false },
  { type: 'finance', name: '财运牌阵', ic: '💰', desc: '财务状况趋势分析', tag: '财运', wide: false },
  { type: 'decision', name: '二择一', ic: '🔀', desc: '两难选择的明灯 · 帮你理清利弊', tag: '', wide: true },
  { type: 'celtic_cross', name: '凯尔特十字', ic: '✝️', desc: '最全面的深度占卜 · 10 张牌全方位剖析', tag: '会员', wide: true },
];

function fmtDate() {
  const d = new Date();
  const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
  const DAYS = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
  return `${MONTHS[d.getMonth()]} ${d.getDate()} · ${DAYS[d.getDay()]} · ${d.getFullYear()}`;
}

function moonPhase() {
  const d = new Date();
  const phases = ['新月', '娥眉月', '上弦月', '盈凸月', '满月', '亏凸月', '下弦月', '残月'];
  const idx = Math.floor(((d.getDate() + 13) % 30) / 4);
  return phases[idx] || '上弦月';
}

/** 未点亮占位卡（未填出生日期时三张卡统一引导） */
const PLACEHOLDER_CARDS = [
  { key: 'sun', icon: '☀', name: '太阳 · 未点亮', line: '填写出生日期，点亮你的核心动力', locked: true },
  { key: 'moon', icon: '☽', name: '月亮 · 未点亮', line: '月亮落在哪一宫，等你来揭晓', locked: true },
  { key: 'rising', icon: '✦', name: '上升 · 未点亮', line: '补全出生时间解锁上升 ✦', locked: true },
];

Page({
  data: {
    dateText: '',
    moonPhase: '',
    zodiacBadge: '',
    elements: [],       // 真实三要素卡（缺失 → 占位/锁卡）
    needsBirth: false,  // 未填出生日期 → 点击引导
    lockedRising: false,
    hintText: '',
    spreads: SPREADS,   // 牌阵馆 6 卡（回归修复：开发05重构时误删 data 绑定，导致牌阵馆空白）
  },

  onLoad() {
    this.setData({
      dateText: fmtDate(),
      moonPhase: moonPhase(),
    });
  },

  onShow() {
    // 徽章与今日页联动（用户可能在设置里改了星座）
    const badge = getZodiacBadge();
    if (badge !== this.data.zodiacBadge) {
      this.setData({ zodiacBadge: badge });
    }
    this._loadChart();
  },

  /** 拉取真实星盘三要素（本地缓存先渲染，再异步刷新） */
  async _loadChart() {
    const cached = getCachedChart();
    if (cached && (cached.sun || cached.moon || cached.rising)) {
      this._render(cached);
    }
    const chart = await fetchBirthchart({ force: true });
    this._render(chart);
  },

  _render(chart) {
    if (!chart) return;
    const elements = [];
    const hint = missingHint(chart);
    const needsBirth = !chart.birth || !chart.birth.date;

    if (needsBirth) {
      this.setData({ elements: PLACEHOLDER_CARDS, needsBirth: true, lockedRising: false, hintText: hint.text });
      return;
    }
    ['sun', 'moon', 'rising'].forEach((role) => {
      const el = chart[role];
      if (!el) return;
      elements.push({
        key: role,
        icon: el.icon,
        name: el.displayName,
        line: el.line,
        approx: el.approx,
        locked: false,
      });
    });
    this.setData({
      elements,
      needsBirth: false,
      lockedRising: !!hint.route && !chart.rising,
      hintText: hint.text,
    });
  },

  /** 三要素卡：真实卡 → 详解页；未点亮/锁卡 → 出生信息引导 */
  onGoElement(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    const el = this.data.elements.find((x) => x.key === key);
    try { wx.vibrateShort({ type: 'light' }); } catch (err) { /* silent */ }
    if (!el || el.locked || !this.data.elements.length) {
      // 未点亮（未填出生日期）→ 出生信息引导
      analytics.trackEvent('oracle_element_to_birth_info', { element: key });
      wx.navigateTo({ url: '/pages/birth-info/birth-info' });
      return;
    }
    analytics.trackEvent('oracle_element_detail_open', { element: key });
    wx.navigateTo({ url: `/pages/element-detail/element-detail?key=${key}&from=oracle` });
  },

  /** 深度星图报告：二期已上线（会员免费 / 19.9 解锁） */
  onDeepReport() {
    analytics.trackEvent('oracle_deep_report_enter', {});
    wx.navigateTo({ url: '/pages/birthchart-report/birthchart-report' });
  },

  /** 牌阵馆卡片 → 提问页 */
  onGoSpread(e) {
    const type = e.currentTarget.dataset.type;
    if (!type) return;
    analytics.trackEvent('oracle_spread_enter', { type, source: 'oracle_spread_hall' });
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },

  /** 卡牌百科入口 */
  onGoEncyclopedia() {
    analytics.trackEvent('oracle_encyclopedia_enter', {});
    wx.navigateTo({ url: '/pages/encyclopedia/encyclopedia' });
  },

  /** 星座徽章 → 修改星座 */
  onGoZodiac() {
    wx.navigateTo({ url: '/pages/zodiac-welcome/zodiac-welcome?from=change' });
  },
});
