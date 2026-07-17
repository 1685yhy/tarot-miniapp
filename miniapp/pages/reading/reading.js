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
    ritualStage: null,   // null = not in ritual, 0 = meditation, 1 = shuffle, 2 = question
    isDrawing: false,
    pageLoading: true,
    pageError: null,
  },

  _timers: [],

  onLoad(options) {
    // 首页点击牌阵直接进入问答，跳过选择页
    const type = (options && options.type) || '';
    if (type) {
      const spread = SPREADS.find(s => s.key === type);
      if (spread) {
        // 先设置数据，再处理会员检查
        this.setData({
          selectedSpread: spread,
          theme: spread.theme || '',
          showQuestionInput: false,
          pageLoading: false,
        });
        // 会员牌阵需要登录检查
        if (spread.premium) {
          checkLogin({ refresh: true }).then(user => {
            if (user && user.is_member) {
              this._startRitual();
            } else {
              wx.showModal({
                title: '会员专属',
                content: `「${spread.name}」为会员专属牌阵，开通会员即可使用`,
                confirmText: '开通会员',
                cancelText: '取消',
                success: (res) => {
                  if (res.confirm) wx.navigateTo({ url: '/pages/membership/membership' });
                },
              });
            }
          }).catch(() => {
            wx.showToast({ title: '请先登录', icon: 'none' });
          });
        } else {
          this._startRitual();
        }
      }
    }
    // 清除骨架屏（pageLoading 初始为 true，确保首次渲染骨架）
    this.setData({ pageLoading: false });
  },

  onUnload() {
    this._clearTimers();
  },

  /* ========== Ritual Flow ========== */

  _clearTimers() {
    this._timers.forEach(t => clearTimeout(t));
    this._timers = [];
  },

  _setTimer(fn, ms) {
    const id = setTimeout(fn, ms);
    this._timers.push(id);
    return id;
  },

  _startRitual() {
    this._clearTimers();
    this.setData({ ritualStage: 0 });

    // Auto-advance from meditation after 6s
    this._setTimer(() => {
      if (this.data.ritualStage === 0) {
        this._advanceRitual();
      }
    }, 6000);
  },

  _advanceRitual() {
    this._clearTimers();
    const stage = this.data.ritualStage;

    if (stage === 0) {
      // Move to shuffle
      this.setData({ ritualStage: 1 });
      // Auto-advance from shuffle after 2s
      this._setTimer(() => {
        if (this.data.ritualStage === 1) {
          this._advanceRitual();
        }
      }, 2000);
    } else if (stage === 1) {
      // Move to question
      this.setData({ ritualStage: 2 });
    }
  },

  // User tap to skip current stage or advance
  onRitualTap() {
    this._advanceRitual();
  },

  async onSelectSpread(e) {
    const spread = e.currentTarget.dataset.spread;

    // Premium spreads require membership
    if (spread.premium) {
      try {
        const user = await checkLogin({ refresh: true });
        if (user && !user.is_member) {
          wx.showModal({
            title: '会员专属',
            content: `「${spread.name}」为会员专属牌阵，开通会员即可使用`,
            confirmText: '开通会员',
            cancelText: '取消',
            success: (res) => {
              if (res.confirm) {
                wx.navigateTo({ url: '/pages/membership/membership' });
              }
            },
          });
          return;
        }
      } catch(e) {
        wx.showToast({ title: '请先登录', icon: 'none' });
        return;
      }
    }

    this.setData({
      selectedSpread: spread,
      theme: spread.theme || '',
      showQuestionInput: false,
    });

    this._startRitual();
  },

  onQuestionInput(e) {
    this.setData({ question: e.detail.value });
  },

  onThemeTap(e) {
    this.setData({ theme: e.currentTarget.dataset.theme });
  },

  onBackToSpreads() {
    this._clearTimers();
    this.setData({ selectedSpread: null, showQuestionInput: false, ritualStage: null, question: '' });
  },

  onRetry() {
    this._clearTimers();
    this.setData({ pageError: null, isDrawing: false, selectedSpread: null, showQuestionInput: false, ritualStage: null });
  },

  async onStartReading() {
    const { selectedSpread, isDrawing } = this.data;
    if (!selectedSpread) return;
    if (isDrawing) return;

    this.setData({ isDrawing: true });

    // Check login first
    try {
      await checkLogin();
    } catch (err) {
      this.setData({ isDrawing: false });
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

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
      if (err.statusCode === 402) {
        this.setData({ isDrawing: false });
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
        this.setData({ isDrawing: false, pageError: err.message || '占卜失败' });
      }
    }
  },
});
