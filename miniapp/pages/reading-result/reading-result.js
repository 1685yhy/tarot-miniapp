// pages/reading-result/reading-result.js
const { request, getFriendlyError } = require('../../utils/api');
const { cardEnter } = require('../../utils/animate');
const { computeImagePath } = require('../../utils/cards');

// ---- Spread type name mapping for share title ----
const SPREAD_TYPE_NAMES = {
  three_card: '三牌占卜',
  celtic_cross: '凯尔特十字',
  daily: '每日占卜',
  relationship: '关系分析',
  career_path: '事业路线',
  weekly_outlook: '周运势',
  love_reading: '爱情占卜',
  fortune_telling: '财运占卜',
};

Page({
  data: {
    reading: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,
    showFullInterpretation: false,

    // 3-stage loading sequence
    loadingStage: 1,        // 1 = 洗牌中, 2 = 翻牌中, 3 = 星光解读中
    loadingDotCount: 0,     // 0..3 — how many dots are lit in stage 3
    loadingTimeText: '',    // dynamic status text in stage 3
    showWaitOptions: false, // show the "continue waiting?" UI after timeout

    // Save / share
    isSaved: false,         // whether this reading is in saved_readings storage

    // ---- wx.createAnimation native animation system ----
    useNativeAnim: true,
    // Staggered card entrance animations (one per drawn card)
    cardAnimData: [],

    // Interactive card enlargement
    enlargedCardIndex: -1,   // -1 = none; 0/1/2 = which card is enlarged
    isFlipped: false,        // front (false) or back (true)
    flipState: '',           // '' | 'flip-out' | 'flip-in'
    isAnimatingExit: false,  // true during exit animation before reset
  },

  onLoad(options) {
    const id = options && options.id;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }
    this._id = id;
    this._cachedReading = null;

    // Check if already saved in local storage
    const saved = wx.getStorageSync('saved_readings') || [];
    this.setData({ isSaved: saved.includes(id) });
    this._cachedError = null;

    // Start the 3-stage ritual animation
    this._startStages();

    // Fire the API call in parallel — result is cached until stage 3 begins
    this._load();
  },

  /* ---------------------------------------------------------------
     Stage Progression
     --------------------------------------------------------------- */

  _startStages() {
    this.setData({ loadingStage: 1, loadingDotCount: 0, loadingTimeText: '', showWaitOptions: false });

    // Stage 1: 洗牌中 — 2s (Emphasis: ritual pacing, not motion timing)
    this._stageTimer1 = setTimeout(() => {
      if (this._destroyed) return;

      // Stage 2: 翻牌中 — 2s (Emphasis: ritual pacing)
      this.setData({ loadingStage: 2 });
      this._stageTimer2 = setTimeout(() => {
        if (this._destroyed) return;

        // Stage 3: 星光解读中 — real waiting with progress feedback
        this.setData({
          loadingStage: 3,
          loadingDotCount: 0,
          loadingTimeText: '约 15-20 秒',
          showWaitOptions: false,
        });
        this._startStage3();
        // If the API already returned during stages 1-2, show result now
        this._tryShowResult();
      }, 2000);
    }, 2000);
  },

  /* ---------------------------------------------------------------
     Stage 3 — Progress Dots + Timeout Messages
     --------------------------------------------------------------- */

  _startStage3() {
    // Light up one dot every ~5s (3 dots total ≈ 15s) — UX pacing for anticipation
    this._dotTimer = setInterval(() => {
      if (this._destroyed) return;
      const next = Math.min(this.data.loadingDotCount + 1, 3);
      this.setData({ loadingDotCount: next });
    }, 5000);

    // After 25 seconds: polite nudge
    this._timeout25 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '仍在努力中，请稍等...' });
    }, 25000);

    // After 50 seconds: firmer nudge
    this._timeout50 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '可能需要更长时间，请耐心等待...' });
    }, 50000);

    // After 55 seconds: offer a choice
    this._timeout55 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '', showWaitOptions: true });
    }, 55000);
  },

  /* ---------------------------------------------------------------
     API Fetch — runs in parallel with stages
     --------------------------------------------------------------- */

  async _load() {
    try {
      const reading = await request('/readings/' + this._id);
      if (this._destroyed) return;

      // Clean AI Markdown formatting
      if (reading && reading.interpretation) {
        reading.interpretation = reading.interpretation
          .replace(/^#{1,4}\s+(\*\*)?[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]*(\*\*)?\s*/gmu, '')
          .replace(/\*\*(.+?)\*\*/g, '$1')
          .replace(/^---+\s*$/gm, '')
          .replace(/^\*\s+/gm, '· ')
          .replace(/^-\s+/gm, '')
          .replace(/\n{3,}/g, '\n\n')
          .trim();
      }

      // Compute image paths for each drawn card
      if (reading && reading.drawn_cards) {
        reading.drawn_cards = reading.drawn_cards.map(card => ({
          ...card,
          imagePath: computeImagePath(card),
        }));
      }

      this._cachedReading = reading;
      this._tryShowResult();
    } catch (err) {
      if (this._destroyed) return;
      this._cachedError = getFriendlyError(err);
      this._tryShowResult();
    }
  },

  /* ---------------------------------------------------------------
     Transition to Result
     Only fires when both stage 3 has begun AND the API has returned,
     so stages 1-2 always play through in full.
     --------------------------------------------------------------- */

  _tryShowResult() {
    if (this.data.loadingStage !== 3) return;

    this._clearStage3Timers();

    if (this._cachedReading) {
      this.setData({ reading: this._cachedReading, pageLoading: false });
      // Trigger staggered card entrance animation after render
      this._animateCardReveal();
    } else if (this._cachedError) {
      this.setData({ pageLoading: false, pageError: this._cachedError });
    }
  },

  /* ---------------------------------------------------------------
     Timer Cleanup
     --------------------------------------------------------------- */

  _clearStageTimers() {
    if (this._stageTimer1) { clearTimeout(this._stageTimer1); this._stageTimer1 = null; }
    if (this._stageTimer2) { clearTimeout(this._stageTimer2); this._stageTimer2 = null; }
    this._clearStage3Timers();
  },

  _clearStage3Timers() {
    if (this._dotTimer) { clearInterval(this._dotTimer); this._dotTimer = null; }
    if (this._timeout25) { clearTimeout(this._timeout25); this._timeout25 = null; }
    if (this._timeout50) { clearTimeout(this._timeout50); this._timeout50 = null; }
    if (this._timeout55) { clearTimeout(this._timeout55); this._timeout55 = null; }
  },

  /** Animate drawn cards appearing one by one using wx.createAnimation stagger */
  _animateCardReveal() {
    if (!this.data.useNativeAnim) return;
    const cards = this.data.reading && this.data.reading.drawn_cards;
    if (!cards || cards.length === 0) return;

    const anims = [];
    for (let i = 0; i < cards.length; i++) {
      // Each card enters with cardEnter + increasing delay for cascade effect
      anims.push(cardEnter(450, i * 120));
    }
    this.setData({ cardAnimData: anims });
  },

  /* ---------------------------------------------------------------
     Handlers
     --------------------------------------------------------------- */

  // —— Card image loading ——
  onCardImgLoad(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`reading.drawn_cards[${idx}]._imgLoaded`]: true });
    }
  },

  onCardImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`reading.drawn_cards[${idx}]._imgError`]: true });
    }
  },

  onEnlargedImgLoad() {
    this.setData({ enlargedImgLoaded: true });
  },

  onUnload() {
    this._destroyed = true;
    this._clearStageTimers();
  },

  onContinueWaiting() {
    this.setData({ showWaitOptions: false, loadingTimeText: '好的，继续为你解读...' });

    // Restart the 55-second timer so the prompt can reappear later
    if (this._timeout55) { clearTimeout(this._timeout55); }
    this._timeout55 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '', showWaitOptions: true });
    }, 55000);
  },

  onCheckLater() {
    this._clearStageTimers();
    wx.showToast({ title: '解读生成后可在记录中查看', icon: 'none', duration: 2000 });
    setTimeout(() => { wx.navigateBack(); }, 2200);
  },

  onCardSwiperChange(e) {
    this.setData({ activeCardIndex: e.detail.current });
  },

  /* ---------------------------------------------------------------
     Interactive Card — Tap to Enlarge
     --------------------------------------------------------------- */

  onCardTap(e) {
    const index = e.currentTarget.dataset.index;
    if (index === undefined) return;
    this.setData({
      enlargedCardIndex: index,
      isFlipped: false,
      flipState: '',
      isAnimatingExit: false,
    });
  },

  onEnlargedCardTap() {
    if (this.data.isAnimatingExit) return;
    if (this.data.flipState === 'flip-out' || this.data.flipState === 'flip-in') return;

    // Phase 1: collapse scaleX(1→0)
    this.setData({ flipState: 'flip-out' });

    setTimeout(() => {
      if (this._destroyed) return;
      // Phase 2: swap content, expand scaleX(0→1)
      this.setData({ isFlipped: !this.data.isFlipped, flipState: 'flip-in' });

      setTimeout(() => {
        if (this._destroyed) return;
        this.setData({ flipState: '' });
      }, 200);
    }, 200);
  },

  onOverlayTap() {
    if (this.data.isAnimatingExit) return;
    // Start exit animation
    this.setData({ isAnimatingExit: true });
    setTimeout(() => {
      if (this._destroyed) return;
      this.setData({
        enlargedCardIndex: -1,
        isFlipped: false,
        flipState: '',
        isAnimatingExit: false,
      });
    }, 300);
  },

  /* ---- Swipe down to dismiss ---- */
  onOverlayTouchStart(e) {
    this._touchStartY = e.touches[0].clientY;
  },

  onOverlayTouchMove(e) {
    // prevent pull-to-refresh / page scroll
  },

  onOverlayTouchEnd(e) {
    if (!this._touchStartY) return;
    const deltaY = e.changedTouches[0].clientY - this._touchStartY;
    if (deltaY > 80) {
      this._touchStartY = 0;
      if (!this.data.isAnimatingExit) this.onOverlayTap();
    }
    this._touchStartY = 0;
  },

  onToggleFull() {
    this.setData({ showFullInterpretation: !this.data.showFullInterpretation });
  },

  onRetry() {
    this._clearStageTimers();
    this._destroyed = false;
    this._cachedReading = null;
    this._cachedError = null;
    this._startStages();
    this._load();
  },

  onAskMore() {
    const reading = this.data.reading;
    if (!reading) return;
    wx.navigateTo({ url: '/pages/chat/chat?readingId=' + reading.id });
  },

  onNewReading() {
    wx.navigateBack();
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  /* ---------------------------------------------------------------
     Share — WeChat built-in share
     --------------------------------------------------------------- */

  onShareAppMessage() {
    const reading = this.data.reading;
    if (!reading) return { title: '星光塔罗解读' };

    const spreadName = SPREAD_TYPE_NAMES[reading.spread_type] || reading.spread_type || '三牌占卜';
    return {
      title: `我的星光解读 ✦ ${spreadName}`,
      path: `/pages/reading-result/reading-result?id=${reading.id}`,
    };
  },

  /* ---------------------------------------------------------------
     Save / Unsave — local storage
     --------------------------------------------------------------- */

  onSaveReading() {
    const reading = this.data.reading;
    if (!reading) return;

    const saved = wx.getStorageSync('saved_readings') || [];
    if (saved.includes(reading.id)) {
      this.setData({ isSaved: true });
      wx.showToast({ title: '已收藏', icon: 'success' });
      return;
    }
    saved.push(reading.id);
    wx.setStorageSync('saved_readings', saved);
    this.setData({ isSaved: true });
    wx.showToast({ title: '已收藏', icon: 'success' });
  },

  onUnsaveReading() {
    const reading = this.data.reading;
    if (!reading) return;

    let saved = wx.getStorageSync('saved_readings') || [];
    saved = saved.filter(id => id !== reading.id);
    wx.setStorageSync('saved_readings', saved);
    this.setData({ isSaved: false });
    wx.showToast({ title: '已取消收藏', icon: 'none' });
  },
});
