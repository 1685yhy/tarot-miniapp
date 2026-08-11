// pages/moon-card/moon-card.js — 月光卡（睡前星语 · T4-3 最小可用版）
// 渲染 GET /moon-card/today：月相 + 星语 + 星光色 + 日期（无海报）。
// 21:00 星语推送点击直达本页；完整版（海报/分享/沉淀）由阶段 2 Task 15 完成。
const { request, getFriendlyError } = require('../../utils/api');

Page({
  data: {
    loading: true,
    pageError: null,
    card: null, // {date, phase:{emoji,label}, phrase, star_color, star_number, source}
  },

  onLoad() {
    this._load();
  },

  async _load() {
    this.setData({ loading: true, pageError: null });
    try {
      const card = await request('/moon-card/today');
      this.setData({ card, loading: false });
    } catch (err) {
      this.setData({
        loading: false,
        pageError: getFriendlyError(err) || '月光暂时迷路了，稍后再来看看',
      });
    }
  },

  onRetry() {
    this._load();
  },
});
