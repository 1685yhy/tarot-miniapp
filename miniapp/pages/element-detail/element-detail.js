// pages/element-detail/element-detail.js
// 三要素详情（神谕主屏点击三要素卡进入）：主角=该要素
// 天赋 / 阴影 / 今年主题 + 深度报告付费占位（19.9 / 29.9 / 39.9 · 二期上线）
const { getElement, ELEMENTS } = require('../../utils/elements');
const analytics = require('../../utils/analytics');

/** 深度报告三档（与原型页 06 一致 · 二期接入支付与真实报告） */
const TIERS = [
  { name: '星盘速览', desc: '三要素精讲 · 2 页图文', price: '19.9' },
  { name: '性格深度报告', desc: '12 页图文 · 附行动建议', price: '29.9' },
  { name: '年度星运指南', desc: '未来 12 个月 · 逐月轨迹', price: '39.9' },
];

Page({
  data: {
    el: null,     // 当前要素（详情数据）
    tiers: TIERS,
    loaded: false,
  },

  onLoad(options) {
    const key = options && options.key;
    const el = getElement(key);
    this.setData({ el, loaded: true });
    wx.setNavigationBarTitle({ title: el.name });
    analytics.trackEvent('element_detail_view', { element: el.key });
  },

  /** 深度报告三档：占位（二期上线） */
  onTierTap(e) {
    const idx = e.currentTarget.dataset.idx;
    const tier = TIERS[idx];
    analytics.trackEvent('element_deep_report_tier', { tier: tier ? tier.name : '' });
    wx.showToast({ title: '深度星图报告 · 二期上线 ✦', icon: 'none', duration: 2000 });
  },

  /** 深度报告整体入口（占位） */
  onDeepReport() {
    analytics.trackEvent('element_deep_report_placeholder', {});
    wx.showToast({ title: '深度星图报告 · 二期上线 ✦', icon: 'none', duration: 2000 });
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
  },
});
