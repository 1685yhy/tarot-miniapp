// pages/index/index.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { computeImagePath } = require('../../utils/cards');
const { createAnim, staggeredEntrance } = require('../../utils/animate');

const FREE_READINGS_LIMIT = 3;

function getTodayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function getYesterdayStr() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

const STREAK_MILESTONES = {
  7: '连续7天！星光与你同行 ✨',
  14: '两周守护！星辰之路持续闪耀 ✨',
  30: '满月之约！30天星光陪伴 ✨',
  100: '百日修行！你已是星光的一部分 ✨',
};

Page({
  data: {
    dailyCard: null,
    pageLoading: true,
    pageError: null,
    drawingLoading: false,
    rippleActive: false,
    shaking: false,
    showOnboarding: false,
    onboardingStep: 0,
    onboardingSteps: [
      { emoji: '✨', title: '每日一牌', desc: '轻触卡片，获得今日专属指引' },
      { emoji: '🔮', title: '牌阵解读', desc: '选择牌阵，AI为您深度解读' },
      { emoji: '💫', title: '星光陪伴', desc: '记录心灵旅程，发现内在力量' },
    ],
    // Daily habit loop
    streak: 0,
    hasDrawnToday: false,
    showReflectionPrompt: false,
    showReminder: false,
    // Free tier display
    freeReadingsUsed: 0,
    freeReadingsTotal: FREE_READINGS_LIMIT,
    isMember: false,
    // Pending reading recovery
    pendingReading: null,

    // ---- wx.createAnimation native animation system ----
    // Toggle: set false to fall back to CSS animations only
    useNativeAnim: true,
    // Animation data for daily card draw (pre-draw press + shuffle)
    cardAnimData: {},
    // Animation data for spread grid staggered entrance
    spreadAnimData: [],

    // v2.0: Daily card teaching entry state
    dailyCardFlipped: false,
    dailyCardRestoring: false,
  },

  async onLoad() {
    const onboardingDone = wx.getStorageSync('onboarding_done');
    if (onboardingDone) {
      try {
        await checkLogin();
        this.setData({ pageLoading: false });
        this._initDailyState();
        this._loadFreeReadings();
        this._restoreDailyCard();
      } catch (err) {
        this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
      }
    } else {
      this.setData({ showOnboarding: true, pageLoading: false });
    }

    // Check for pending reading to show recovery card
    this._checkPendingReading();

    // Trigger native staggered entrance for spread cards after render
    if (this.data.useNativeAnim) {
      setTimeout(() => { this._triggerSpreadEntrance(); }, 100);
    }
  },

  async onShow() {
    // Refresh free-reading count every time the page is shown
    this._loadFreeReadings();
    // Check if daily card has been flipped today
    this._checkDailyCardFlipped();
  },

  /** Load free-reading usage from cached user (or refresh if stale) */
  async _loadFreeReadings() {
    try {
      const user = await checkLogin({ refresh: true });
      if (user) {
        const used = user.free_readings_today || 0;
        const isMember = !!user.is_member;
        this.setData({
          freeReadingsUsed: used,
          freeReadingsTotal: FREE_READINGS_LIMIT,
          isMember,
        });
        const app = getApp();
        app.globalData.freeReadingsUsed = used;
        app.globalData.isMember = isMember;
      }
    } catch (_err) {
      // Silently degrade — counts stay at defaults
    }
  },

  /** Initialize daily streak and reminder state from storage */
  _initDailyState() {
    const lastDate = wx.getStorageSync('last_draw_date');
    const storedStreak = wx.getStorageSync('streak') || 0;
    const today = getTodayStr();
    const yesterday = getYesterdayStr();

    let hasDrawnToday = false;
    let streak = 0;
    let showReminder = false;

    if (lastDate === today) {
      hasDrawnToday = true;
      streak = storedStreak;
    } else if (lastDate === yesterday) {
      // User drew yesterday — streak is alive, new fortune is ready
      streak = storedStreak;
      showReminder = true;
    } else {
      // Streak broken or first time
      streak = 0;
      showReminder = true; // still show the card is ready
    }

    this.setData({ streak, hasDrawnToday, showReminder });
  },

  /** Update streak after a successful daily draw */
  _updateStreak() {
    const lastDate = wx.getStorageSync('last_draw_date');
    const storedStreak = wx.getStorageSync('streak') || 0;
    const today = getTodayStr();
    const yesterday = getYesterdayStr();

    let newStreak;
    if (lastDate === yesterday) {
      newStreak = storedStreak + 1;
    } else if (lastDate === today) {
      newStreak = storedStreak; // redraw same day
    } else {
      newStreak = 1; // fresh start after break
    }

    wx.setStorageSync('last_draw_date', today);
    wx.setStorageSync('streak', newStreak);
    this.setData({ streak: newStreak, hasDrawnToday: true, showReminder: false });

    const message = STREAK_MILESTONES[newStreak];
    if (message) {
      setTimeout(() => {
        wx.showToast({ title: message, icon: 'none', duration: 2500 });
      }, 800);
    }
  },

  onOnboardingSwipe(e) {
    const { current } = e.detail;
    this.setData({ onboardingStep: current });
  },

  onOnboardingNext() {
    const next = this.data.onboardingStep + 1;
    if (next < this.data.onboardingSteps.length) {
      this.setData({ onboardingStep: next });
    }
  },

  onOnboardingDone() {
    wx.setStorageSync('onboarding_done', true);
    this.setData({ showOnboarding: false });
    this.onLoad();
  },

  onTapDot(e) {
    const idx = e.currentTarget.dataset.index;
    this.setData({ onboardingStep: idx });
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  async drawDailyCard() {
    if (this.data.drawingLoading) return;
    this.setData({ drawingLoading: true });

    // --- wx.createAnimation 3-step sequence (when enabled) ---
    // Replaces the CSS-only shake+ripple with native animation.
    // Step 3 (card appear) uses the existing CSS .card-rise reveal
    // on the post-draw card which runs alongside.
    if (this.data.useNativeAnim) {
      const preAnim = createAnim({});
      preAnim.scale(0.97).step({ duration: 150 });                // Feedback: press feedback (150ms)
      preAnim.scale(1.02).rotate(2).step({ duration: 300 });      // Emphasis: shuffle feel (300ms)
      preAnim.scale(1).rotate(0).step({ duration: 200 });         // Orientation: settle before swap (200ms)
      this.setData({ cardAnimData: preAnim.export() });
    }

    // --- Haptic & visual feedback (existing CSS, kept intact) ---
    wx.vibrateShort({ type: 'light' }).catch(() => {});

    // 1. Ripple burst from center (animation: 0.15s via .ripple-run)
    this.setData({ rippleActive: true });
    // 2. Shake — brief shuffle feel (animation: 0.15s via .card-shake-fx)
    this.setData({ shaking: true });

    // Cleanup timers matching reduced CSS durations
    this._pushTimer(setTimeout(() => { this.setData({ shaking: false }); }, 150)); // Feedback: shake duration
    this._pushTimer(setTimeout(() => { this.setData({ rippleActive: false }); }, 200)); // Feedback: ripple duration + buffer

    // Orientation: brief pause so user sees initial animation frames before API call (200ms)
    await new Promise(r => setTimeout(r, 200));

    wx.showLoading({ title: '抽取中...' });
    try {
      // Emphasis: extra delay so pre-draw state lingers before reveal transition (300ms)
      await new Promise(r => setTimeout(r, 300));
      const card = await request('/cards/daily');
      card.imagePath = computeImagePath(card, 'https://xingxiang.chat/images/cards_full');
      this.setData({ dailyCard: card, drawingLoading: false });
      wx.hideLoading();
      // 保存到globalData供详情页使用
      getApp().globalData.dailyCard = card;
      // Daily habit loop: update streak + show reflection prompt
      this._updateStreak();
      this.setData({ showReflectionPrompt: true });
    } catch (err) {
      this.setData({ drawingLoading: false });
      this._clearTimers();
      this.setData({ rippleActive: false, shaking: false });
      wx.hideLoading();
      wx.showToast({ title: '抽取失败，请重试', icon: 'none' });
    }
  },

  navigateToReading(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },

  goToDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  goToAllSpreads() {
    wx.navigateTo({ url: '/pages/reading/reading' });
  },

  /** Show a brief explainer of what tarot is */
  showTarotExplainer() {
    wx.showModal({
      title: '什么是塔罗？',
      content: '塔罗是一面镜子，帮你看见自己内心已经知道、却未说出口的东西。每张牌是一种人生情境的映射，而非对未来的预言。解读的意义在于激发你的内在思考——答案不在牌里，而在你心里。',
      showCancel: false,
      confirmText: '明白了',
    });
  },

  /** Check for a saved pending reading to offer recovery */
  _checkPendingReading() {
    const pending = wx.getStorageSync('pending_reading');
    if (pending && pending.spread_type) {
      // Expire after 24 hours
      if (pending.timestamp && Date.now() - pending.timestamp > 24 * 60 * 60 * 1000) {
        wx.removeStorageSync('pending_reading');
        return;
      }
      this.setData({ pendingReading: pending });
    }
  },

  /** Trigger staggered entrance for spread grid cards using wx.createAnimation */
  _triggerSpreadEntrance() {
    if (!this.data.useNativeAnim) return;
    // 4 spread cards + 1 "查看更多" link = 5 animated elements
    const anims = staggeredEntrance(5, 100);
    this.setData({ spreadAnimData: anims });
  },

  onContinueReading() {
    const pending = this.data.pendingReading;
    if (!pending) return;
    wx.navigateTo({
      url: `/pages/reading/reading?type=${pending.spread_type}`,
    });
  },

  /** Navigate to daily-card teaching page */
  onDailyCardTap() {
    wx.navigateTo({ url: '/pages/daily-card/daily-card' });
  },

  /** Check if today's daily card has been flipped on the daily-card page */
  _checkDailyCardFlipped() {
    const today = getTodayStr();
    const flippedDate = wx.getStorageSync('daily_card_flipped_date');
    this.setData({ dailyCardFlipped: flippedDate === today });
  },

  /** Restore daily card from globalData or re-fetch if already drawn today */
  async _restoreDailyCard() {
    const app = getApp();
    if (app.globalData.dailyCard) {
      this.setData({ dailyCard: app.globalData.dailyCard });
      return;
    }
    if (this.data.hasDrawnToday) {
      this.setData({ dailyCardRestoring: true });
      try {
        const card = await request('/cards/daily');
        card.imagePath = computeImagePath(card, 'https://xingxiang.chat/images/cards_full');
        app.globalData.dailyCard = card;
        this.setData({ dailyCard, dailyCardRestoring: false });
      } catch (_err) {
        this.setData({ dailyCardRestoring: false });
      }
    }
  },

  onUnload() {
    this._clearTimers();
  },

  _pushTimer(timer) {
    if (!this._timers) this._timers = [];
    this._timers.push(timer);
    return timer;
  },

  _clearTimers() {
    if (this._timers) {
      this._timers.forEach(t => clearTimeout(t));
      this._timers = [];
    }
  },
});
