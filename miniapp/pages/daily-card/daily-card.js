// pages/daily-card/daily-card.js
// 每日一牌 — 卡牌翻转动画 + 牌意教学 + 收集进度 + 日记入口
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');
const { playCardRevealSound } = require('../../utils/sound');

const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';
const MAJOR_ARCANA_TOTAL = 22;

const MILESTONES = {
  1: '收集到第1张牌！78张牌等你探索 ✦',
  5: '已收集5张！你对塔罗有了初步认识 ✦',
  10: '10张了！大牌进度 {majorCount}/22',
  22: '🎉 集齐所有大牌22张！你是塔罗大师',
  30: '30张！超过三分之一的塔罗世界已被你解锁',
  50: '50张！你已经超越了大多数人的塔罗知识',
  78: '🏆 78张全收集！星光映照的完整故事都在你手中',
};

function getTodayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

Page({
  data: {
    // Card data
    dailyCard: null,
    cardImagePath: '',
    cardImgLoaded: false,
    cardImgError: false,

    // Teaching data
    teaching: null,
    teachingSymbol: '',
    teachingLife: '',

    // Card flip state
    isFlipped: false,
    isAnimating: false,
    showTeaching: false,
    showGlow: false,
    backHidden: false,
    frontVisible: false,

    // Loading / Error states
    pageLoading: true,
    pageError: null,
    teachingLoading: false,
    teachingError: null,

    // Collection progress (major arcana only)
    collectedCount: 0,
    collectedMajorIds: [],
    MAJOR_ARCANA_TOTAL: MAJOR_ARCANA_TOTAL,

    // Push subscription prompt
    showPushPrompt: false,
    pushSubscribed: false,

    // Diary
    diaryText: '',
    diarySaving: false,
    diarySaved: false,

    // v2.1: Zodiac sign
    zodiacSign: '',

    // Streak context (from checkin system — optional enhancement)
    dailyStreak: -1,
    streakEncouragement: '',
    nextMilestone: 7,
    milestoneProgress: 0,
    streakHint: '',
  },

  async onLoad() {
    const today = getTodayStr();
    const flippedDate = wx.getStorageSync('daily_card_flipped_date');
    const alreadyFlipped = flippedDate === today;

    // Load collection progress from storage
    this._loadCollectionProgress();

    // v2.1: Load stored zodiac sign
    const storedZodiac = wx.getStorageSync('zodiac_sign') || '';
    this.setData({ zodiacSign: storedZodiac });

    // Load streak context from checkin system (fire-and-forget, non-blocking)
    this._loadStreakContext();

    try {
      const card = await request('/cards/daily', { data: { zodiac: storedZodiac } });
      card.imagePath = computeImagePath(card, IMAGE_BASE);

      this.setData({
        dailyCard: card,
        pageLoading: false,
        // If already flipped today, show face-up immediately
        isFlipped: alreadyFlipped,
        showTeaching: alreadyFlipped,
        showGlow: alreadyFlipped,
        backHidden: alreadyFlipped,
        frontVisible: alreadyFlipped,
      });

      // Fetch teaching data in parallel after card loads
      this._loadTeaching(card.id);
    } catch (err) {
      this.setData({
        pageLoading: false,
        pageError: getFriendlyError(err),
      });
    }
  },

  // ---- Teaching data ----

  async _loadTeaching(cardId) {
    this.setData({ teachingLoading: true, teachingError: null });
    try {
      const teaching = await request(`/cards/${cardId}/teaching`);
      // Extract first symbol name and life_connection for the compact snippet
      const firstSymbol = teaching.symbols && teaching.symbols.length > 0
        ? teaching.symbols[0].name || teaching.symbols[0].symbol || ''
        : '';
      const lifeConn = teaching.life_connection || '';
      this.setData({
        teaching,
        teachingSymbol: firstSymbol,
        teachingLife: lifeConn,
        teachingLoading: false,
      });
    } catch (err) {
      this.setData({
        teachingLoading: false,
        teachingError: getFriendlyError(err),
      });
    }
  },

  // ---- Collection progress ----

  _loadCollectionProgress() {
    try {
      const collectedMajorIds = wx.getStorageSync('collected_major_ids') || [];
      this.setData({
        collectedCount: collectedMajorIds.length,
        collectedMajorIds,
      });
    } catch (_e) {
      // Storage corrupted — reset silently
      this.setData({ collectedCount: 0, collectedMajorIds: [] });
    }
  },

  _saveCollectionProgress() {
    const card = this.data.dailyCard;
    if (!card || card.arcana !== 'major') return;

    let collectedMajorIds;
    try {
      collectedMajorIds = wx.getStorageSync('collected_major_ids') || [];
    } catch (_e) {
      collectedMajorIds = [];
    }
    if (!collectedMajorIds.includes(card.id)) {
      collectedMajorIds.push(card.id);
      try { wx.setStorageSync('collected_major_ids', collectedMajorIds); } catch (_e) {}
      const collectedCount = collectedMajorIds.length;
      this.setData({
        collectedCount,
        collectedMajorIds,
      });

      // Check milestone
      this._checkMilestone(collectedCount);
    }
  },

  _checkMilestone(count) {
    const milestone = MILESTONES[count];
    if (!milestone) return;

    const majorCount = count; // all collected are major arcana
    const content = milestone.replace('{majorCount}', majorCount);

    setTimeout(() => {
      wx.showModal({
        title: '收集里程碑',
        content,
        showCancel: false,
        confirmText: '继续探索',
      });
    }, 500);
  },

  // ---- Streak context from checkin system ----

  _loadStreakContext() {
    // Streak info is an enhancement — gracefully handle failures
    request('/tasks/status').then(res => {
      if (res && res.streak !== undefined) {
        const streak = res.streak || 0;
        const level = res.level || { name: '星光旅人' };

        // Compute encouragement text by streak tier
        let encouragement = '';
        if (streak === 0) {
          encouragement = '今天开始你的星光之旅吧 ✦';
        } else if (streak < 3) {
          encouragement = `已连续 ${streak} 天 · 星光初现`;
        } else if (streak < 7) {
          encouragement = `连续 ${streak} 天 · 星辰相伴`;
        } else if (streak < 30) {
          encouragement = `连续 ${streak} 天 · ${level.name}`;
        } else {
          encouragement = `${level.name} · 星光不负赶路人`;
        }

        // Compute next milestone (7, 30, 100) and progress
        let nextMilestone = 7;
        let nextName = '星辰学徒';
        if (streak >= 7) { nextMilestone = 30; nextName = '月光智者'; }
        if (streak >= 30) { nextMilestone = 100; nextName = '银河导师'; }

        const milestoneProgress = Math.min(100, (streak / nextMilestone) * 100);
        const daysToGo = nextMilestone - streak;

        let streakHint = '';
        if (streak < 100 && daysToGo > 0) {
          streakHint = `再坚持 ${daysToGo} 天解锁${nextName} ✦`;
        }

        this.setData({
          dailyStreak: streak,
          streakEncouragement: encouragement,
          nextMilestone,
          milestoneProgress,
          streakHint,
        });
      }
    }).catch(() => {
      // Silently fail — streak info is optional enhancement, not critical
    });
  },

  // ---- Card flip ----

  onCardTap() {
    if (this.data.isFlipped || this.data.isAnimating) return;

    this.setData({ isAnimating: true });

    // Haptic feedback
    wx.vibrateShort({ type: 'light' }).catch(() => {});

    // Midpoint (~700ms): swap card faces
    this._midFlipTimer = setTimeout(() => {
      this.setData({
        backHidden: true,
        frontVisible: true,
      });
    }, 700);

    // End of flip animation (1.5s): glow + teaching reveal
    this._endFlipTimer = setTimeout(() => {
      this.setData({
        isFlipped: true,
        isAnimating: false,
      });

      // Play reveal sound when flip completes
      try { playCardRevealSound(); } catch(e) {}

      // Golden glow (0.3s), then show teaching content
      this.setData({ showGlow: true });

      this._glowTimer = setTimeout(() => {
        this.setData({ showTeaching: true });
        this._saveCollectionProgress();

        // Store flipped date so it persists across page revisits
        const today = getTodayStr();
        wx.setStorageSync('daily_card_flipped_date', today);

        // Show push subscription prompt (one-time, gentle)
        this._showPushPrompt();
      }, 300);
    }, 1500);
  },

  // ---- Diary ----

  onDiaryInput(e) {
    this.setData({ diaryText: e.detail.value });
  },

  async onDiarySave() {
    if (this.data.diarySaving || !this.data.diaryText.trim()) return;
    if (!this.data.dailyCard) return;

    this.setData({ diarySaving: true });
    try {
      await request('/diary/entries', {
        method: 'POST',
        data: {
          reflection: this.data.diaryText.trim(),
          card_id: this.data.dailyCard.id,
        },
      });
      this.setData({ diarySaved: true, diarySaving: false });
      try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
      wx.showToast({ title: '记录成功', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
      this.setData({ diarySaving: false });
    }
  },

  // ---- Image events ----

  onCardImgLoad() {
    this.setData({ cardImgLoaded: true });
  },

  onCardImgError() {
    this.setData({ cardImgError: true });
  },

  // ---- Retry ----

  onRetry() {
    this.setData({
      pageError: null,
      pageLoading: true,
      teachingError: null,
    });
    this.onLoad();
  },

  onRetryTeaching() {
    if (this.data.dailyCard) {
      this._loadTeaching(this.data.dailyCard.id);
    }
  },

  // ---- Push subscription ----

  /** Show the push subscription prompt (one-time, not a nag) */
  _showPushPrompt() {
    // Only prompt once per user per lifetime
    const alreadyPrompted = wx.getStorageSync('push_prompted');
    const alreadySubscribed = wx.getStorageSync('push_daily_subscribed');
    if (alreadyPrompted || alreadySubscribed) return;

    // Delay slightly to let the teaching area appear first
    this._pushPromptTimer = setTimeout(() => {
      this.setData({ showPushPrompt: true });
      wx.setStorageSync('push_prompted', true);
    }, 2000);
  },

  /** User accepted — call wx.requestSubscribeMessage then report to backend */
  onAcceptPush() {
    this.setData({ showPushPrompt: false });
    wx.requestSubscribeMessage({
      tmplIds: ['TEMPLATE_DAILY_CARD'],
      success: (res) => {
        const accepted = res['TEMPLATE_DAILY_CARD'] === 'accept';
        if (accepted) {
          wx.setStorageSync('push_daily_subscribed', true);
          this.setData({ pushSubscribed: true });
          wx.showToast({ title: '订阅成功，每日推送 ✦', icon: 'none', duration: 2000 });
          // Report to backend
          this._reportSubscription(accepted);
        } else {
          wx.showToast({ title: '已关闭推送', icon: 'none', duration: 1500 });
        }
      },
      fail: () => {
        // User dismissed or error — silently degrade
      },
    });
  },

  /** User declined — dismiss prompt, no further action */
  onDismissPush() {
    this.setData({ showPushPrompt: false });
    wx.showToast({ title: '暂不需要，随时可在设置中开启', icon: 'none', duration: 1500 });
  },

  /** Report subscription status to backend */
  async _reportSubscription(accepted) {
    try {
      const { request } = require('../../utils/api');
      const app = getApp();
      const user = app.globalData.user || wx.getStorageSync('user');
      const openid = user?.openid || '';
      // We need the openid — get it from the cached user object
      const resp = await wx.login();
      // Use the login code to get openid on backend side — for subscription
      // we just send what we have; the backend stores it from the user record
      await request('/notify/subscribe', {
        method: 'POST',
        data: {
          openid: openid,
          template_id: 'TEMPLATE_DAILY_CARD',
          accept: accepted,
        },
      });
    } catch (err) {
      // Silent degrade — subscription preference stored locally
    }
  },

  // ---- Cleanup ----

  onUnload() {
    if (this._midFlipTimer) { clearTimeout(this._midFlipTimer); this._midFlipTimer = null; }
    if (this._endFlipTimer) { clearTimeout(this._endFlipTimer); this._endFlipTimer = null; }
    if (this._glowTimer) { clearTimeout(this._glowTimer); this._glowTimer = null; }
    if (this._pushPromptTimer) { clearTimeout(this._pushPromptTimer); this._pushPromptTimer = null; }
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    if (this._midFlipTimer) { clearTimeout(this._midFlipTimer); this._midFlipTimer = null; }
    if (this._endFlipTimer) { clearTimeout(this._endFlipTimer); this._endFlipTimer = null; }
    if (this._glowTimer) { clearTimeout(this._glowTimer); this._glowTimer = null; }
    if (this._pushPromptTimer) { clearTimeout(this._pushPromptTimer); this._pushPromptTimer = null; }
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
