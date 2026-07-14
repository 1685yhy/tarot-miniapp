// pages/index/index.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    dailyCard: null,
    pageLoading: true,
    pageError: null,
    drawingLoading: false,
    rippleActive: false,
    shaking: false,
  },

  async onLoad() {
    try {
      await checkLogin();
      this.setData({ pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  async drawDailyCard() {
    if (this.data.drawingLoading) return;
    this.setData({ drawingLoading: true });

    // --- Haptic & visual feedback ---
    wx.vibrateShort({ type: 'light' }).catch(() => {});

    // 1. Ripple burst from center (animation: 0.6s via .ripple-run)
    this.setData({ rippleActive: true });
    // 2. Shake — brief shuffle feel (animation: 0.3s via .card-shake-fx)
    this.setData({ shaking: true });

    // Let the shake animation play for its full 0.3s duration,
    // then clean up. The ripple (0.6s) cleans up on its own timeout.
    this._shakeTimer = setTimeout(() => { this.setData({ shaking: false }); }, 300);
    this._rippleTimer = setTimeout(() => { this.setData({ rippleActive: false }); }, 650);

    // Brief pause before API call so the user sees the initial animation frames
    await new Promise(r => setTimeout(r, 200));

    wx.showLoading({ title: '抽取中...' });
    try {
      // Small extra delay (300ms) so the pre-draw state lingers,
      // making the wx:if→wx:else switch feel like a reveal transition
      await new Promise(r => setTimeout(r, 300));
      const card = await request('/cards/daily');
      this.setData({ dailyCard: card, drawingLoading: false });
      wx.hideLoading();
      // 保存到globalData供详情页使用
      getApp().globalData.dailyCard = card;
    } catch (err) {
      this.setData({ drawingLoading: false });
      this._shakeTimer && clearTimeout(this._shakeTimer);
      this._rippleTimer && clearTimeout(this._rippleTimer);
      this.setData({ rippleActive: false, shaking: false });
      wx.hideLoading();
      wx.showToast({ title: '抽取失败，请重试', icon: 'none' });
    }
  },

  navigateToReading(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },

  goToAllSpreads() {
    wx.navigateTo({ url: '/pages/reading/reading' });
  },

  onUnload() {
    this._shakeTimer && clearTimeout(this._shakeTimer);
    this._rippleTimer && clearTimeout(this._rippleTimer);
  },
});
