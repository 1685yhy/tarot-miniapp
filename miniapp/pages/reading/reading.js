// pages/reading/reading.js
/**
 * ===== Acceptance Criteria: Theme-Spread Consistency =====
 *
 * 1. Each spread in SPREADS has a `defaultTheme` field:
 *    - General spreads (three_card, decision, celtic_cross, life_cross, year_ahead): defaultTheme: null
 *    - Love-themed spreads (triangle, horseshoe, relationship): defaultTheme: 'love'
 *    - Career spread: defaultTheme: 'career'
 *    - Finance spread: defaultTheme: 'finance'
 *
 * 2. When a themed spread is selected:
 *    - Theme auto-sets to the spread's defaultTheme
 *    - Theme selector shows the matching theme pre-selected
 *    - A hint "此牌阵侧重{爱情/事业/财运}解读" is displayed below the label
 *
 * 3. When a general spread is selected:
 *    - User can freely choose any theme
 *    - Defaults to 'general'
 *    - No theme hint displayed
 *
 * 4. For themed spreads, if user switches to a non-matching theme:
 *    - It's allowed (user choice is respected)
 *    - A subtle note "此牌阵更擅长{爱情/事业/财运}解读" replaces the default hint
 *    - No blocking — just informative
 *
 * 5. Home page spread cards with a theme affinity show it as a small tag.
 */
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

const FREE_READINGS_LIMIT = 3; // matches the backend FREE_DAILY_READINGS (should match after backend update)

const SPREADS = [
  { key: 'three_card', name: '三牌占卜', icon: '🕯️', desc: '过去·现在·未来', cards: 3, popular: true, defaultTheme: null },
  { key: 'triangle', name: '恋人三角', icon: '💕', desc: '感情关系深度分析', cards: 4, defaultTheme: 'love' },
  { key: 'career', name: '事业牌阵', icon: '💼', desc: '职业发展方向指引', cards: 5, defaultTheme: 'career' },
  { key: 'finance', name: '财运牌阵', icon: '💰', desc: '财务状况趋势分析', cards: 4, defaultTheme: 'finance' },
  { key: 'decision', name: '二择一', icon: '🔀', desc: '两难选择的明灯', cards: 5, defaultTheme: null },
  { key: 'celtic_cross', name: '凯尔特十字', icon: '✝️', desc: '最全面的深度占卜', cards: 10, premium: true, defaultTheme: null },
  { key: 'life_cross', name: '人生十字', icon: '⭐', desc: '人生方向的十字路口', cards: 5, defaultTheme: null },
  { key: 'horseshoe', name: '马蹄牌阵', icon: '🧲', desc: '七步看清局势', cards: 7, premium: true, defaultTheme: 'love' },
  { key: 'relationship', name: '关系牌阵', icon: '🤝', desc: '双人关系全面透视', cards: 7, premium: true, defaultTheme: 'love' },
  { key: 'year_ahead', name: '年度运势', icon: '📅', desc: '未来12个月逐月详解', cards: 13, premium: true, defaultTheme: null },
];

const THEME_LABELS = {
  love: '爱情',
  career: '事业',
  finance: '财运',
  general: '综合',
};

Page({
  data: {
    spreads: SPREADS,
    selectedSpread: null,
    spreadDefaultTheme: null,
    question: '',
    theme: '',
    themeHint: '',
    showQuestionInput: false,
    ritualStage: null,   // null = not in ritual, 0 = meditation, 1 = shuffle
    ritualEnabled: false,
    isDrawing: false,
    pageLoading: true,
    pageError: null,
    // Free tier display
    freeReadingsUsed: 0,
    freeReadingsTotal: FREE_READINGS_LIMIT,
    isMember: false,
  },

  _timers: [],

  onLoad(options) {
    // 首页点击牌阵直接进入问答，跳过选择页
    const type = (options && options.type) || '';
    if (type) {
      const spread = SPREADS.find(s => s.key === type);
      if (spread) {
        // Check for pending reading context (from home page "继续" flow)
        const pending = wx.getStorageSync('pending_reading');
        let restoredQuestion = '';
        let restoredTheme = '';
        if (pending && pending.spread_type === type) {
          if (!pending.timestamp || Date.now() - pending.timestamp < 24 * 60 * 60 * 1000) {
            restoredQuestion = pending.question || '';
            restoredTheme = pending.theme || '';
          }
          wx.removeStorageSync('pending_reading');
        }

        // Apply default-theme logic
        const defaultTheme = spread.defaultTheme || null;
        const theme = restoredTheme || defaultTheme || 'general';
        const themeHint = defaultTheme
          ? `此牌阵侧重${THEME_LABELS[defaultTheme]}解读`
          : '';

        // 先设置数据，再处理会员检查
        this.setData({
          selectedSpread: spread,
          spreadDefaultTheme: defaultTheme,
          theme: theme,
          themeHint: themeHint,
          question: restoredQuestion,
          showQuestionInput: !spread.premium,
          pageLoading: false,
        });
        // 会员牌阵需要登录检查
        if (spread.premium) {
          checkLogin({ refresh: true }).then(user => {
            if (user && user.is_member) {
              this.setData({ showQuestionInput: true });
            } else {
              this.setData({ showQuestionInput: false });
              wx.showModal({
                title: '会员专属牌阵',
                content: `「${spread.name}」仅限会员使用 ✦ 开通会员即可解锁全部 10 种牌阵，享无限次解读`,
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
        }
      }
    }
    // 清除骨架屏（pageLoading 初始为 true，确保首次渲染骨架）
    this.setData({ pageLoading: false });
    // 加载免费次数信息
    this._loadFreeReadings();
  },

  onShow() {
    // Refresh free reading count when returning from other pages
    if (!this.data.selectedSpread) {
      this._loadFreeReadings();
    }
  },

  /** Load free-reading usage from cached user */
  async _loadFreeReadings() {
    try {
      const user = await checkLogin({ refresh: true });
      if (user) {
        this.setData({
          freeReadingsUsed: user.free_readings_today || 0,
          freeReadingsTotal: FREE_READINGS_LIMIT,
          isMember: !!user.is_member,
        });
        const app = getApp();
        app.globalData.freeReadingsUsed = user.free_readings_today || 0;
        app.globalData.isMember = !!user.is_member;
      }
    } catch (_err) {
      // Silently degrade — counts stay at defaults
    }
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

  _advanceRitual() {
    const stage = this.data.ritualStage;

    if (stage === 0) {
      // Move to shuffle
      this.setData({ ritualStage: 1 });
    } else if (stage === 1) {
      // Ritual complete — return to question input
      this.setData({ ritualStage: null, showQuestionInput: true });
    }
  },

  // User tap to advance ritual stage
  onRitualTap() {
    this._advanceRitual();
  },

  /** Toggle meditation ritual on/off */
  onToggleRitual() {
    this._clearTimers();
    this.setData({
      ritualEnabled: true,
      showQuestionInput: false,
      ritualStage: 0,
    });
  },

  async onSelectSpread(e) {
    const spread = e.currentTarget.dataset.spread;

    // Premium spreads require membership
    if (spread.premium) {
      try {
        const user = await checkLogin({ refresh: true });
        if (user && !user.is_member) {
          wx.showModal({
            title: '会员专属牌阵',
            content: `「${spread.name}」仅限会员使用 ✦ 开通会员即可解锁全部 10 种牌阵，享无限次解读`,
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

    // Apply default-theme logic
    const defaultTheme = spread.defaultTheme || null;
    const theme = defaultTheme || 'general';
    const themeHint = defaultTheme
      ? `此牌阵侧重${THEME_LABELS[defaultTheme]}解读`
      : '';

    // Skip ritual by default — show question input directly
    this.setData({
      selectedSpread: spread,
      spreadDefaultTheme: defaultTheme,
      theme: theme,
      themeHint: themeHint,
      showQuestionInput: true,
    });
  },

  onQuestionInput(e) {
    this.setData({ question: e.detail.value });
  },

  onThemeTap(e) {
    const newTheme = e.currentTarget.dataset.theme;
    const defaultTheme = this.data.spreadDefaultTheme;
    let themeHint = '';

    if (defaultTheme) {
      // Themed spread — show relevant hint
      if (newTheme === defaultTheme) {
        themeHint = `此牌阵侧重${THEME_LABELS[defaultTheme]}解读`;
      } else {
        themeHint = `此牌阵更擅长${THEME_LABELS[defaultTheme]}解读`;
      }
    }
    // General spread: no hint needed

    this.setData({ theme: newTheme, themeHint });
  },

  onBackToSpreads() {
    this._clearTimers();
    this.setData({
      selectedSpread: null,
      spreadDefaultTheme: null,
      showQuestionInput: false,
      ritualStage: null,
      ritualEnabled: false,
      question: '',
      theme: '',
      themeHint: '',
    });
  },

  onRetry() {
    this._clearTimers();
    if (this.data.selectedSpread) {
      // 保留已选的牌阵和问题，回到提问界面重新尝试
      this.setData({
        pageError: null,
        isDrawing: false,
      });
    } else {
      this.setData({
        pageError: null,
        isDrawing: false,
        selectedSpread: null,
        spreadDefaultTheme: null,
        showQuestionInput: false,
        ritualStage: null,
        ritualEnabled: false,
        theme: '',
        themeHint: '',
      });
    }
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

    // Save context before API call for error recovery
    wx.setStorageSync('pending_reading', {
      spread_type: selectedSpread.key,
      question: this.data.question || null,
      theme: this.data.theme || 'general',
      timestamp: Date.now(),
    });

    try {
      const result = await request(`/readings/spread/${selectedSpread.key}`, {
        method: 'POST',
        data: {
          spread_type: selectedSpread.key,
          question: this.data.question || null,
          theme: this.data.theme || 'general',
        },
      });

      // Success — clear pending
      wx.removeStorageSync('pending_reading');

      // Navigate to result page with reading ID
      wx.redirectTo({
        url: `/pages/reading-result/reading-result?id=${result.id}`,
      });
    } catch (err) {
      if (err.statusCode === 402) {
        this.setData({ isDrawing: false });
        wx.showModal({
          title: '次数不足',
          content: `今日免费解读 ${this.data.freeReadingsUsed}/${this.data.freeReadingsTotal} 次已用完 ✦ 明天00:00自动恢复 ✦ 或开通会员，立即无限解读`,
          confirmText: '开通会员',
          success: (res) => {
            if (res.confirm) {
              wx.navigateTo({ url: '/pages/membership/membership' });
            }
          },
        });
      } else {
        this.setData({ isDrawing: false, pageError: getFriendlyError(err) });
      }
    }
  },
});
