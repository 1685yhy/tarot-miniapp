// pages/element-detail/element-detail.js
// 三要素详情（神谕主屏/星盘页点击进入）：主角=该要素
// 数据：真实星盘（GET /user/birthchart 缓存）→ 天赋/阴影/今年主题 + 深度报告入口
// 深度报告（开发 05）：会员免费 / 19.9 解锁 → 支付流程在 birthchart-report 页
const { fetchBirthchart, getCachedChart, missingHint } = require('../../utils/birthchart');
const { checkLogin } = require('../../utils/auth');
const analytics = require('../../utils/analytics');

/** 深度报告三档（与原型页 06 一致 · 当前 19.9 档解锁完整报告） */
const TIERS = [
  { name: '星盘速览', desc: '三要素精讲 · 2 页图文', price: '19.9' },
  { name: '性格深度报告', desc: '12 页图文 · 附行动建议', price: '29.9' },
  { name: '年度星运指南', desc: '未来 12 个月 · 逐月轨迹', price: '39.9' },
];

Page({
  data: {
    el: null,          // 当前要素（真实数据或 mock 兜底）
    tiers: TIERS,
    loaded: false,
    locked: false,     // 未填出生信息 / 该要素未解锁
    needsBirth: false,
    isMember: false,
    birthchartPaid: false,
  },

  async onLoad(options) {
    const key = options && options.key;

    // 先渲染本地缓存（快速），再异步刷新
    const cached = getCachedChart();
    if (cached && cached.birth && cached.birth.date) {
      this._buildEl(key, cached);
    }
    await this._load(key);
  },

  async _load(key) {
    const chart = await fetchBirthchart({ force: true });
    const built = this._buildEl(key, chart);
    if (!built) return;

    // 权益状态（详情页底部展示 已解锁/会员免费）
    try {
      const user = await checkLogin({ refresh: true });
      this.setData({ isMember: !!(user && user.is_member), birthchartPaid: !!(user && user.birthchart_paid) });
    } catch (err) { /* silent */ }
  },

  /** 用真实星盘数据构建该要素；返回 false 表示需要引导 */
  _buildEl(key, chart) {
    if (!key || !chart || !chart.birth || !chart.birth.date) {
      this.setData({ loaded: true, el: null, needsBirth: true });
      analytics.trackEvent('element_detail_no_birth', { element: key });
      return false;
    }
    const real = chart[key];
    if (!real) {
      // 该要素未解锁（如缺出生时间 → 上升）
      const hint = missingHint(chart);
      this.setData({ loaded: true, el: null, locked: true, lockedText: hint.text || '补全出生时间解锁 ✦' });
      analytics.trackEvent('element_detail_locked', { element: key });
      return false;
    }

    const detail = real.detail || {};
    const el = {
      key,
      sign: real.sign || '✦',
      name: real.displayName || `${real.name}`,
      line: real.line || '',
      approx: real.approx,
      talent: detail.talent || '',
      shadow: detail.shadow || '',
      theme: detail.theme || '',
    };
    this.setData({ el, loaded: true, locked: false, needsBirth: false });
    wx.setNavigationBarTitle({ title: el.name });
    analytics.trackEvent('element_detail_view', { element: key });
    return true;
  },

  /** 深度报告三档 → 深度报告页（会员免费 / 19.9 解锁） */
  onTierTap(e) {
    const idx = e.currentTarget.dataset.idx;
    const tier = TIERS[idx];
    analytics.trackEvent('element_deep_report_tier', { tier: tier ? tier.name : '' });
    if (idx > 0) {
      // 29.9/39.9 档为进阶展示：当前 19.9 解锁完整报告
      wx.showModal({
        title: tier.name,
        content: '当前版本 19.9 元即可解锁完整深度星图报告（性格底色 / 关系模式 / 年度主题 / 牌面建议）✦',
        confirmText: '去解锁',
        cancelText: '再想想',
        success: (res) => {
          if (res.confirm) this._goReport();
        },
      });
      return;
    }
    this._goReport();
  },

  /** 深度报告整体入口 */
  onDeepReport() {
    analytics.trackEvent('element_deep_report_placeholder', {});
    this._goReport();
  },

  _goReport() {
    analytics.trackEvent('element_to_deep_report', {});
    wx.navigateTo({ url: '/pages/birthchart-report/birthchart-report' });
  },

  /** 未填出生信息 → 引导 */
  onGoBirthInfo() {
    analytics.trackEvent('element_detail_to_birth_info', {});
    wx.navigateTo({ url: '/pages/birth-info/birth-info' });
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
  },
});
