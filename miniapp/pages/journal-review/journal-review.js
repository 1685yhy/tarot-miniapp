// pages/journal-review/journal-review.js —— 月度星光复盘（T1-5）
//
// 入口：手账页月历顶部"本月星光回顾"卡（/pages/journal/journal →
//   /pages/journal-review/journal-review?month=YYYY-MM）
//
// 内容（设计 1.1 step 4）：
//   - AI 温柔总结开场（trend_summary：后端 AI/降级模板生成，前端只渲染）
//   - 亮暗星统计（点亮天数/亮星/暗星/亮暗比例）
//   - 情绪曲线（mood_series 星光亮度 → 块状曲线，与周回顾同口径）
//   - 本月星空色带（star_color_counts 色点串）
//   - 本月高频之牌（top_cards）+ 星光洞察（insight）+ 下月指引（next_guide）
//
// 交互：
//   - 重新复盘 → POST /journal/review/regenerate（覆盖当月缓存；非会员受
//     FREE_DIARY_AI_DAILY 配额，耗尽时 402 由接口兜底）
//   - 分享海报 → GET /journal/review/share-preview（脱敏：无昵称/无原文）+
//     /tasks/status 星阶徽章 → share-poster mode="journal" 绘制保存/分享；
//     分享时 POST /share/track（share_type="journal"）打点

const { request, getFriendlyError } = require('../../utils/api');
const analytics = require('../../utils/analytics');

// 星光亮度 → 块状曲线字符（与手账页周回顾 _computeMoodTrendCurve 同口径）
const BLOCK_MAP = ['▁', '▁', '▂', '▃', '▅', '▇'];
const MOOD_EMOJI_MAP = {
  happy: '😊', calm: '😌', excited: '🤩',
  anxious: '😰', sad: '😢', thoughtful: '🤔',
};

// 星阶阈值映射（与 backend app/services/stardust.py STAR_TIERS 一致）
const STAR_TIERS = [
  { threshold: 0, name: '微光' },
  { threshold: 7, name: '星光' },
  { threshold: 30, name: '星辉' },
  { threshold: 100, name: '星冠' },
];

function currentTierName(stardust) {
  let name = '微光';
  for (const t of STAR_TIERS) {
    if (stardust >= t.threshold) name = t.name;
  }
  return name;
}

/** '2026-08' → '八月' */
function monthLabelOf(monthStr) {
  const names = ['一月', '二月', '三月', '四月', '五月', '六月',
    '七月', '八月', '九月', '十月', '十一月', '十二月'];
  const m = Number((monthStr || '').split('-')[1]);
  return names[(m >= 1 && m <= 12 ? m : new Date().getMonth() + 1) - 1];
}

function pad(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

Page({
  data: {
    month: '',
    monthLabel: '',
    loading: true,
    error: null,
    review: null, // {stats, mood_series, star_color_counts, top_cards, trend_summary, insight, next_guide}
    curveText: '',
    starBand: [], // [{color, count, pct}]
    hasStarBand: false, // WXML 编译环境下 wx:if 不认 .length > 0，JS 预计算
    hasTopCards: false,
    brightRatioText: '',
    regenerating: false,
    sharing: false,

    // 匿名分享海报（脱敏数据 + 星阶徽章）
    posterData: null,
    showPoster: false,
    starTierName: '',
  },

  onLoad(options) {
    const now = new Date();
    const month = (options && options.month) || `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
    this.setData({ month, monthLabel: monthLabelOf(month) });
    this._loadTier(); // 静默：星阶徽章（海报用，失败不影响复盘页）
    this._loadReview();
  },

  // ============================================================
  // 数据
  // ============================================================

  /** 星阶徽章（/tasks/status；失败静默降级为空——海报省略徽章，不印错） */
  async _loadTier() {
    try {
      const status = await request('/tasks/status');
      this.setData({
        starTierName: (status && status.star_tier_name) || currentTierName((status && status.stardust_total) || 0),
      });
    } catch (err) {
      // 静默：海报无徽章仍可生成
    }
  },

  /** 拉取月度星光复盘（缓存命中即返回；未命中 AI 生成或降级模板） */
  async _loadReview() {
    this.setData({ loading: true, error: null });
    try {
      const review = await request(`/journal/review?month=${this.data.month}`);
      this._applyReview(review);
    } catch (err) {
      this.setData({ loading: false, error: getFriendlyError(err) });
    }
  },

  _applyReview(review) {
    const stats = (review && review.stats) || {};
    const series = (review && review.mood_series) || [];
    const starBand = this._computeStarBand((review && review.star_color_counts) || []);
    const topCards = (review && review.top_cards) || [];
    this.setData({
      review,
      loading: false,
      error: null,
      curveText: this._computeCurve(series),
      starBand,
      hasStarBand: starBand.length > 0,
      hasTopCards: topCards.length > 0,
      brightRatioText: `${Math.round((stats.bright_ratio || 0) * 100)}%`,
    });
    analytics.trackEvent('journal_review_view', { month: this.data.month });
  },

  /** mood_series 星光亮度 → 块状曲线（😔 ▁▂▃▅▇ 😊，与周回顾同口径） */
  _computeCurve(series) {
    if (!series || series.length === 0) return '';
    const blocks = series.map((p) => {
      const b = Math.round(p.brightness || 3);
      return BLOCK_MAP[Math.min(Math.max(b, 1), 5)];
    });
    return '😔 ' + blocks.join(' ') + ' 😊';
  },

  /** star_color_counts → 色带段（宽度按次数占比；pct 最小 3% 保证可见） */
  _computeStarBand(colorCounts) {
    const counts = (colorCounts || []).filter((c) => c && c.color);
    const total = counts.reduce((s, c) => s + (Number(c.count) || 0), 0) || 1;
    return counts.map((c) => ({
      color: c.color,
      count: Number(c.count) || 0,
      pct: Math.max((Number(c.count) || 0) / total * 100, 3),
    }));
  },

  onRetry() {
    this._loadReview();
  },

  /** 重新复盘（覆盖当月缓存；非会员配额 402 由后端兜底，展示友好文案） */
  async onRefreshReview() {
    if (this.data.regenerating) return;
    this.setData({ regenerating: true });
    wx.vibrateShort({ type: 'light' }).catch(() => {});
    try {
      const review = await request('/journal/review/regenerate', {
        method: 'POST',
        data: { month: this.data.month },
      });
      this._applyReview(review);
      wx.showToast({ title: '新的星光复盘已生成 ✦', icon: 'none', duration: 2000 });
    } catch (err) {
      wx.showToast({ title: getFriendlyError(err) || '生成失败，请重试', icon: 'none', duration: 2500 });
    } finally {
      this.setData({ regenerating: false });
    }
  },

  // ============================================================
  // 匿名分享海报
  // ============================================================

  /** 生成并预览月度星光手账海报（share-preview 仅返回脱敏字段） */
  async onSharePoster() {
    const review = this.data.review;
    if (!review || this.data.sharing) return;
    if ((review.stats && review.stats.days_recorded) === 0) {
      wx.showToast({ title: '先记几颗星，再分享你的夜空吧', icon: 'none', duration: 2000 });
      return;
    }
    this.setData({ sharing: true });
    wx.showLoading({ title: '生成分享图...', mask: true });
    try {
      const preview = await request(`/journal/review/share-preview?month=${this.data.month}`);
      this.setData({
        posterData: {
          monthLabel: this.data.monthLabel,
          stats: preview.stats || {},
          starColorCounts: preview.star_color_counts || [],
          summary: preview.summary || review.trend_summary || '',
          starTierName: this.data.starTierName,
        },
        showPoster: true,
      });
      wx.hideLoading();
      analytics.trackEvent('journal_review_poster', { month: this.data.month });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '生成失败，请重试', icon: 'none' });
    } finally {
      this.setData({ sharing: false });
    }
  },

  onClosePoster() {
    this.setData({ showPoster: false });
  },

  onShareJournalPosterToFriend(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'journal_poster');
    // 分享打点 + 奖励（fire-and-forget，与解读分享同模式）
    request('/share/track', {
      method: 'POST',
      data: { channel: 'wechat_friend', share_type: 'journal', ref_id: this.data.month },
    }).then((res) => {
      if (res && res.rewarded) {
        wx.showToast({ title: '分享成功！奖励已发放 ✦', icon: 'success', duration: 2000 });
      }
    }).catch(() => {});
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: `星光映照 · ${this.data.monthLabel} 我的星光夜空`,
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
  // 空月引导
  // ============================================================

  goBackToJournal() {
    wx.navigateBack({
      fail: () => wx.switchTab({ url: '/pages/index/index' }),
    });
  },

  onShareAppMessage() {
    return {
      title: `星光映照 · ${this.data.monthLabel} 我的星光夜空`,
      path: '/pages/index/index',
    };
  },
});
