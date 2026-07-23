// pages/community/community.js
const { request, getFriendlyError } = require('../../utils/api');

Page({
  data: {
    // Page state
    pageLoading: true,
    pageError: null,

    // Today's topic
    topic: null,

    // Posts
    posts: [],
    page: 1,
    total: 0,
    hasMore: true,
    loadingMore: false,

    // Composer
    showComposer: false,
    composerContent: '',
    composerFocused: false,
    submitting: false,
  },

  async onLoad() {
    try {
      await this._loadTodayTopic();
      await this._loadPosts(1);
      this.setData({ pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  /** Load today's topic from API */
  async _loadTodayTopic() {
    const data = await request('/community/today');
    // Guard: API must return { topic: { id, title } } shape
    if (data && data.topic && data.topic.id) {
      this.setData({ topic: data });
    } else {
      throw new Error('话题数据格式异常');
    }
  },

  /** Load posts for current topic */
  async _loadPosts(page) {
    if (!this.data.topic) return;
    const topicId = this.data.topic.topic.id;
    const limit = 20;
    const data = await request(
      `/community/posts?topic_id=${topicId}&page=${page}&limit=${limit}`
    );
    const posts = data.posts || [];
    if (page === 1) {
      this.setData({
        posts,
        page,
        total: data.total,
        hasMore: data.has_more,
      });
    } else {
      this.setData({
        posts: [...this.data.posts, ...posts],
        page,
        hasMore: data.has_more,
      });
    }
  },

  /** Load more posts (scroll to bottom) */
  async loadMorePosts() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    try {
      await this._loadPosts(this.data.page + 1);
    } catch (_err) {
      wx.showToast({ title: '加载更多失败', icon: 'none' });
    }
    this.setData({ loadingMore: false });
  },

  /** Format datetime to relative time string */
  _formatTime(datetimeStr) {
    if (!datetimeStr) return '';
    const now = Date.now();
    const date = new Date(datetimeStr);
    const diffMs = now - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    if (diffHour < 24) return `${diffHour} 小时前`;
    if (diffDay < 7) return `${diffDay} 天前`;

    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  },

  /** Navigate back */
  goBack() {
    wx.navigateBack({ delta: 1 });
  },

  /** Open post composer */
  openComposer() {
    this.setData({ showComposer: true, composerFocused: true });
  },

  /** Close composer */
  closeComposer() {
    this.setData({ showComposer: false, composerFocused: false });
  },

  /** Prevent overlay close when tapping inside sheet */
  preventClose() {
    // Stop propagation
  },

  /** Composer text input */
  onComposerInput(e) {
    this.setData({ composerContent: e.detail.value });
  },

  /** Submit anonymous post */
  async onSubmitPost() {
    if (this.data.submitting || !this.data.composerContent.trim()) return;
    if (!this.data.topic) {
      wx.showToast({ title: '话题未加载', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    try {
      const data = await request('/community/posts', {
        method: 'POST',
        data: {
          topic_id: this.data.topic.topic.id,
          content: this.data.composerContent.trim(),
        },
      });
      // Prepend new post to list
      this.setData({
        posts: [data, ...this.data.posts],
        total: this.data.total + 1,
        showComposer: false,
        composerContent: '',
        submitting: false,
      });
      // Update topic post count
      const topic = this.data.topic;
      topic.post_count = (topic.post_count || 0) + 1;
      this.setData({ topic });
      wx.showToast({ title: '倾诉已发布 ✦', icon: 'success' });
      wx.vibrateShort({ type: 'light' }).catch(() => {});
    } catch (err) {
      wx.showToast({ title: '发布失败，请重试', icon: 'none' });
      this.setData({ submitting: false });
    }
  },

  /** Retry after error */
  onRetry() {
    this.setData({
      pageError: null,
      pageLoading: true,
      posts: [],
      page: 1,
      total: 0,
      hasMore: true,
    });
    this.onLoad();
  },

  onUnload() {
    // Cleanup
  },
});
