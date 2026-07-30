// pages/index/index.js
const perf = require('../../utils/performance');
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { computeImagePath } = require('../../utils/cards');
const { createAnim, staggeredEntrance } = require('../../utils/animate');
const { playPageEnterSound, playCardFlipSound, startAmbientSound, stopAmbientSound } = require('../../utils/sound');
const analytics = require('../../utils/analytics');

/** Get free daily readings limit from member status (or fallback) */
function _getFreeReadingsLimit() {
  const app = getApp();
  const quota = app.globalData.memberStatus?.free_quota;
  return quota?.daily_readings || 3;
}

const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';

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
    showTrialExpiryBanner: false,
    // Free tier display
    freeReadingsUsed: 0,
    freeReadingsTotal: _getFreeReadingsLimit(),
    isMember: false,
    // Pending reading recovery
    pendingReading: null,
    // Community topic title for home entry
    communityTopicTitle: '',

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

    // Annual report season flag (Dec-Jan)
    isAnnualReportSeason: false,
    annualReportYear: new Date().getFullYear(),

    // Collection progress
    collectedCount: 0,
    // Today's tasks (checked from /tasks/status)
    tasksCheckedIn: false,
    tasksDailyCardDrawn: false,
    tasksReadingDone: false,
    tasksShared: false,
    tasksCompleted: 0,
    tasksTotal: 3,
    taskStreak: 0,
    // Checkin entry on homepage
    checkinStreak: 0,
    checkedInToday: false,
    // Immersive tarot explainer overlay
    showTarotOverlay: false,
    // Shooting star easter egg
    shootingStarActive: false,

    // v2.1: Time-of-day greeting
    greetingText: '',
    greetingAnimKey: 0,

    // Membership smart prompt
    showMembershipPrompt: false,
    membershipPromptReason: '', // 'quota_exhausted' | 'near_limit'

    // v2.1: Zodiac sign onboarding
    zodiacSign: '',
    dailyCardImgError: false,
    zodiacList: [
      { key: 'aries', name: '白羊座', emoji: '♈' },
      { key: 'taurus', name: '金牛座', emoji: '♉' },
      { key: 'gemini', name: '双子座', emoji: '♊' },
      { key: 'cancer', name: '巨蟹座', emoji: '♋' },
      { key: 'leo', name: '狮子座', emoji: '♌' },
      { key: 'virgo', name: '处女座', emoji: '♍' },
      { key: 'libra', name: '天秤座', emoji: '♎' },
      { key: 'scorpio', name: '天蝎座', emoji: '♏' },
      { key: 'sagittarius', name: '射手座', emoji: '♐' },
      { key: 'capricorn', name: '摩羯座', emoji: '♑' },
      { key: 'aquarius', name: '水瓶座', emoji: '♒' },
      { key: 'pisces', name: '双鱼座', emoji: '♓' },
    ],
  },

  async onLoad() {
    // Analytics: page view
    analytics.pageView('home');

    // ── Onboarding: migrate old key ──
    const onboardingCompleted = wx.getStorageSync('onboarding_completed');
    const oldDone = wx.getStorageSync('onboarding_done');
    if (oldDone) {
      wx.setStorageSync('onboarding_completed', true);
      wx.removeStorageSync('onboarding_done');
    }
    // Store onboarding state for onReady usage (avoids re-reading storage)
    this._onboardingCompleted = !!(onboardingCompleted || oldDone);

    // Always load page content (bubble floats on top, not a full-screen block)
    try {
      await checkLogin();
      this.setData({ pageLoading: false });
      this._initDailyState();
      this._loadFreeReadings();
      this._restoreDailyCard();
      this._loadTasks();
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  onReady() {
    // Performance monitoring: first page rendered
    perf.mark('firstPageReady');
    perf.report();

    // Defer non-critical UI setup to unblock first paint
    this._deferredInit();
  },

  async onShow() {
    // Refresh free-reading count every time the page is shown
    this._loadFreeReadings();
    // Check if daily card has been flipped today
    this._checkDailyCardFlipped();
    // Check trial expiry and auto-revoke if expired
    this._checkTrialExpiry();
    // Load collection progress
    this._loadCollectionProgress();
    // Re-init shooting star timer if page was hidden
    this._initShootingStar();
    // v2.1: Recompute greeting (in case hour changed)
    this._computeGreeting();
    // v2.1: Refresh zodiac from storage (user might update elsewhere)
    const storedZodiac = wx.getStorageSync('zodiac_sign') || '';
    if (storedZodiac !== this.data.zodiacSign) {
      this.setData({ zodiacSign: storedZodiac });
    }
    this._loadTasks();
    // Load community topic title for home entry
    this._loadCommunityTopic();
    // Resume ambient sound if previously stopped
    if (wx.getStorageSync('ambient_enabled') === true) {
      startAmbientSound();
    }

    // Check for share success flag and show reward feedback banner
    this._checkShareSuccessFeedback();
  },

  /** Load today's community topic title for the home entry card */
  async _loadCommunityTopic() {
    try {
      const data = await request('/community/today');
      if (data && data.topic) {
        this.setData({ communityTopicTitle: data.topic.title });
      }
    } catch (_err) {
      // Silent degrade — entry just shows default text
    }
  },

  _loadCollectionProgress() {
    try {
      const collectedMajorIds = wx.getStorageSync('collected_major_ids') || [];
      this.setData({ collectedCount: collectedMajorIds.length });
    } catch (_e) {
      // Storage corrupted — reset silently
      this.setData({ collectedCount: 0 });
    }
  },

  /** v2.1: Compute time-of-day greeting with optional nickname */
  _computeGreeting() {
    const h = new Date().getHours();
    let base = '';
    if (h >= 5 && h < 11) {
      base = '晨光中的指引 ✦';
    } else if (h >= 11 && h < 14) {
      base = '午后的星光 ✦';
    } else if (h >= 14 && h < 18) {
      base = '傍晚的思绪 ✦';
    } else if (h >= 18 && h < 22) {
      base = '夜幕低垂 ✦';
    } else {
      base = '深夜静思 ✦';
    }
    const user = wx.getStorageSync('user') || {};
    const nickname = user.nickname || '';
    const greetingText = nickname ? `${base} ${nickname}` : base;
    this.setData({
      greetingText,
      greetingAnimKey: this.data.greetingAnimKey + 1,
    });
  },

  /** Load free-reading usage from cached user (or refresh if stale) */
  async _loadFreeReadings() {
    try {
      const user = await checkLogin({ refresh: true });
      if (user) {
        const used = user.free_readings_today || 0;
        const isMember = !!user.is_member;
        const app = getApp();
        app.globalData.memberStatus = { free_quota: user.free_quota };
        app.globalData.freeReadingsUsed = used;
        app.globalData.isMember = isMember;
        this.setData({
          freeReadingsUsed: used,
          freeReadingsTotal: _getFreeReadingsLimit(),
          isMember,
        });
      }
    } catch (_err) {
      // Silently degrade — counts stay at defaults
    }
    this._checkMembershipPrompt();
  },

  /** Show membership CTA when free quota is exhausted or nearly so */
  _checkMembershipPrompt() {
    const freeReadingsUsed = this.data.freeReadingsUsed;
    const freeReadingsTotal = this.data.freeReadingsTotal;
    const isMember = this.data.isMember;
    const freeLeft = Math.max(0, freeReadingsTotal - freeReadingsUsed);

    if (isMember) {
      this.setData({ showMembershipPrompt: false });
      return;
    }

    if (freeLeft <= 0) {
      this.setData({
        showMembershipPrompt: true,
        membershipPromptReason: 'quota_exhausted',
      });
    } else if (freeLeft === 1) {
      this.setData({
        showMembershipPrompt: true,
        membershipPromptReason: 'near_limit',
      });
    }
  },

  /** Dismiss the membership prompt card */
  onDismissMembership() {
    this.setData({ showMembershipPrompt: false });
  },

  /** Check trial expiry and auto-revoke if expired */
  _checkTrialExpiry() {
    try {
      const expiry = wx.getStorageSync('trial_expiry');
      const isTrial = wx.getStorageSync('is_trial_member');
      if (expiry && isTrial && Date.now() >= expiry) {
        wx.removeStorageSync('trial_expiry');
        wx.removeStorageSync('is_trial_member');
        this.setData({ isMember: false });
        console.log('[trial] 试用已过期，自动撤销');
      }
    } catch (e) {
      // silent
    }
  },

  /** Check if trial is expiring within 24h and show reminder banner */
  _checkTrialExpiryReminder() {
    try {
      const expiry = wx.getStorageSync('trial_expiry');
      const isTrial = wx.getStorageSync('is_trial_member');
      if (expiry && isTrial) {
        const now = Date.now();
        const timeLeft = expiry - now;
        const twentyFourHours = 24 * 60 * 60 * 1000;
        if (timeLeft > 0 && timeLeft <= twentyFourHours) {
          this.setData({ showTrialExpiryBanner: true });
        } else if (timeLeft <= 0) {
          // Already expired — clear
          wx.removeStorageSync('trial_expiry');
          wx.removeStorageSync('is_trial_member');
        }
      }
    } catch (_e) {
      // silent
    }
  },

  /** Load today's task status from server */
  async _loadTasks() {
    try {
      const status = await request('/tasks/status');
      this.setData({
        tasksCheckedIn: status.checked_in_today,
        tasksDailyCardDrawn: status.daily_card_drawn,
        tasksReadingDone: status.reading_done_today,
        tasksShared: status.shared_today,
        tasksCompleted: status.tasks_completed,
        tasksTotal: status.tasks_total,
        taskStreak: status.streak,
        checkinStreak: status.streak,
        checkedInToday: status.checked_in_today,
      });
    } catch (_err) {
      // Silent degrade — task UI just shows defaults (all false, 0/3)
    }
  },

  /** Check for pending share-success feedback from reading-result page */
  _checkShareSuccessFeedback() {
    const shareSuccess = wx.getStorageSync('_share_success_flag');
    if (shareSuccess) {
      wx.removeStorageSync('_share_success_flag');
      this._loadShareStatsAndShowBanner();
    }
  },

  /** Show a subtle banner with share reward info */
  async _loadShareStatsAndShowBanner() {
    try {
      const stats = await request('/share/stats?days=365');
      const shareCount = stats.share_count || 0;
      let msg = '';
      if (shareCount < 3) {
        const remaining = 3 - shareCount;
        msg = `分享成功！再分享 ${remaining} 次解锁 +3 次免费解读`;
      } else if (shareCount < 10) {
        const remaining = 10 - shareCount;
        msg = `分享成功！再分享 ${remaining} 次解锁 1 周免费会员`;
      } else if (shareCount < 30) {
        const remaining = 30 - shareCount;
        msg = `分享成功！再分享 ${remaining} 次解锁 1 个月免费会员`;
      } else {
        msg = '分享成功！你已解锁全部奖励 ✦';
      }
      wx.showToast({
        title: msg,
        icon: 'none',
        duration: 3000,
      });
    } catch (_err) {
      // Silent fail
    }
  },

  /** Navigate to checkin page */
  onGoCheckin() {
    wx.navigateTo({ url: '/pages/checkin/checkin' });
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

  /** Step 1 → Step 2 → Step 3 (zodiac picker): dismiss bubble, persist progress */
  onNextOnboarding() {
    const nextStep = this.data.onboardingStep + 1;
    if (nextStep > 3) {
      // All 3 steps done — close onboarding
      wx.setStorageSync('onboarding_completed', true);
      wx.setStorageSync('zodiac_onboarding_done', true);
      wx.removeStorageSync('onboarding_step');
      if (this._onboardingTimer) clearTimeout(this._onboardingTimer);
      this.setData({ showOnboarding: false, onboardingStep: 0 });
      return;
    }
    this.setData({ onboardingStep: nextStep });
  },

  /** Select a zodiac sign on step 3 */
  onSelectZodiac(e) {
    const sign = e.currentTarget.dataset.sign;
    wx.setStorageSync('zodiac_sign', sign);
    wx.setStorageSync('zodiac_onboarding_done', true);
    wx.setStorageSync('onboarding_completed', true);
    wx.removeStorageSync('onboarding_step');
    if (this._onboardingTimer) clearTimeout(this._onboardingTimer);
    this.setData({
      zodiacSign: sign,
      showOnboarding: false,
      onboardingStep: 0,
    });
    try { wx.vibrateShort({ type: 'light' }); } catch (e) {}
  },

  /** Skip zodiac selection */
  onSkipZodiac() {
    wx.setStorageSync('zodiac_onboarding_done', true);
    wx.setStorageSync('onboarding_completed', true);
    wx.removeStorageSync('onboarding_step');
    if (this._onboardingTimer) clearTimeout(this._onboardingTimer);
    this.setData({ showOnboarding: false, onboardingStep: 0 });
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
      const zodiacSign = this.data.zodiacSign;
      const card = await request('/cards/daily', { data: { zodiac: zodiacSign } });
      card.imagePath = computeImagePath(card, IMAGE_BASE);
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

  /** Handle daily card thumbnail image load error */
  onDailyCardImgError() {
    this.setData({ dailyCardImgError: true });
  },

  navigateToReading(e) {
    const type = e.currentTarget.dataset.type;
    analytics.trackEvent('reading_start', { type, source: 'home_spread_card' });
    wx.navigateTo({ url: `/pages/reading/reading?type=${type}` });
  },

  goToDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  onGoDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  goToAllSpreads() {
    wx.navigateTo({ url: '/pages/reading/reading' });
  },

  /** Navigate to community / tree hole page */
  onGoCommunity() {
    wx.navigateTo({ url: '/pages/community/community' });
  },

  /** Navigate to the 9.9 yuan first reading (three-card spread) */
  onStartFirstReading() {
    wx.navigateTo({ url: '/pages/reading/reading?type=three_card' });
  },

  /** Navigate to annual report page (members only) */
  onGoAnnualReport() {
    wx.navigateTo({ url: '/pages/annual-report/annual-report' });
  },

  /** Navigate to membership page */
  onGoMembership() {
    analytics.trackEvent('membership_cta', { source: 'home' });
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  /** DEV: Navigate to page test runner */
  onGoTestRunner() {
    wx.navigateTo({ url: '/pages/test-runner/test-runner' });
  },

  /** Show a brief explainer of what tarot is */
  showTarotExplainer() {
    this.setData({ showTarotOverlay: true });
  },

  /** Close the tarot explainer overlay */
  closeTarotOverlay() {
    this.setData({ showTarotOverlay: false });
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

  /** Deferred non-critical initialization — called from onReady to unblock first paint */
  _deferredInit() {
    // Entrance sound + micro-haptic (once per session)
    playPageEnterSound();
    const appEnter = getApp();
    if (!appEnter.globalData._pageHapticPlayed) {
      wx.vibrateShort({ type: 'light' }).catch(() => {});
      appEnter.globalData._pageHapticPlayed = true;
    }

    // Start ambient sound if user has it enabled
    if (wx.getStorageSync('ambient_enabled') === true) {
      startAmbientSound();
    }

    // Init shooting star easter egg with random intervals
    this._initShootingStar();

    // v2.1: Compute time-of-day greeting
    this._computeGreeting();

    // v2.1: Load stored zodiac sign
    const storedZodiac = wx.getStorageSync('zodiac_sign') || '';
    this.setData({ zodiacSign: storedZodiac });

    // Check if it's annual report season (Dec-Jan)
    const currentMonth = new Date().getMonth() + 1;
    const currentYear = new Date().getFullYear();
    if (currentMonth === 12 || currentMonth === 1) {
      this.setData({
        isAnnualReportSeason: true,
        annualReportYear: currentMonth === 1 ? currentYear - 1 : currentYear,
      });
    }

    // Onboarding flow — simplified: show all 3 steps, auto-dismiss after 5s
    const zodiacCompleted = wx.getStorageSync('zodiac_onboarding_done');
    if (!this._onboardingCompleted && !zodiacCompleted) {
      this.setData({ showOnboarding: true, onboardingStep: 0 });
      this._onboardingTimer = setTimeout(() => {
        if (this.data.showOnboarding) {
          wx.setStorageSync('onboarding_completed', true);
          wx.setStorageSync('zodiac_onboarding_done', true);
          wx.removeStorageSync('onboarding_step');
          this.setData({ showOnboarding: false, onboardingStep: 0 });
        }
      }, 5000);
    }

    // Check for pending reading to show recovery card
    this._checkPendingReading();

    // Trigger native staggered entrance for spread cards after render
    if (this.data.useNativeAnim) {
      setTimeout(() => { this._triggerSpreadEntrance(); }, 100);
    }

    // Check trial expiry reminder (within 24h)
    this._checkTrialExpiryReminder();
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
        const zodiacSign = this.data.zodiacSign;
        const card = await request('/cards/daily', { data: { zodiac: zodiacSign } });
        card.imagePath = computeImagePath(card, IMAGE_BASE);
        app.globalData.dailyCard = card;
        this.setData({ dailyCard, dailyCardRestoring: false });
      } catch (_err) {
        this.setData({ dailyCardRestoring: false });
      }
    }
  },

  // ===================== Shooting star easter egg =====================

  /** Init the shooting star scheduler (guarded — won't double-init) */
  _initShootingStar() {
    if (this._shootingStarReady) return;
    this._shootingStarReady = true;
    this._scheduleShootingStar();
  },

  /** Schedule next shooting star appearance at random 20-45s */
  _scheduleShootingStar() {
    const delay = 20000 + Math.random() * 25000; // 20-45 seconds
    this._pushTimer(setTimeout(() => {
      this._triggerShootingStar();
    }, delay));
  },

  /** Fire the shooting star: toggle class, play sound, haptic */
  _triggerShootingStar() {
    // Reset first to guarantee CSS animation re-triggers
    this.setData({ shootingStarActive: false });
    // Re-add class after a micro delay to restart the animation
    this._pushTimer(setTimeout(() => {
      this.setData({ shootingStarActive: true });
    }, 30));

    // Magical swoosh sound
    playCardFlipSound();

    // Light haptic for the magical moment
    wx.vibrateShort({ type: 'light' }).catch(() => {});

    // Reset class after animation completes, then schedule next
    this._pushTimer(setTimeout(() => {
      this.setData({ shootingStarActive: false });
      this._scheduleShootingStar();
    }, 5000));
  },

  onUnload() {
    if (this._onboardingTimer) clearTimeout(this._onboardingTimer);
    this._clearTimers();
  },

  onHide() {
    if (this._onboardingTimer) clearTimeout(this._onboardingTimer);
    this._clearTimers();
    this._shootingStarReady = false;
    // Stop ambient sound when page hidden (will resume on show)
    stopAmbientSound();
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
