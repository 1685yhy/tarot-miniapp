// pages/oracle/oracle.js
// 神谕主屏（简版）：星图三要素卡（点击 → 详情页）+ 深度报告占位 + 牌阵馆 6 卡 + 百科入口
// 深度内容（三要素详情页）见 pages/element-detail/
const { getZodiacBadge } = require('../../utils/energy');
const { ELEMENTS } = require('../../utils/elements');
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

Page({
  data: {
    dateText: '',
    moonPhase: '',
    zodiacBadge: '',
    elements: ELEMENTS,
    spreads: SPREADS,
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
  },

  /** 三要素卡：点击 → 三要素详情页（主角=该要素） */
  onGoElement(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    try { wx.vibrateShort({ type: 'light' }); } catch (err) { /* silent */ }
    analytics.trackEvent('oracle_element_detail_open', { element: key });
    wx.navigateTo({ url: `/pages/element-detail/element-detail?key=${key}` });
  },

  /** 深度星图报告：占位入口（二期） */
  onDeepReport() {
    analytics.trackEvent('oracle_deep_report_placeholder', {});
    wx.showToast({ title: '深度星图报告 · 二期解锁 ✦', icon: 'none', duration: 2000 });
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
