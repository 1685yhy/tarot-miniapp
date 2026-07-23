// pages/share-center/share-center.js
const { request, getFriendlyError } = require('../../utils/api');

Page({
  data: {
    pageLoading: true,
    pageError: null,
    inviteCode: '',
    copied: false,
    stats: {},
    shareHistory: [],
    rewardProgressPercent: 0,
  },

  async onLoad() {
    await this._loadAll();
    this._loaded = true;
  },

  async onShow() {
    // Refresh stats every time page becomes visible (skip the initial onShow that fires right after onLoad)
    if (this._loaded) {
      await this._loadAll();
    }
  },

  async _loadAll() {
    this.setData({ pageLoading: true, pageError: null });
    try {
      const [stats, codeResult] = await Promise.all([
        request('/share/stats?days=365'),
        request('/share/invite-code'),
      ]);

      const inviteCode = codeResult.invite_code || '';
      const shareCount = stats.share_count || 0;

      // Compute progress toward next tier
      const progressPercent = this._computeProgress(shareCount);

      this.setData({
        stats,
        inviteCode,
        rewardProgressPercent: progressPercent,
        pageLoading: false,
      });

      // Load share history
      await this._loadShareHistory();
    } catch (err) {
      this.setData({
        pageLoading: false,
        pageError: getFriendlyError(err),
      });
    }
  },

  async _loadShareHistory() {
    try {
      // Use share/stats which contains share history
      // For full list we re-use the stats endpoint
      const stats = this.data.stats;
      // Share history is derived from share count data
      // In a real app we'd have a dedicated history endpoint
    } catch (_err) {
      // Silent
    }
  },

  _computeProgress(shares) {
    // 0 shares = 0%, 30+ shares = 100%
    if (shares >= 30) return 100;
    if (shares >= 10) return 75;
    if (shares >= 3) return 50;
    if (shares >= 1) return 25;
    return 0;
  },

  nextTierRemaining(threshold) {
    const shares = this.data.stats.share_count || 0;
    const remaining = threshold - shares;
    return remaining > 0 ? remaining : 0;
  },

  async onCopyCode() {
    const code = this.data.inviteCode;
    if (!code) return;

    try {
      await wx.setClipboardData({ data: code });
      this.setData({ copied: true });
      wx.showToast({ title: '邀请码已复制', icon: 'success' });
      if (!this._timers) this._timers = [];
      this._timers.push(setTimeout(() => {
        this.setData({ copied: false });
      }, 2000));
    } catch (_err) {
      wx.showToast({ title: '复制失败', icon: 'none' });
    }
  },

  async onInviteFriend() {
    const code = this.data.inviteCode;
    if (!code) {
      wx.showToast({ title: '获取邀请码中...', icon: 'none' });
      return;
    }

    try {
      // Trigger WeChat share with the invite card
      wx.shareAppMessage({
        title: '来星光塔罗一起探索命运吧 ✦',
        imageUrl: '',
      });
    } catch (_err) {
      // Fallback to custom share
      wx.showToast({
        title: '分享失败，请重试',
        icon: 'none',
      });
    }
  },

  // Override WeChat share message
  onShareAppMessage() {
    const code = this.data.inviteCode || 'STAR-****';
    return {
      title: `邀你加入星光塔罗 ✦ 我的邀请码: ${code}`,
      path: `/pages/index/index?invite=${code}`,
      imageUrl: '/images/icons/star_64.png',
    };
  },

  onRetry() {
    this._loadAll();
  },

  onUnload() {
    this._clearTimers();
  },

  onHide() {
    this._clearTimers();
  },

  _clearTimers() {
    if (this._timers) {
      this._timers.forEach(t => clearTimeout(t));
      this._timers = [];
    }
  },

  onBack() {
    wx.navigateBack();
  },
});
