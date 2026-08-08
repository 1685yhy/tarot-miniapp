// pages/review/review.js — 满月复盘（开发 04 · 星光记录为主角的「我的流」）
// 原型页 14：满月动画 + AI 复盘卡 + 愿望回望三态 + 分享
const { request, getFriendlyError } = require('../../utils/api');

// 愿望回望三态（✓已生长 / ○生长中 / ✕待回应）
const STATUS_META = {
  grown: { icon: '✓', label: '已生长', cls: 'ok' },
  active: { icon: '○', label: '生长中', cls: 'go' },
  answered: { icon: '✕', label: '待回应', cls: 'no' },
};

Page({
  data: {
    loading: true,
    pageError: null,
    regenerating: false,

    // 复盘数据
    review: null,          // {date, date_range, wishes, review, tips, has_data, cached}
    statusMeta: STATUS_META,
  },

  onLoad() {
    this._load();
  },

  onPullDownRefresh() {
    this._load().finally(() => wx.stopPullDownRefresh());
  },

  async _load() {
    this.setData({ loading: true, pageError: null });
    try {
      const data = await request('/reviews/moon');
      this.setData({ review: this._decorate(data), loading: false });
    } catch (err) {
      this.setData({ loading: false, pageError: getFriendlyError(err) });
    }
  },

  /** 愿望三态展示数据（✓已生长 / ○生长中 / ✕待回应）预计算 */
  _decorate(data) {
    if (!data || !data.wishes) return data;
    const wishes = data.wishes.map(w => {
      const meta = STATUS_META[w.status] || STATUS_META.answered;
      return {
        ...w,
        statusIcon: meta.icon,
        statusLabel: meta.label,
        statusCls: meta.cls,
      };
    });
    return { ...data, wishes };
  },

  onRetry() {
    this._load();
  },

  /** 手动重新生成复盘（当天缓存覆盖） */
  async onRegenerate() {
    if (this.data.regenerating) return;
    this.setData({ regenerating: true });
    try {
      const data = await request('/reviews/moon', { method: 'POST' });
      this.setData({ review: this._decorate(data), regenerating: false });
      wx.showToast({ title: '月光重新为你整理了一遍 ✦', icon: 'none', duration: 2000 });
    } catch (err) {
      this.setData({ regenerating: false });
      wx.showToast({ title: getFriendlyError(err) || '复盘生成失败，请稍后再试', icon: 'none' });
    }
  },

  /** 分享复盘（页面级分享 + 按钮分享） */
  onShare() {
    if (!this.data.review || !this.data.review.has_data) {
      wx.showToast({ title: '有愿望和日记，月亮才能为你复盘', icon: 'none', duration: 2200 });
      return;
    }
    wx.shareAppMessage({
      title: '满月复盘 · 我的愿望回望 ✦',
    });
  },

  onShareAppMessage() {
    const has = this.data.review && this.data.review.has_data;
    return {
      title: has ? '满月复盘 · 我的愿望回望 ✦' : '星光映照 · 新月许愿，满月回望',
      path: '/pages/review/review',
    };
  },

  /** 去许愿（空态引导） */
  onGoWish() {
    wx.navigateTo({ url: '/pages/wish/wish' });
  },
});
