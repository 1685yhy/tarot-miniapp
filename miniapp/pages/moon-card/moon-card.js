// pages/moon-card/moon-card.js — 月光卡（睡前星语 · T4-5 完整版）
// 渲染 GET /moon-card/today：月相 + 星语 + 星光色 + 日期。
// 完整版新增（T4-5）：
//   1. 晚安卡海报分享（深空底晚安版星光名片 → share-poster mode="moon"）
//   2. 沉淀引导「睡前三分钟，给今天记一颗星」→ pages/journal/journal
//   3. 分享打点 POST /share/track（share_type="moon_card"）+ 拉新小程序码
// 21:00 星语推送点击直达本页。
const { request, getFriendlyError } = require('../../utils/api');
const analytics = require('../../utils/analytics');

Page({
  data: {
    loading: true,
    pageError: null,
    card: null, // {date, phase:{emoji,label}, phrase, star_color, star_number, source}
    hasCard: false, // WXML 编译环境下 wx:if 不认复杂表达式，JS 预计算
    sharing: false,

    // 晚安卡海报（深空底 · share-poster mode="moon"）
    posterData: null,
    showPoster: false,
  },

  onLoad() {
    this._load();
  },

  async _load() {
    this.setData({ loading: true, pageError: null });
    try {
      const card = await request('/moon-card/today');
      this.setData({ card, hasCard: !!card, loading: false });
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

  // ============================================================
  // 晚安卡海报（T4-5）
  // ============================================================

  /** 生成并预览晚安卡海报（深空底 · 月亮替你收尾今天的晚安版星光名片） */
  onSharePoster() {
    const card = this.data.card;
    if (!card || this.data.sharing) return;
    this.setData({ sharing: true });
    wx.showLoading({ title: '生成晚安卡...', mask: true });
    // 延迟一拍让 loading 显示（与 journal-review 同款）
    setTimeout(() => {
      this.setData({
        posterData: {
          dateText: formatDateText(card.date),
          card,
        },
        showPoster: true,
      });
      wx.hideLoading();
      analytics.trackEvent('moon_card_poster', { date: card.date });
      this.setData({ sharing: false });
    }, 120);
  },

  onClosePoster() {
    this.setData({ showPoster: false });
  },

  onShareMoonPosterToFriend(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'moon_card');
    // 分享打点 + 奖励（fire-and-forget，与解读/手账分享同模式）
    const card = this.data.card || {};
    request('/share/track', {
      method: 'POST',
      data: { channel: 'wechat_friend', share_type: 'moon_card', ref_id: card.date || '' },
    }).then((res) => {
      if (res && res.rewarded) {
        wx.showToast({ title: '分享成功！奖励已发放 ✦', icon: 'success', duration: 2000 });
      }
    }).catch(() => {});
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: '星光映照 · 今晚的月光卡',
      });
    } catch (err) {
      // 降级：先保存海报，再从相册分享
      wx.showToast({
        title: '请先保存海报，再从相册分享',
        icon: 'none',
        duration: 2000,
      });
    }
  },

  // ============================================================
  // 沉淀（设计 4.1）：睡前三分钟，给今天记一颗星
  // ============================================================

  goWriteJournal() {
    wx.navigateTo({ url: '/pages/journal/journal' });
  },

  onShareAppMessage() {
    return {
      title: '星光映照 · 今晚的月光卡',
      path: '/pages/moon-card/moon-card',
    };
  },
});

/** '2026-08-11' → '2026年8月11日 · 晚安' */
function formatDateText(isoDate) {
  if (!isoDate) return '';
  const parts = String(isoDate).split('-');
  if (parts.length !== 3) return isoDate;
  const y = Number(parts[0]);
  const m = Number(parts[1]);
  const d = Number(parts[2]);
  if (!y || !m || !d) return isoDate;
  return `${y}年${m}月${d}日 · 晚安`;
}
