// pages/card-landing/card-landing.js
// 星光名片落地页 —— 好友扫小程序码后进入：展示名片卡面 + 星阶 + 星光数
// scene 参数由 getwxacodeunlimit 带入（微信会 encodeURIComponent，需解码）
const { request, getFriendlyError } = require('../../utils/api');
const analytics = require('../../utils/analytics');

Page({
  data: {
    loading: true,
    error: '',
    card: null, // { nickname, starTierName, stardustTotal, inviteCode }
  },

  async onLoad(options) {
    let rawScene = '';
    try {
      // 手工拼接/畸形 scene（如未编码的 %xx）会让 decodeURIComponent 抛
      // URIError —— 捕获后走错误态，避免页面卡在 loading。
      rawScene = (options && options.scene) ? decodeURIComponent(options.scene) : '';
    } catch (e) {
      this.setData({ loading: false, error: '名片链接不完整' });
      return;
    }
    const code = this._parseCode(rawScene);

    if (!code) {
      this.setData({ loading: false, error: '名片链接不完整' });
      return;
    }

    analytics.funnel('card_landing_visit', { invite_code: code.slice(0, 5) });

    try {
      const data = await request('/share/card-info?code=' + encodeURIComponent(code));
      this.setData({
        loading: false,
        card: {
          nickname: data.nickname,
          starTierName: data.star_tier_name,
          stardustTotal: data.stardust_total,
          inviteCode: data.invite_code,
        },
      });
    } catch (err) {
      this.setData({ loading: false, error: getFriendlyError(err) || '名片加载失败' });
    }
  },

  /** scene 可能为裸邀请码（新）或 invite_code=STAR-XXXX（旧版邀请海报） */
  _parseCode(rawScene) {
    const s = (rawScene || '').trim();
    if (!s) return '';
    if (s.indexOf('invite_code=') === 0) {
      return s.slice('invite_code='.length).trim();
    }
    return s;
  },

  /** 加入星光映照：去首页（未登录用户由首页引导登录） */
  onGoApp() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onShareAppMessage() {
    const card = this.data.card;
    return {
      title: card ? `${card.nickname} 的星光名片 ✦ 加入星光映照` : '星光映照 · 塔罗占卜',
      path: '/pages/index/index',
    };
  },
});
