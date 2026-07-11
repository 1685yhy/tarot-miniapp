// pages/annual-report/annual-report.js
const { request } = require('../../utils/api');

Page({
  data: {
    report: null,
    loading: true,
    generating: false,
  },

  async onLoad() {
    // Don't auto-generate, let user trigger it
    this.setData({ loading: false });
  },

  async onGenerate() {
    this.setData({ generating: true });
    try {
      const report = await request('/report/annual');
      this.setData({ report, generating: false });
    } catch (err) {
      this.setData({ generating: false });
      if (err.message.includes('402')) {
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

  onShare() {
    wx.showShareMenu({ withShareTicket: true });
  },
});
