// pages/diary/diary.js
const { request } = require('../../utils/api');

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
  },

  async onShow() {
    this.setData({ page: 1, entries: [], pageLoading: true });
    await this.loadEntries();
  },

  async loadEntries() {
    try {
      const data = await request(`/diary/entries?page=${this.data.page}`);
      this.setData({
        entries: [...this.data.entries, ...(data.entries || [])],
        hasMore: data.entries && data.entries.length === 20,
        pageLoading: false,
      });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
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
});
