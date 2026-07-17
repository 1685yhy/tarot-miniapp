// pages/reading-result/reading-result.js
const { request } = require('../../utils/api');

const QUOTES = [
  '星光不问赶路人，时光不负有心人',
  '每一次凝视星海，都是在凝视另一个自己',
  '命运不是机遇，而是选择',
  '当你仰望星空，你看到的不是遥远的过去，而是内心的倒影',
  '所有的偶然，都是另一种形式的必然',
  '答案早已在你心中，星光只是帮你照亮它',
  '你走过的路，每一步都算数',
  '真正的智慧，是知道自己的无知',
  '人不能两次踏入同一条河流，但可以两次仰望同一片星空',
  '世界上只有一种英雄主义，就是看清生活真相之后依然热爱它',
  '你的心就是你的指南针，不必向外界寻求方向',
  '万物皆有裂痕，那是光照进来的地方',
  '有些路看起来很近，走起来却很远',
  '我们都在阴沟里，但仍有人仰望星空',
  '你所经历的一切，都是在帮你成为你自己',
  '认识你自己，是终身的课题',
  '当你感到迷茫，说明你已经在路上了',
  '不要害怕改变，那可能是蜕变的开始',
  '每一个结束都是新的开始，每一次告别都是重逢的序章',
  '种一棵树最好的时间是十年前，其次是现在',
  '内心的宁静，是最强大的力量',
  '夜晚的尽头是黎明，而你已经走过了最黑暗的时刻',
  '星辰不需要被看见，它们自会发光',
  '每一次抽牌，都是与潜意识的一次对话',
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
    // Pick a random quote and rotate during loading
    const idx = Math.floor(Math.random() * QUOTES.length);
    this.setData({ pageLoading: true, loadingStage: 0, loadingQuote: QUOTES[idx] });
    let qi = idx;
    this.data._quoteTimer = setInterval(() => {
      qi = (qi + 1) % QUOTES.length;
      if (!this.data._destroyed && this.data.pageLoading) {
        this.setData({ loadingQuote: QUOTES[qi] });
      }
    }, 5000);

    // Animate through stages while loading
    this._stageTimer1 = setTimeout(() => { this.setData({ loadingStage: 1 }); }, 800);
    this._stageTimer2 = setTimeout(() => { this.setData({ loadingStage: 2 }); }, 2000);
    this._stageTimer3 = setTimeout(() => { this.setData({ loadingStage: 3 }); }, 4000);
    try {
      const reading = await request(`/readings/${id}`);
      if (this.data._destroyed) return;
      this.setData({ reading, pageLoading: false });
    } catch (err) {
      if (this.data._destroyed) return;
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    } finally {
      this._stageTimer1 && clearTimeout(this._stageTimer1);
      this._stageTimer2 && clearTimeout(this._stageTimer2);
      this._stageTimer3 && clearTimeout(this._stageTimer3);
      this.data._quoteTimer && clearInterval(this.data._quoteTimer);
    }
  },

  onUnload() {
    this.data._destroyed = true;
    this._stageTimer1 && clearTimeout(this._stageTimer1);
    this._stageTimer2 && clearTimeout(this._stageTimer2);
    this._stageTimer3 && clearTimeout(this._stageTimer3);
    this.data._quoteTimer && clearInterval(this.data._quoteTimer);
  },

  onCardSwiperChange(e) {
    this.setData({ activeCardIndex: e.detail.current });
  },

  onSwiperPrev() {
    const total = this.data.reading?.drawn_cards?.length || 0;
    if (total === 0) return;
    const prev = (this.data.activeCardIndex - 1 + total) % total;
    this.setData({ activeCardIndex: prev });
  },

  onSwiperNext() {
    const total = this.data.reading?.drawn_cards?.length || 0;
    if (total === 0) return;
    const next = (this.data.activeCardIndex + 1) % total;
    this.setData({ activeCardIndex: next });
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

  onShareAppMessage() {
    const { reading } = this.data;
    const cards = reading?.drawn_cards || [];
    const cardNames = cards.map(c => c.card_name).join('、');
    const title = cardNames
      ? `我抽到了 ${cardNames} —— 来看看塔罗的解读吧`
      : '星光映照，揭秘你的命运';
    return {
      title,
      desc: 'AI星光映照解读，揭示你的过去、现在与未来',
    };
  },

  onToggleFull() {
    this.setData({ showFullInterpretation: !this.data.showFullInterpretation });
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

  async onReinterpret() {
    const id = this.options?.id;
    if (!id) return;
    wx.showLoading({ title: '重新生成解读...' });
    try {
      const result = await request(`/readings/${id}/reinterpret`, { method: 'POST' });
      this.setData({ reading: result });
      wx.hideLoading();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '生成失败，请重试', icon: 'none' });
    }
  },
});
