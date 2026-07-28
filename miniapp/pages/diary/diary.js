// pages/diary/diary.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

// Mood score map for trend analysis
const MOOD_SCORE_MAP = { happy: 4.5, calm: 3.5, excited: 5, anxious: 2, sad: 1, thoughtful: 3 };

Page({
  data: {
    entries: [],
    showCreate: false,
    mood: '',
    reflection: '',
    reflectionPlaceholder: '',
    creating: false,
    page: 1,
    hasMore: true,
    pageLoading: true,
    pageError: null,
    loadingMore: false,
    todayCard: null,
    topCard: '',
    moodTrend: '',

    // Weekly AI review
    weeklyReview: null,
    reviewLoading: false,
    reviewError: null,

    // Card image error
    diaryCardImgError: false,
    entryCardImgErrors: {},
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },

  async onShow() {
    this.setData({ page: 1, entries: [], pageLoading: true, weeklyReview: null });
    await this.loadEntries();
    this._loadTodayCard();
  },

  async loadEntries() {
    try {
      const data = await request(`/diary/entries?page=${this.data.page}`);
      const rawEntries = data.entries || [];
      // Compute card thumbnail paths for each entry
      const entries = [...this.data.entries, ...rawEntries.map(e => {
        if (e.card) {
          e.cardImagePath = computeImagePath(e.card);
        }
        return e;
      })];
      this.setData({
        entries,
        hasMore: rawEntries.length === 20,
        pageLoading: false,
      });
      this._computeRetrospect();
      // Update placeholder after entries loaded
      this._updatePlaceholder();
      // Auto-load weekly review if enough entries
      if (entries.length >= 3 && !this.data.weeklyReview && !this.data.reviewLoading) {
        this._loadWeeklyReview();
      }
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  async loadMore() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.setData({ loadingMore: true, page: this.data.page + 1 });
    await this.loadEntries();
    this.setData({ loadingMore: false });
  },

  showCreateModal() {
    this.setData({ showCreate: true, diaryCardImgError: false });
  },

  hideCreateModal() {
    this.setData({ showCreate: false, mood: '', reflection: '' });
  },

  preventClose() {
    // 阻止事件冒泡——防止点击 modal 内部元素时关闭弹窗
  },

  /** Handle card thumbnail load error in diary create modal */
  onDiaryCardImgError() {
    this.setData({ diaryCardImgError: true });
  },

  onMoodSelect(e) {
    this.setData({ mood: e.currentTarget.dataset.mood });
  },

  onReflectionInput(e) {
    this.setData({ reflection: e.detail.value });
  },

  async onCreateEntry() {
    if (this.data.creating) return;
    if (!this.data.mood) {
      wx.showToast({ title: '请选择心情', icon: 'none' });
      return;
    }
    this.setData({ creating: true });
    try {
      const entry = await request('/diary/entries', {
        method: 'POST',
        data: { mood: this.data.mood, reflection: this.data.reflection },
      });
      if (!entry) {
        throw new Error("创建日记失败");
      }
      this.setData({
        entries: [entry, ...this.data.entries],
        showCreate: false,
        mood: '',
        reflection: '',
        creating: false,
      });
      wx.showToast({ title: '记录成功 ✨', icon: 'success' });
      // Refresh weekly review after new entry
      if (this.data.entries.length >= 3) {
        this._loadWeeklyReview();
      }
    } catch (err) {
      wx.showToast({ title: '记录失败', icon: 'none' });
      this.setData({ creating: false });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true, page: 1, entries: [], weeklyReview: null });
    this.loadEntries();
  },

  /** Load today's card to show in the editor header */
  async _loadTodayCard() {
    try {
      const card = await request('/cards/daily');
      card.imagePath = computeImagePath(card);
      this.setData({ todayCard: card });
      this._updatePlaceholder();
    } catch(e) {
      // 静默降级——今日卡牌加载失败不影响记录列表
    }
  },

  /** Update textarea placeholder based on today's card context */
  _updatePlaceholder() {
    const card = this.data.todayCard;
    if (card && card.name_zh) {
      this.setData({
        reflectionPlaceholder: `这张${card.name_zh}让你想到了什么？你此刻的心情是怎样的？`
      });
    } else {
      this.setData({
        reflectionPlaceholder: '此刻你的心情是怎样的？'
      });
    }
  },

  /** Compute local fallback retrospect data (kept for backward compat) */
  _computeRetrospect() {
    const entries = this.data.entries;
    if (entries.length < 3) return;

    // 统计最常出现的牌
    const cardCount = {};
    entries.forEach(e => {
      const name = e.card?.name_zh;
      if (name) cardCount[name] = (cardCount[name] || 0) + 1;
    });
    const topEntry = Object.entries(cardCount).sort((a, b) => b[1] - a[1])[0];
    const topCard = topEntry?.[0] || '未知';

    // 心情趋势：最近3条记录的平均心情（1-5分）
    const recent = entries.slice(0, 3);
    const avgMood = recent.reduce((s, e) => {
      return s + (e.mood_score || MOOD_SCORE_MAP[e.mood] || 3);
    }, 0) / recent.length;
    const moodTrend = avgMood > 3.5 ? '在变好 ✦' : avgMood < 2.5 ? '有些低落' : '比较平稳';

    this.setData({ topCard, moodTrend });
  },

  // ============================================================
  // AI Weekly Review
  // ============================================================

  /** Fetch AI weekly review from backend */
  async _loadWeeklyReview() {
    if (this.data.reviewLoading) return;
    this.setData({ reviewLoading: true, reviewError: null });
    try {
      const review = await request('/diary/review?period=weekly');
      // Compute emoji trend curve for mood visualization
      if (review.mood_trends && review.mood_trends.length > 0) {
        review.moodTrendCurve = this._computeMoodTrendCurve(review.mood_trends);
      }
      this.setData({ weeklyReview: review, reviewLoading: false });
    } catch (err) {
      this.setData({ reviewLoading: false, reviewError: getFriendlyError(err) });
    }
  },

  /** User tap to refresh weekly review */
  onRefreshReview() {
    this._loadWeeklyReview();
    wx.vibrateShort({ type: 'light' }).catch(() => {});
  },

  /** Get CSS width percentage for mood chart bar */
  _getMoodBarWidth(score) {
    return Math.max(10, (score / 5) * 100);
  },

  /** Compute emoji mood trend curve from weekly review data */
  _computeMoodTrendCurve(trends) {
    const BLOCK_MAP = ['▁', '▁', '▂', '▃', '▅', '▇'];
    const blocks = trends.map(t => {
      const score = Math.round(t.mood_score || 3);
      return BLOCK_MAP[Math.min(Math.max(score, 1), 5)];
    });
    return '😔 ' + blocks.join(' ') + ' 😊';
  },

  /** Handle entry card image load error — hide the broken thumbnail */
  onEntryCardImageError(e) {
    const entryId = e.currentTarget.dataset.entryId;
    if (!entryId) return;
    const key = `entryCardImgErrors.${entryId}`;
    this.setData({ [key]: true });
  },

  /** Floating AI review button tap — scroll to review card */
  onTapFloatingReview() {
    wx.pageScrollTo({
      selector: '.review-card',
      duration: 300,
    });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
