// pages/reading-result/reading-result.js
const { request } = require('../../utils/api');

const QUOTES = [
  '星光不问赶路人，时光不负有心人',
  '每一次凝视星海，都是在凝视另一个自己',
  '命运不是机遇，而是选择',
  '答案早已在你心中，星光只是帮你照亮它',
];

Page({
  data: {
    reading: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,
    showFullInterpretation: false,
    loadingStage: 0,
    loadingQuote: '',
    _destroyed: false,
    _quoteTimer: null,
  },

  onLoad(options) {
    const id = options && options.id;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }
    this._id = id;
    this._load();
  },

  async _load() {
    const id = this._id;
    const qi = Math.floor(Math.random() * QUOTES.length);
    this.setData({ pageLoading: true, loadingStage: 0, loadingQuote: QUOTES[qi] });

    let qi2 = qi;
    this.data._quoteTimer = setInterval(() => {
      qi2 = (qi2 + 1) % QUOTES.length;
      if (!this.data._destroyed && this.data.pageLoading) {
        this.setData({ loadingQuote: QUOTES[qi2] });
      }
    }, 5000);

    try {
      // 已完成的解读瞬间返回，不需要延迟动画
      const reading = await request('/readings/' + id);
      if (this.data._destroyed) return;
      this.setData({ reading: reading, pageLoading: false });
    } catch (err) {
      if (this.data._destroyed) return;
      this.setData({ pageLoading: false, pageError: (err && err.message) || '加载失败' });
    }

    if (this.data._quoteTimer) { clearInterval(this.data._quoteTimer); this.data._quoteTimer = null; }
  },

  onUnload() {
    this.data._destroyed = true;
    if (this.data._quoteTimer) { clearInterval(this.data._quoteTimer); this.data._quoteTimer = null; }
  },

  onCardSwiperChange(e) {
    this.setData({ activeCardIndex: e.detail.current });
  },

  onToggleFull() {
    this.setData({ showFullInterpretation: !this.data.showFullInterpretation });
  },

  onRetry() {
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
});
