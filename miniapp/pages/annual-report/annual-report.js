// pages/annual-report/annual-report.js
const { request } = require('../../utils/api');

Page({
  data: {
    report: null,
    pageLoading: true,
    pageError: null,
    generating: false,
  },

  async onLoad() {
    // Try to load cached report first
    try {
      const cached = wx.getStorageSync('annual_report');
      if (cached && cached.generated_at) {
        this.setData({ report: cached, pageLoading: false });
        return;
      }
    } catch (_) { /* ignore cache read errors */ }
    this.setData({ pageLoading: false });
  },

  async onGenerate() {
    this.setData({ generating: true });
    try {
      const report = await request('/report/annual');
      this.setData({ report, generating: false });
      // Cache to local storage so next visit doesn't re-generate
      wx.setStorageSync('annual_report', report);
    } catch (err) {
      this.setData({ generating: false });
      if (err.statusCode === 402) {
        wx.showModal({
          title: '会员专属',
          content: '年度运势报告仅限会员使用',
          confirmText: '开通会员',
          success: (res) => {
            if (res.confirm) {
              wx.navigateTo({ url: '/pages/membership/membership' });
            }
          },
        });
      } else {
        wx.showToast({ title: '生成失败', icon: 'none' });
      }
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  onCardPreview(e) {
    const idx = e.currentTarget.dataset.cardidx;
    const card = this.data.report.cards[idx];
    if (!card) return;
    wx.showModal({
      title: `${card.month} · ${card.card_name}`,
      content: `${card.direction}\n\n${card.meaning || '暂无详细解读'}`,
      showCancel: false,
    });
  },

  onBuySingle() {
    wx.navigateTo({ url: '/pages/membership/membership?product=annual_report' });
  },

  onShareAppMessage() {
    return {
      title: '我的塔罗年度运势报告 —— 来看看未来12个月的运势吧',
      desc: 'AI塔罗年度运势报告',
    };
  },

  onShare() {
    wx.showShareMenu({ withShareTicket: true });
  },
});
