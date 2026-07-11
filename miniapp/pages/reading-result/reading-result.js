// pages/reading-result/reading-result.js
const { request } = require('../../utils/api');

Page({
  data: {
    reading: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,
    showFullInterpretation: false,
    loadingStage: 0,
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
    this.setData({ pageLoading: true, loadingStage: 0 });
    // Animate through stages while loading
    this._stageTimer1 = setTimeout(() => { this.setData({ loadingStage: 1 }); }, 800);
    this._stageTimer2 = setTimeout(() => { this.setData({ loadingStage: 2 }); }, 2000);
    this._stageTimer3 = setTimeout(() => { this.setData({ loadingStage: 3 }); }, 4000);
    try {
      const reading = await request(`/readings/${id}`);
      this.setData({ reading, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.errMsg || '加载失败' });
    } finally {
      this._stageTimer1 && clearTimeout(this._stageTimer1);
      this._stageTimer2 && clearTimeout(this._stageTimer2);
      this._stageTimer3 && clearTimeout(this._stageTimer3);
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
