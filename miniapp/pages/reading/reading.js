// pages/reading/reading.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

const SPREADS = [
  { key: 'three_card', name: '三牌占卜', icon: '🕯️', desc: '过去·现在·未来', cards: 3, popular: true },
  { key: 'triangle', name: '恋人三角', icon: '💕', desc: '感情关系深度分析', cards: 4, theme: 'love' },
  { key: 'career', name: '事业牌阵', icon: '💼', desc: '职业发展方向指引', cards: 5, theme: 'career' },
  { key: 'finance', name: '财运牌阵', icon: '💰', desc: '财务状况趋势分析', cards: 4, theme: 'finance' },
  { key: 'decision', name: '二择一', icon: '🔀', desc: '两难选择的明灯', cards: 5 },
  { key: 'celtic_cross', name: '凯尔特十字', icon: '✝️', desc: '最全面的深度占卜', cards: 10, premium: true },
  { key: 'life_cross', name: '人生十字', icon: '⭐', desc: '人生方向的十字路口', cards: 5 },
  { key: 'horseshoe', name: '马蹄牌阵', icon: '🧲', desc: '七步看清局势', cards: 7, premium: true },
  { key: 'relationship', name: '关系牌阵', icon: '🤝', desc: '双人关系全面透视', cards: 7, premium: true },
  { key: 'year_ahead', name: '年度运势', icon: '📅', desc: '未来12个月逐月详解', cards: 13, premium: true },
];

Page({
  data: {
    spreads: SPREADS,
    selectedSpread: null,
    question: '',
    theme: '',
    showQuestionInput: false,
    isDrawing: false,
    pageLoading: false,
    pageError: null,
  },

  onSelectSpread(e) {
    const spread = e.currentTarget.dataset.spread;
    this.setData({
      selectedSpread: spread,
      theme: spread.theme || '',
      showQuestionInput: true,
    });
  },

  onQuestionInput(e) {
    this.setData({ question: e.detail.value });
  },

  onThemeTap(e) {
    this.setData({ theme: e.currentTarget.dataset.theme });
  },

  onBackToSpreads() {
    this.setData({ selectedSpread: null, showQuestionInput: false, question: '' });
  },

  onRetry() {
    this.setData({ pageError: null });
  },

  async onStartReading() {
    const { selectedSpread } = this.data;
    if (!selectedSpread) return;

    // Check login first
    try {
      await checkLogin();
    } catch (err) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    this.setData({ isDrawing: true });

    try {
      const result = await request(`/readings/spread/${selectedSpread.key}`, {
        method: 'POST',
        data: {
          spread_type: selectedSpread.key,
          question: this.data.question || null,
          theme: this.data.theme || 'general',
        },
      });

      // Navigate to result page with reading ID
      wx.redirectTo({
        url: `/pages/reading-result/reading-result?id=${result.id}`,
      });
    } catch (err) {
      this.setData({ isDrawing: false });
      if (err.message.includes('402')) {
        wx.showModal({
          title: '次数不足',
          content: '今日免费次数已用完，开通会员享无限解读',
          confirmText: '开通会员',
          success: (res) => {
            if (res.confirm) {
              wx.navigateTo({ url: '/pages/membership/membership' });
            }
          },
        });
      } else {
        wx.showToast({ title: '占卜失败，请重试', icon: 'none' });
      }
    }
  },
});
