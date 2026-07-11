// pages/reading-result/reading-result.js
const { request } = require('../../utils/api');

Page({
  data: {
    reading: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,
    showFullInterpretation: false,
  },

  async onLoad(options) {
    this.options = options;
    const { id } = options;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }
    await this.loadReading(id);
  },

  async loadReading(id) {
    this.setData({ pageLoading: true });
    try {
      const reading = await request(`/readings/${id}`);
      this.setData({ reading, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.errMsg || '加载失败' });
    }
  },

  onCardSwiperChange(e) {
    this.setData({ activeCardIndex: e.detail.current });
  },

  onCardTap(e) {
    const index = e.currentTarget.dataset.index;
    this.setData({ activeCardIndex: index });
  },

  onToggleInterpretation() {
    this.setData({ showFullInterpretation: !this.data.showFullInterpretation });
  },

  onShareResult() {
    // Share to WeChat
    wx.showShareMenu({
      withShareTicket: true,
    });
  },

  onAskMore() {
    const { reading } = this.data;
    if (!reading) return;
    wx.navigateTo({
      url: `/pages/chat/chat?readingId=${reading.id}`,
    });
  },

  onNewReading() {
    wx.redirectTo({ url: '/pages/reading/reading' });
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onRetry() {
    this.setData({ pageError: null });
    const id = this.options?.id;
    if (id) this.loadReading(id);
  },
});
