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
  },

  async onShow() {
    this.setData({ page: 1, entries: [] });
    await this.loadEntries();
  },

  async loadEntries() {
    try {
      const data = await request(`/diary/entries?page=${this.data.page}`);
      this.setData({
        entries: [...this.data.entries, ...(data.entries || [])],
        hasMore: data.entries && data.entries.length === 20,
      });
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' });
    }
  },

  async loadMore() {
    if (!this.data.hasMore) return;
    this.setData({ page: this.data.page + 1 });
    await this.loadEntries();
  },

  showCreateModal() {
    this.setData({ showCreate: true });
  },

  hideCreateModal() {
    this.setData({ showCreate: false, mood: '', reflection: '' });
  },

  onMoodSelect(e) {
    this.setData({ mood: e.currentTarget.dataset.mood });
  },

  onReflectionInput(e) {
    this.setData({ reflection: e.detail.value });
  },

  async onCreateEntry() {
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
});
