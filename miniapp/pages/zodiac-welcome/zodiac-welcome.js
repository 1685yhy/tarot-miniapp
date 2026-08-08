// pages/zodiac-welcome/zodiac-welcome.js
// 首次使用：12 星座网格引导（可跳过）｜设置/今日徽章进入：改星座（from=change）
const { ZODIACS, ZODIAC_BY_NAME } = require('../../utils/energy');
const { request } = require('../../utils/api');
const analytics = require('../../utils/analytics');

Page({
  data: {
    isChange: false,        // from=change：改星座模式（带返回）
    zodiacs: ZODIACS,       // 12 星座（含日期区间）
    selected: '',           // 选中星座名
  },

  onLoad(options) {
    const isChange = options && options.from === 'change';
    wx.setNavigationBarTitle({ title: isChange ? '我的星座' : '初次见面' });
    let current = '';
    try { current = wx.getStorageSync('zodiac_sign') || ''; } catch (e) { /* silent */ }
    if (isChange && current) {
      this.setData({ selected: current });
    }
    this.setData({ isChange });
    if (isChange) {
      analytics.trackEvent('zodiac_change_open', {});
    } else {
      analytics.trackEvent('zodiac_welcome_show', {});
    }
  },

  onSelect(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    this.setData({ selected: name });
    try { wx.vibrateShort({ type: 'light' }); } catch (err) { /* silent */ }
  },

  /** 选择后确认（引导模式：开始旅程 · 改星座模式：保存） */
  onConfirm() {
    const name = this.data.selected;
    if (!name) return;
    const z = ZODIAC_BY_NAME[name];
    if (!z) return;

    wx.setStorageSync('zodiac_sign', name);
    wx.setStorageSync('zodiac_onboarding_done', true);
    wx.setStorageSync('onboarding_completed', true);
    wx.removeStorageSync('onboarding_step');

    // 上报星座到服务端（POST /user/zodiac · 失败不阻塞页面流程）
    this._reportZodiac(z.key);

    if (this.data.isChange) {
      analytics.trackEvent('zodiac_changed', { sign: name });
      wx.showToast({ title: `已更新为 ${z.emoji} ${name} ✦`, icon: 'none', duration: 1800 });
      setTimeout(() => wx.navigateBack({ delta: 1 }), 600);
    } else {
      analytics.trackEvent('zodiac_selected', { sign: name });
      wx.switchTab({ url: '/pages/index/index' });
    }
  },

  /** 星座上报：失败静默（能量引擎可用兜底星座） */
  _reportZodiac(key) {
    request('/user/zodiac', {
      method: 'POST',
      data: { zodiac: key },
    }).then(() => {
      analytics.trackEvent('zodiac_reported', { sign: key });
    }).catch(() => {
      // 静默：不上报不阻塞引导/跳转
    });
  },

  /** 跳过（仅引导模式）：先随便逛逛，设置里可随时补 */
  onSkip() {
    wx.setStorageSync('zodiac_onboarding_done', true);
    wx.setStorageSync('onboarding_completed', true);
    wx.removeStorageSync('onboarding_step');
    analytics.trackEvent('zodiac_skipped', {});
    wx.switchTab({ url: '/pages/index/index' });
  },

  /** 改星座模式：返回 */
  onBack() {
    wx.navigateBack({ delta: 1 });
  },
});
