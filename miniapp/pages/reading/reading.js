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
const { playCardDrawSound } = require('../../utils/sound');

const FREE_READINGS_LIMIT = 5; // matches the backend FREE_DAILY_READINGS (should match after backend update)

const SPREADS = [
  { key: 'three_card', name: '三牌占卜', icon: '🕯️', desc: '过去·现在·未来', cards: 3, popular: true, defaultTheme: null, plainDesc: '最通用的牌阵，适合任何问题' },
  { key: 'triangle', name: '恋人三角', icon: '💕', desc: '感情关系深度分析', cards: 4, defaultTheme: 'love', plainDesc: '专看感情，4张牌深度分析双方状态' },
  { key: 'career', name: '事业牌阵', icon: '💼', desc: '职业发展方向指引', cards: 5, defaultTheme: 'career', plainDesc: '工作选择和职业规划专用' },
  { key: 'finance', name: '财运牌阵', icon: '💰', desc: '财务状况趋势分析', cards: 4, defaultTheme: 'finance', plainDesc: '看收入和投资方向' },
  { key: 'decision', name: '二择一', icon: '🔀', desc: '两难选择的明灯', cards: 5, defaultTheme: null, plainDesc: '两个选项纠结时，帮你理清利弊' },
  { key: 'celtic_cross', name: '凯尔特十字', icon: '✝️', desc: '最全面的深度占卜', cards: 10, premium: true, defaultTheme: null, plainDesc: '全方位剖析，适合复杂问题时用' },
  { key: 'life_cross', name: '人生十字', icon: '⭐', desc: '人生方向的十字路口', cards: 5, defaultTheme: null, plainDesc: '迷茫期专用，看清人生方向' },
  { key: 'horseshoe', name: '马蹄牌阵', icon: '🧲', desc: '七步看清局势', cards: 7, premium: true, defaultTheme: 'love', plainDesc: '7张牌一步步推演事情发展' },
  { key: 'relationship', name: '关系牌阵', icon: '🤝', desc: '双人关系全面透视', cards: 7, premium: true, defaultTheme: 'love', plainDesc: '你和TA之间，7张牌全盘解析' },
  { key: 'year_ahead', name: '年度运势', icon: '📅', desc: '未来12个月逐月详解', cards: 13, premium: true, defaultTheme: null, plainDesc: '一整年的每月运势预览' },
];

const THEME_LABELS = {
  love: '爱情',
  career: '事业',
  finance: '财运',
  general: '综合',
};

const THEME_ICONS = {
  love: '/images/icons/theme_love_64.png',
  career: '/images/icons/theme_career_64.png',
  finance: '/images/icons/theme_finance_64.png',
  general: '/images/icons/theme_general_64.png',
};

// ── Reader Personas ──────────────────────────────────────────────
const PERSONAS = [
  { key: 'gentle_star', name: '温和的星', icon: '✦', label: '温暖陪伴' },
  { key: 'wise_moon',  name: '智慧的月', icon: '☽', label: '理性分析' },
  { key: 'frank_sun',  name: '率直的太阳', icon: '☀', label: '直击要害' },
];

const DEFAULT_PERSONA = 'wise_moon';

// Build ordered theme list: themed spreads show ONLY their theme; general shows all
function buildDisplayThemes(defaultTheme) {
  const all = ['general', 'love', 'career', 'finance'];
  if (!defaultTheme) {
    return all.map(k => ({ key: k, label: THEME_LABELS[k], icon: THEME_ICONS[k] }));
  }
  // Themed spreads: ONLY the matching theme — others don't apply
  return [{ key: defaultTheme, label: THEME_LABELS[defaultTheme], icon: THEME_ICONS[defaultTheme] }];
}

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
    // Reader persona selection
    personas: PERSONAS,
    selectedPersona: DEFAULT_PERSONA,

    // Draw mode: 'quick' (default) or 'immersive'
    drawMode: 'quick',
    quickMode: true,
    // Quick purchase packs in exhausted state
    packQuick3: {
      id: 'reading_pack_3',
      price: '9.90',
    },
    packQuick10: {
      id: 'reading_pack_10',
      price: '29.90',
    },
    // Onboarding Step 2
    showOnboarding: false,
    onboardingStep: 0,
  },

  _timers: [],

  onLoad(options) {
    // Load draw mode preference from profile settings
    const savedDrawMode = wx.getStorageSync('default_draw_mode') || 'quick';
    this.setData({
      drawMode: savedDrawMode,
      quickMode: savedDrawMode === 'quick',
    });

    // 首页点击牌阵直接进入问答，跳过选择页
    const type = (options && options.type) || '';
    if (type) {
      const spread = SPREADS.find(s => s.key === type);
      if (spread) {
        // Check for pending reading context (from home page "继续" flow)
        const pending = wx.getStorageSync('pending_reading');
        let restoredQuestion = '';
        let restoredTheme = '';
        let restoredPersona = '';
        if (pending && pending.spread_type === type) {
          if (!pending.timestamp || Date.now() - pending.timestamp < 24 * 60 * 60 * 1000) {
            restoredQuestion = pending.question || '';
            restoredTheme = pending.theme || '';
            restoredPersona = pending.persona || '';
          }
          wx.removeStorageSync('pending_reading');
        }

        // Apply default-theme logic
        const defaultTheme = spread.defaultTheme || null;
        const theme = restoredTheme || defaultTheme || 'general';
        const themeHint = defaultTheme
          ? `此牌阵侧重${THEME_LABELS[defaultTheme]}解读`
          : '';
        const displayThemes = buildDisplayThemes(defaultTheme);

        // 先设置数据，再处理会员检查
        this.setData({
          selectedSpread: spread,
          spreadDefaultTheme: defaultTheme,
          themeDefaultLabel: defaultTheme ? THEME_LABELS[defaultTheme] : '',
          theme: theme,
          themeHint: themeHint,
          displayThemes: displayThemes,
          question: restoredQuestion,
          selectedPersona: restoredPersona || DEFAULT_PERSONA,
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

    // ── Onboarding Step 2: show bubble when entering with a spread type ──
    const onboardingCompleted = wx.getStorageSync('onboarding_completed');
    const onboardingStep = wx.getStorageSync('onboarding_step') || 1;
    if (!onboardingCompleted && onboardingStep === 2 && type) {
      this.setData({ showOnboarding: true, onboardingStep: 2 });
      this._setTimer(() => {
        this.setData({ showOnboarding: false });
        wx.setStorageSync('onboarding_step', 3);
      }, 3000);
    }

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

  onHide() {
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
    try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
    try { playCardDrawSound(); } catch(e) {}
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
    const displayThemes = buildDisplayThemes(defaultTheme);

    // Skip ritual by default — show question input directly
    this.setData({
      selectedSpread: spread,
      spreadDefaultTheme: defaultTheme,
      themeDefaultLabel: defaultTheme ? THEME_LABELS[defaultTheme] : '',
      theme: theme,
      themeHint: themeHint,
      displayThemes: displayThemes,
      selectedPersona: DEFAULT_PERSONA,
      showQuestionInput: true,
    });
  },

  /** Step 2: dismiss bubble on tap and advance progress */
  onNextOnboarding() {
    this.setData({ showOnboarding: false });
    wx.setStorageSync('onboarding_step', 3);
  },

  onQuestionInput(e) {
    // Dismiss Step 2 bubble if user starts typing
    if (this.data.showOnboarding && this.data.onboardingStep === 2) {
      this.setData({ showOnboarding: false });
      wx.setStorageSync('onboarding_step', 3);
    }
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

  onPersonaTap(e) {
    const persona = e.currentTarget.dataset.persona;
    this.setData({ selectedPersona: persona });
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
      selectedPersona: DEFAULT_PERSONA,
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
        selectedPersona: DEFAULT_PERSONA,
      });
    }
  },

  /** Select draw mode: quick or immersive */
  onSelectMode(e) {
    const mode = e.currentTarget.dataset.mode;
    const isQuick = mode === 'quick';
    this.setData({
      quickMode: isQuick,
      drawMode: isQuick ? 'quick' : 'immersive',
    });
    wx.setStorageSync('default_draw_mode', isQuick ? 'quick' : 'immersive');
  },

  /** 快速购买补充包（从免费次数耗尽状态直接购买） */
  async onPurchasePackQuick(e) {
    const product = e.currentTarget.dataset.product;
    if (!product || !product.id) return;

    try {
      await checkLogin();
    } catch (err) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '创建订单...' });
    try {
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: product.id },
      });
      wx.hideLoading();

      if (!order.payment_params) {
        wx.showModal({
          title: '支付未配置',
          content: '微信支付商户尚未配置完成。请先在服务器 .env 中配置微信支付参数。',
          showCancel: false,
        });
        return;
      }

      wx.requestPayment({
        timeStamp: order.payment_params.timeStamp,
        nonceStr: order.payment_params.nonceStr,
        package: order.payment_params.package,
        signType: order.payment_params.signType || 'HMAC-SHA256',
        paySign: order.payment_params.paySign,
        success: () => {
          wx.showToast({ title: '购买成功！继续解读', icon: 'success' });
          // 刷新用户信息，更新剩余次数
          this._loadFreeReadings();
          // 自动继续之前选择的牌阵解读
          if (this.data.selectedSpread) {
            setTimeout(() => {
              this.onStartReading();
            }, 1200);
          }
        },
        fail: (err) => {
          if (err.errMsg && err.errMsg.includes('cancel')) {
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else {
            wx.showToast({ title: '支付失败，请重试', icon: 'none' });
          }
        },
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },

  async onStartReading() {
    const { selectedSpread, isDrawing, quickMode } = this.data;
    if (!selectedSpread) return;
    if (isDrawing) return;

    // Check login first
    try {
      await checkLogin();
    } catch (err) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    // Show confirmation dialog before consuming reading quota
    const isMember = this.data.isMember;
    const confirmContent = isMember
      ? '将消耗 1 次付费解读机会，确定要继续吗？'
      : '将消耗 1 次免费解读机会，确定要继续吗？';

    const confirmed = await new Promise((resolve) => {
      wx.showModal({
        title: '确认开始解读',
        content: confirmContent,
        confirmText: '确定',
        cancelText: '取消',
        success: (res) => resolve(res.confirm),
      });
    });

    if (!confirmed) return;

    // Save pending context for result page
    const pending = {
      spread_type: selectedSpread.key,
      question: this.data.question || null,
      theme: this.data.theme || 'general',
      persona: this.data.selectedPersona || DEFAULT_PERSONA,
      timestamp: Date.now(),
    };
    wx.setStorageSync('pending_reading', pending);

    // Play shuffle sound before navigating
    try { playCardDrawSound(); } catch(e) {}
    try { wx.vibrateShort({ type: 'medium' }); } catch(e) {}

    if (quickMode) {
      // Quick mode: skip ritual & loading stages, go directly to result
      wx.redirectTo({
        url: `/pages/reading-result/reading-result?pending=1&spread=${selectedSpread.key}&quick=1`,
      });
    } else {
      // Immersive mode: existing flow with full animation
      wx.redirectTo({
        url: `/pages/reading-result/reading-result?pending=1&spread=${selectedSpread.key}`,
      });
    }
  },
});
