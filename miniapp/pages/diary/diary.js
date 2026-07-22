// pages/diary/diary.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

Page({
  data: {
    entries: [],
    showCreate: false,
    mood: '',
    reflection: '',
    creating: false,
    page: 1,
    hasMore: true,
    pageLoading: true,
    pageError: null,
    loadingMore: false,
    todayCard: null,
    topCard: '',
    moodTrend: '',
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },

  async onShow() {
    this.setData({ page: 1, entries: [], pageLoading: true });
    await this.loadEntries();
    this._loadTodayCard();
  },

  async loadEntries() {
    try {
      const data = await request(`/diary/entries?page=${this.data.page}`);
      this.setData({
        entries: [...this.data.entries, ...(data.entries || [])],
        hasMore: data.entries && data.entries.length === 20,
        pageLoading: false,
      });
      this._computeRetrospect();
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
    this.setData({ showCreate: true });
  },

  hideCreateModal() {
    this.setData({ showCreate: false, mood: '', reflection: '' });
  },

  preventClose() {
    // 阻止事件冒泡——防止点击 modal 内部元素时关闭弹窗
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
    } catch (err) {
      wx.showToast({ title: '记录失败', icon: 'none' });
      this.setData({ creating: false });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true, page: 1, entries: [] });
    this.loadEntries();
  },

  /** 加载今日卡牌，在编辑器顶部展示 */
  async _loadTodayCard() {
    try {
      const card = await request('/cards/daily');
      card.imagePath = computeImagePath(card);
      this.setData({ todayCard: card });
    } catch(e) {
      // 静默降级——今日卡牌加载失败不影响记录列表
    }
  },

  /** 计算复盘数据：最常出现的牌 + 心情趋势 */
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
    const MOOD_SCORE_MAP = { happy: 4.5, calm: 3.5, excited: 5, anxious: 2, sad: 1, thoughtful: 3 };
    const recent = entries.slice(0, 3);
    const avgMood = recent.reduce((s, e) => {
      return s + (e.mood_score || MOOD_SCORE_MAP[e.mood] || 3);
    }, 0) / recent.length;
    const moodTrend = avgMood > 3.5 ? '在变好 ✦' : avgMood < 2.5 ? '有些低落' : '比较平稳';

    this.setData({ topCard, moodTrend });
  },
});
