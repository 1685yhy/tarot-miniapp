// pages/index/index.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

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
  },

  async onLoad() {
    const onboardingDone = wx.getStorageSync('onboarding_done');
    if (onboardingDone) {
      try {
        await checkLogin();
        this.setData({ pageLoading: false });
        this._initDailyState();
        this._loadFreeReadings();
      } catch (err) {
        this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
      }
    } else {
      this.setData({ showOnboarding: true, pageLoading: false });
    }

    // Check for pending reading to show recovery card
    this._checkPendingReading();
  },

  async onShow() {
    // Refresh free-reading count every time the page is shown
    this._loadFreeReadings();
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
      // Daily habit loop: update streak + show reflection prompt
      this._updateStreak();
      this.setData({ showReflectionPrompt: true });
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

  goToDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  goToAllSpreads() {
    wx.navigateTo({ url: '/pages/reading/reading' });
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

  onContinueReading() {
    const pending = this.data.pendingReading;
    if (!pending) return;
    wx.navigateTo({
      url: `/pages/reading/reading?type=${pending.spread_type}`,
    });
  },

  onUnload() {
    this._shakeTimer && clearTimeout(this._shakeTimer);
    this._rippleTimer && clearTimeout(this._rippleTimer);
  },
});
