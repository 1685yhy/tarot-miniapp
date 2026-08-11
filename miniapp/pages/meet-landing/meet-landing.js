// pages/meet-landing/meet-landing.js —— 星辰相遇落地页（SDD P1 · T2-5）
//
// 流程（设计 2.1 邀请版接收侧）：
//   好友扫邀请码（scene=m:{meet_id}）→ 本页
//     → GET /meet/public/{meet_id} 脱敏公开信息（昵称/星座/星阶/状态，无需登录）
//     → status=pending：展示「XX 邀请你进行星辰相遇」+ 好友选星座/出生
//       → 未登录先微信登录（auth.checkLogin）→ POST /meet/join
//       → 成功跳结果页（/pages/meet/meet?meet_id=，双端可见）；奖励发放 toast
//     → status=completed：优雅提示「这场相遇已完成」+ 去看看结果
//     → 404/接口错误：优雅错误态（可重试）
//
// 合规：展示字段全部来自后端脱敏接口（无出生信息/无 invite_code/无联系方式）；
// 底部固定免责「仅供娱乐 · 星光映照」。文案前端零自造结果（join 结果全来自后端）。
// 约定：WXML 不用 .length > 0 表达式（T1-5 教训），所有布尔一律 JS 预计算。

const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { ZODIACS, ZODIAC_BY_KEY } = require('../../utils/energy');
const analytics = require('../../utils/analytics');

// 星座 12 宫格：符号 + 元素（四组软底色，E3 奶油系 —— 与 meet 页同款）
const ELEMENT_OF = {
  fire: ['aries', 'leo', 'sagittarius'],
  earth: ['taurus', 'virgo', 'capricorn'],
  air: ['gemini', 'libra', 'aquarius'],
  water: ['cancer', 'scorpio', 'pisces'],
};
const ZODIAC_ELEMENT = {};
Object.keys(ELEMENT_OF).forEach((el) => {
  ELEMENT_OF[el].forEach((key) => { ZODIAC_ELEMENT[key] = el; });
});

const ELEMENT_BG = {
  fire: 'rgba(232, 196, 190, 0.35)',  // 雾粉 · 火
  earth: 'rgba(201, 169, 124, 0.22)', // 细金 · 土
  air: 'rgba(216, 210, 228, 0.40)',   // 淡紫 · 风
  water: 'rgba(175, 194, 209, 0.35)', // 薄蓝 · 水
};

/** 'YYYY-MM-DD' → '8.12'（非法回退 ''） */
function fmtShort(dateStr) {
  const p = String(dateStr || '').split('-');
  if (p.length !== 3 || !p.every((s) => /^\d{1,4}$/.test(s))) return '';
  return `${Number(p[1])}.${Number(p[2])}`;
}

Page({
  _meetId: '',   // scene 解析出的 meet_id
  _reqSeq: 0,    // 请求序号守卫（防静默刷新竞态）
  _loadingLogin: false,

  data: {
    // 屏幕状态：loading（拉公开信息）| invite（pending 可加入）| done（已完成）
    // | error（404/接口错误）
    step: 'loading',
    errorMsg: '',

    // 公开信息（脱敏，来自 GET /meet/public/{meet_id}）
    info: null,          // { nickname, zodiac_cn, star_tier_name }
    hasInfo: false,
    meetId: '',

    // 登录态（未登录 → 先登录再接受相遇）
    loggedIn: false,

    // 好友出生信息表单（b 侧，与 meet 页同款：星座必选，出生可选）
    zodiacs: ZODIACS.map((z) => ({
      ...z,
      element: ZODIAC_ELEMENT[z.key] || '',
      elementBg: ELEMENT_BG[ZODIAC_ELEMENT[z.key]] || '',
      selected: false,
    })),
    zodiacKey: '',
    hasZodiac: false,
    birthDate: '',
    birthDateText: '',
    birthDateLabel: '出生日期（可选）',
    birthTime: '',
    birthTimeLabel: '出生时间（可选）',
    hasBirth: false,
    maxBirthYear: String(new Date().getFullYear()),

    submitting: false,
    submitLabel: '接受相遇 ✦',
  },

  onLoad(options) {
    const meetId = this._parseMeetId(options);
    if (!meetId) {
      this.setData({ step: 'error', errorMsg: '相遇链接不完整，请重新扫描邀请码' });
      return;
    }
    this._meetId = meetId;
    this.setData({ meetId });
    this._loadPublic(meetId);
  },

  /** scene=m:{meet_id} 解码（兼容分享卡片直带 meet_id / 未编码 scene） */
  _parseMeetId(options) {
    let rawScene = '';
    try {
      rawScene = (options && options.scene) ? decodeURIComponent(options.scene) : '';
    } catch (e) {
      rawScene = String((options && options.scene) || '');
    }
    const s = rawScene.trim();
    if (s.indexOf('m:') === 0) {
      return s.slice(2).trim();
    }
    // 分享卡片直带：?meet_id=xxx
    if (options && options.meet_id) {
      return String(options.meet_id).trim();
    }
    return '';
  },

  /** GET /meet/public/{meet_id}：脱敏公开信息 + 状态裁决 */
  _loadPublic(meetId) {
    const seq = ++this._reqSeq;
    this.setData({ step: 'loading', errorMsg: '', loggedIn: !!wx.getStorageSync('token') });
    request(`/meet/public/${meetId}`)
      .then((res) => {
        if (seq !== this._reqSeq) return;
        if (!res || res.meet_id !== meetId || !res.nickname) {
          this.setData({ step: 'error', errorMsg: '相遇信息不完整，请稍后重试' });
          return;
        }
        analytics.funnel('meet_landing_visit', { meet_id: meetId });
        const status = res.status || '';
        const info = {
          nickname: res.nickname,
          zodiacCn: res.zodiac_cn || '',
          hasZodiac: !!res.zodiac_cn,
          starTierName: res.star_tier_name || '',
          hasTier: !!res.star_tier_name,
        };
        if (status === 'pending') {
          // 邀请中：展示加入表单（等待接受）
          this.setData({ step: 'invite', info, hasInfo: true });
        } else {
          // 已完成（含快速版直接落库）：优雅提示，可去看看结果
          this.setData({ step: 'done', info, hasInfo: true });
        }
      })
      .catch((err) => {
        if (seq !== this._reqSeq) return;
        const msg = getFriendlyError(err) || '相遇信息加载失败';
        this.setData({
          step: 'error',
          errorMsg: err && err.statusCode === 404 ? '这场相遇不存在或已失效' : msg,
        });
      });
  },

  onRetry() {
    if (this._meetId) this._loadPublic(this._meetId);
  },

  /* ── 登录引导（未登录 → 微信登录后展示接受表单） ── */

  async onLogin() {
    if (this._loadingLogin) return;
    this._loadingLogin = true;
    wx.showLoading({ title: '微信登录中...', mask: true });
    try {
      await checkLogin();
      this.setData({ loggedIn: true });
      analytics.trackEvent('meet_landing_login', { meet_id: this._meetId });
    } catch (err) {
      wx.showToast({ title: getFriendlyError(err) || '登录失败，请重试', icon: 'none' });
    } finally {
      this._loadingLogin = false;
      wx.hideLoading();
    }
  },

  /* ── 好友出生信息表单（b 侧；时间需配合日期，后端口径） ── */

  onZodiacTap(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    const zodiacs = this.data.zodiacs.map((z) => ({ ...z, selected: z.key === key }));
    this.setData({ zodiacs, zodiacKey: key, hasZodiac: true });
    analytics.trackEvent('meet_landing_zodiac_tap', { zodiac: key });
  },

  onDateChange(e) {
    const birthDate = e.detail.value || '';
    this.setData({
      birthDate,
      birthDateText: fmtShort(birthDate),
      birthDateLabel: fmtShort(birthDate) || '出生日期（可选）',
      hasBirth: !!(birthDate || this.data.birthTime),
    });
  },

  onTimeChange(e) {
    if (!this.data.birthDate) {
      wx.showToast({ title: '请先选择出生日期', icon: 'none' });
      return;
    }
    const birthTime = e.detail.value || '';
    this.setData({
      birthTime,
      birthTimeLabel: birthTime || '出生时间（可选）',
      hasBirth: true,
    });
  },

  onClearBirth() {
    this.setData({
      birthDate: '', birthDateText: '', birthDateLabel: '出生日期（可选）',
      birthTime: '', birthTimeLabel: '出生时间（可选）', hasBirth: false,
    });
  },

  /* ── 接受相遇：登录（如需）→ POST /meet/join → 结果页 ── */

  async onAccept() {
    if (this.data.submitting) return;
    if (!this.data.hasZodiac) {
      wx.showToast({ title: '先选一个星座 ✦', icon: 'none' });
      return;
    }
    // 未登录 → 先微信登录（登录成功继续接受；登录失败停在原页）
    if (!wx.getStorageSync('token')) {
      await this.onLogin();
      if (!wx.getStorageSync('token')) return;
    }

    const seq = ++this._reqSeq;
    this.setData({ submitting: true, submitLabel: '星空中…', errorMsg: '' });

    const payload = { meet_id: this._meetId, zodiac_b: this.data.zodiacKey };
    if (this.data.birthDate) payload.b_birth_date = this.data.birthDate;
    // 出生时间需配合出生日期（后端口径）：只有时间没日期 → 不发送，避免 400
    if (this.data.birthDate && this.data.birthTime) payload.b_birth_time = this.data.birthTime;

    try {
      const res = await request('/meet/join', { method: 'POST', data: payload });
      if (seq !== this._reqSeq) return;
      analytics.trackEvent('meet_join', {
        meet_id: this._meetId,
        zodiac_b: payload.zodiac_b,
        with_birth: !!payload.b_birth_date,
        score: res && res.score,
        rewarded: !!(res && res.reward_granted),
      });
      const rewardNote = res && res.reward_granted ? ' · 相遇奖励已发放 ✦' : '';
      wx.showToast({ title: `相遇达成${rewardNote}`, icon: 'none', duration: 1800 });
      // 跳结果页（redirectTo：落地页不再保留返回栈，防重复加入）
      setTimeout(() => {
        wx.redirectTo({ url: `/pages/meet/meet?meet_id=${this._meetId}` });
      }, 900);
    } catch (err) {
      if (seq !== this._reqSeq) return;
      this.setData({ submitting: false, submitLabel: '接受相遇 ✦' });
      if (err && err.statusCode === 400) {
        // 已完成/重复加入/自己的相遇 → 弹层说明；若是发起人自己可回发起页
        wx.showModal({
          title: '暂时无法加入',
          content: err.message || '这场相遇未在邀请中或已完成',
          confirmText: '知道了',
          showCancel: false,
        });
      } else {
        wx.showToast({ title: getFriendlyError(err) || '接受失败，请重试', icon: 'none' });
      }
    }
  },

  /** 已完成态：去看看结果（双端均有访问权；无权限时 meet 页自身优雅降级） */
  onViewResult() {
    wx.redirectTo({ url: `/pages/meet/meet?meet_id=${this._meetId}` });
  },

  /** 去发起自己的相遇（回发起侧主入口） */
  onGoCreate() {
    wx.navigateTo({ url: '/pages/meet/meet' });
  },

  /* ── 分享（落地页转发：同一 meet_id 邀请码，转发即拉新） ── */

  onShareAppMessage() {
    const info = this.data.info;
    analytics.trackEvent('meet_landing_share', { meet_id: this._meetId || '' });
    return {
      title: info
        ? `${info.nickname} 邀请你进行星辰相遇 ✦`
        : '有人邀请你进行星辰相遇 ✦ 星光映照',
      path: this._meetId
        ? `/pages/meet-landing/meet-landing?scene=${encodeURIComponent('m:' + this._meetId)}`
        : '/pages/index/index',
    };
  },

  onShareTimeline() {
    return {
      title: '有人邀请你进行星辰相遇 ✦ 星光映照',
      query: this._meetId ? `scene=${encodeURIComponent('m:' + this._meetId)}` : '',
    };
  },
});
