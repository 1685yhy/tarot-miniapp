// pages/share-center/share-center.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');
const analytics = require('../../utils/analytics');

// Same zodiac list as onboarding (pages/index/index.js zodiacList)
const ZODIAC_LIST = [
  { key: 'aries', name: '白羊座', emoji: '♈' },
  { key: 'taurus', name: '金牛座', emoji: '♉' },
  { key: 'gemini', name: '双子座', emoji: '♊' },
  { key: 'cancer', name: '巨蟹座', emoji: '♋' },
  { key: 'leo', name: '狮子座', emoji: '♌' },
  { key: 'virgo', name: '处女座', emoji: '♍' },
  { key: 'libra', name: '天秤座', emoji: '♎' },
  { key: 'scorpio', name: '天蝎座', emoji: '♏' },
  { key: 'sagittarius', name: '射手座', emoji: '♐' },
  { key: 'capricorn', name: '摩羯座', emoji: '♑' },
  { key: 'aquarius', name: '水瓶座', emoji: '♒' },
  { key: 'pisces', name: '双鱼座', emoji: '♓' },
];

Page({
  data: {
    pageLoading: true,
    pageError: null,
    inviteCode: '',
    copied: false,
    stats: {},
    shareHistory: [],
    rewardProgressPercent: 0,

    // Zodiac match (fun sharing — "你们的塔罗关系牌")
    zodiacList: ZODIAC_LIST,
    sign1Key: 'aries',
    sign1Name: '白羊座',
    sign1Emoji: '♈',
    sign2Key: 'taurus',
    sign2Name: '金牛座',
    sign2Emoji: '♉',
    pickerFor: '', // '' | 'sign1' | 'sign2' — which picker grid is open
    matchLoading: false,
    matchResult: null,
    showMatchPoster: false,
    matchCardImage: '',
    matchCardName: '',
    matchCompatText: '',
    matchSignsText: '',
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
      // Analytics: invite share
      analytics.trackShare('wechat_friend', 'invite');
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

  /* ---------------------------------------------------------------
     Zodiac match — "星座契合 · 塔罗关系牌" (fun, light, no rewards)
     --------------------------------------------------------------- */

  onSelectSign1() {
    this.setData({ pickerFor: 'sign1' });
  },

  onSelectSign2() {
    this.setData({ pickerFor: 'sign2' });
  },

  onPickSign(e) {
    const key = e.currentTarget.dataset && e.currentTarget.dataset.key;
    const which = this.data.pickerFor;
    if (!which || !key) return;

    const sign = this.data.zodiacList.find(s => s.key === key);
    if (!sign) return;

    const patch = { pickerFor: '' };
    patch[`${which}Key`] = sign.key;
    patch[`${which}Name`] = sign.name;
    patch[`${which}Emoji`] = sign.emoji;
    this.setData(patch);
  },

  onClosePicker() {
    this.setData({ pickerFor: '' });
  },

  noop() {},

  /** Fetch the relationship tarot card for the two selected signs */
  async onCheckMatch() {
    const { sign1Key, sign2Key, matchLoading } = this.data;
    if (matchLoading) return;
    if (!sign1Key || !sign2Key) {
      wx.showToast({ title: '请先选择两个星座', icon: 'none' });
      return;
    }

    this.setData({ matchLoading: true });
    try {
      const result = await request(`/share/zodiac-match?sign1=${sign1Key}&sign2=${sign2Key}`);

      // Compute the card image path from the card metadata the API returns
      const cardImage = computeImagePath({
        name_en: result.name_en || '',
        arcana: result.arcana,
        card_number: result.card_number,
        suit: result.suit,
      }) || '';

      this.setData({
        matchResult: result,
        matchLoading: false,
        matchCardImage: cardImage,
        matchCardName: result.card_name || '',
        matchCompatText: result.compatibility_text || '',
        matchSignsText: `${this.data.sign1Emoji} + ${this.data.sign2Emoji}`,
      });
    } catch (err) {
      this.setData({ matchLoading: false });
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  /** Open the zodiac match poster modal */
  onShowMatchPoster() {
    if (!this.data.matchResult) return;
    this.setData({ showMatchPoster: true });
  },

  onCloseMatchPoster() {
    this.setData({ showMatchPoster: false });
  },

  /** Share the zodiac poster to a friend (voluntary — no rewards attached) */
  onShareMatchPoster(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;

    const shareText = (this.data.matchResult && this.data.matchResult.share_text)
      || '看看你和谁的星座最契合 ✦';

    // Analytics: zodiac match poster share
    analytics.trackShare('wechat_friend', 'zodiac_match_poster');
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: shareText,
      });
    } catch (_err) {
      // Fallback: guide the user to save first
      wx.showToast({
        title: '请先保存海报，再从相册分享',
        icon: 'none',
        duration: 2000,
      });
    }
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
