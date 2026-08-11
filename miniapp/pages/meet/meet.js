// pages/meet/meet.js —— 星辰相遇（SDD P1 · T2-4 前端）
//
// 流程（设计 2.1 快速版 + 邀请版发起侧）：
//   输入（关系 4 星光徽章 + 对方星座 12 宫格 + 可选出生日期/时间）
//     → POST /meet/quick 快速合盘（落库返回完整结果）
//     → 结果三屏（双星徽章 → 共鸣度大圆环 → 三要素分解卡 → 三牌横排
//        → 相处提示卡 → 固定免责尾行）
//     → 邀请 ta 相遇（POST /meet/invite → 小程序码 PNG → 预览/保存相册）
//     → 好友扫码落 meet-landing（T2-5 建页，本任务只做发起侧）
// 直链：onLoad 带 meet_id 参数（分享/我的相遇）→ GET /meet/{meet_id} 直接渲染结果
// 我的相遇：GET /meet/list 输入屏底部轻列表，点项回看（快速版也落库）
//
// 合规：相处提示/牌意全部直接来自后端（MEET_TIPS 池 + meaning_upright 截取），
//   前端零自造文案；结果页固定免责尾行「星辰只描述你们如何相处，不定义任何
//   结局 · 仅供娱乐」；分享文案用后端同款「我和 TA 的星辰共鸣度是 N · 看看
//   你和谁星光相映 ✦」。
// 约定：WXML 不用 .length > 0 表达式（T1-5 教训），所有布尔一律 JS 预计算。

const { request, getFriendlyError, BASE_URL } = require('../../utils/api');
const { ZODIACS, ZODIAC_BY_KEY } = require('../../utils/energy');
const { findCard, computeImagePath } = require('../../utils/cards');
const analytics = require('../../utils/analytics');

// ── 关系选择：4 枚星光徽章（设计 2.2）──
const RELATIONS = [
  { key: 'friend', label: '友', name: '朋友', emoji: '🌿' },
  { key: 'love', label: '恋', name: '恋人', emoji: '✦' },
  { key: 'family', label: '亲', name: '家人', emoji: '☾' },
  { key: 'work', label: '事', name: '同事', emoji: '✧' },
];
const RELATION_BY_KEY = {};
RELATIONS.forEach((r) => { RELATION_BY_KEY[r.key] = r; });

// ── 星座 12 宫格：符号 + 元素（四组软底色，E3 奶油系）──
const ELEMENT_OF = {
  // 火：aries/leo/sagittarius
  fire: ['aries', 'leo', 'sagittarius'],
  // 土：taurus/virgo/capricorn
  earth: ['taurus', 'virgo', 'capricorn'],
  // 风：gemini/libra/aquarius
  air: ['gemini', 'libra', 'aquarius'],
  // 水：cancer/scorpio/pisces
  water: ['cancer', 'scorpio', 'pisces'],
};
const ZODIAC_ELEMENT = {};
Object.keys(ELEMENT_OF).forEach((el) => {
  ELEMENT_OF[el].forEach((key) => { ZODIAC_ELEMENT[key] = el; });
});

// 元素底色（雾粉/细金/淡紫/薄蓝 —— E3 奶油疗愈四系）
const ELEMENT_BG = {
  fire: 'rgba(232, 196, 190, 0.35)',  // 雾粉 · 火
  earth: 'rgba(201, 169, 124, 0.22)', // 细金 · 土
  air: 'rgba(216, 210, 228, 0.40)',   // 淡紫 · 风
  water: 'rgba(175, 194, 209, 0.35)', // 薄蓝 · 水
};

// 三要素角色名（factors[].role → 中文）
const ROLE_NAMES = { sun: '太阳', moon: '月亮', rising: '上升' };

// 免责尾行（结果页常驻，设计 2.3 合规要求）
// T5-1 合规统一：固定「仅供娱乐 · 星光映照」（设计五-5）
const DISCLAIMER = '星辰只描述你们如何相处，不定义任何结局 · 仅供娱乐 · 星光映照';

// 本地默认关系（未选择时提示用）
const DEFAULT_RELATION = 'friend';

/** 'YYYY-MM-DD' → '8.12'（非法回退 ''） */
function fmtShort(dateStr) {
  const p = String(dateStr || '').split('-');
  if (p.length !== 3 || !p.every((s) => /^\d{1,4}$/.test(s))) return '';
  return `${Number(p[1])}.${Number(p[2])}`;
}

/** 星座 key → 展示对象（key 非法回退 null） */
function zodiacOf(key) {
  return ZODIAC_BY_KEY[key] || null;
}

/** 牌名 → 卡牌图片 CDN 路径（registry 查不到 → ''，前端隐藏图占位） */
function cardImageOf(nameZh) {
  const reg = findCard(nameZh);
  return reg ? computeImagePath(reg) : '';
}

/** ArrayBuffer → UTF-8 字符串（invite 错误响应 JSON 解码用） */
function bufferToUtf8(buf) {
  try {
    const bytes = new Uint8Array(buf);
    let out = '';
    for (let i = 0; i < bytes.length; i += 8192) {
      out += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    }
    return decodeURIComponent(escape(out));
  } catch (e) {
    return '';
  }
}

Page({
  _meetId: '',       // 当前结果 meet_id（直链带入或 quick 返回）
  _reqSeq: 0,        // 请求序号守卫（防静默刷新竞态）
  _qrPath: '',       // 邀请码临时文件路径
  _lastOp: '',       // 最近一次结果来源：quick | detail（决定错误态重试目标）

  data: {
    // 屏幕状态：form（输入）| loading（合盘中）| result（结果）| error（接口错误）
    step: 'form',
    errorMsg: '',

    // 输入表单
    relations: RELATIONS.map((r) => ({ ...r, selected: r.key === DEFAULT_RELATION })),
    relationKey: DEFAULT_RELATION,
    zodiacs: ZODIACS.map((z) => ({ ...z, element: ZODIAC_ELEMENT[z.key] || '', elementBg: ELEMENT_BG[ZODIAC_ELEMENT[z.key]] || '', selected: false })),
    zodiacKey: '',          // 已选对方星座 key
    hasZodiac: false,       // JS 预计算（WXML 不用三元短路）
    birthDate: '',          // YYYY-MM-DD
    birthDateText: '',      // '8.12' 展示
    birthDateLabel: '出生日期', // WXML 文本预计算（不写 || 表达式）
    birthTime: '',          // HH:mm
    birthTimeLabel: '出生时间',
    hasBirth: false,        // 日期或时间任一已填（JS 预计算）
    submitting: false,
    submitLabel: '开始合盘 ✦',
    maxBirthYear: String(new Date().getFullYear()),

    // 我的相遇（输入屏底部轻列表，GET /meet/list）
    meets: [],
    hasMeets: false,
    meetsLoading: false,

    // 结果页
    res: null,              // 归一化结果 {a, b, score, levelName, factors, cards, tips, estimated, estimateNote, disclaimer}
    hasResult: false,
    hasFactors: false,
    expandedFactors: false, // 三要素卡「为什么」展开
    whyLabel: '为什么',     // 展开/收起按钮文案（预计算）
    hasCards: false,
    hasTips: false,
    estimated: false,       // estimated=true 空态标注「按太阳星座估算」
    inviting: false,        // 邀请码拉取中
    inviteLabel: '邀请 TA 相遇 ✦',
    inviteVisible: false,   // 邀请码弹层
    inviteQrPath: '',
    inviteSaving: false,
    saveLabel: '保存到相册',

    // 合盘海报（T2-5：GET /meet/{meet_id}/poster → share-poster mode="meet"）
    posterLoading: false,
    posterLabel: '合盘海报',
    posterData: null,       // 海报数据（脱敏）
    showPoster: false,      // 海报预览弹层
  },

  onLoad(options) {
    const meetId = options && options.meet_id;
    if (meetId) {
      // 分享/我的相遇直链：直接加载结果
      this._meetId = meetId;
      this._loadMeet(meetId);
    } else {
      this._loadList();
    }
  },

  /** 弹层蒙层点击穿透占位（catchtap 防冒泡） */
  noop() {},

  /* ── 输入表单交互 ── */

  onRelationTap(e) {
    const key = e.currentTarget.dataset.key;
    if (!key || key === this.data.relationKey) return;
    const relations = this.data.relations.map((r) => ({ ...r, selected: r.key === key }));
    this.setData({ relations, relationKey: key });
  },

  onZodiacTap(e) {
    const key = e.currentTarget.dataset.key;
    if (!key) return;
    const zodiacs = this.data.zodiacs.map((z) => ({ ...z, selected: z.key === key }));
    this.setData({ zodiacs, zodiacKey: key, hasZodiac: true });
    analytics.trackEvent('meet_zodiac_tap', { zodiac: key });
  },

  onDateChange(e) {
    const birthDate = e.detail.value || '';
    this.setData({
      birthDate,
      birthDateText: fmtShort(birthDate),
      birthDateLabel: fmtShort(birthDate) || '出生日期',
      hasBirth: !!(birthDate || this.data.birthTime),
    });
  },

  onTimeChange(e) {
    // 出生时间需配合出生日期（后端口径）：日期未选 → 提示并忽略，避免静默丢弃
    if (!this.data.birthDate) {
      wx.showToast({ title: '请先选择出生日期', icon: 'none' });
      return;
    }
    const birthTime = e.detail.value || '';
    this.setData({
      birthTime,
      birthTimeLabel: birthTime || '出生时间',
      hasBirth: true,
    });
  },

  onClearBirth() {
    this.setData({
      birthDate: '', birthDateText: '', birthDateLabel: '出生日期',
      birthTime: '', birthTimeLabel: '出生时间', hasBirth: false,
    });
  },

  /* ── 开始合盘：POST /meet/quick ── */

  onStart() {
    if (this.data.submitting) return;
    if (!this.data.hasZodiac) {
      wx.showToast({ title: '先选一个星座 ✦', icon: 'none' });
      return;
    }
    const seq = ++this._reqSeq;
    this._lastOp = 'quick'; // 错误态重试目标：本次是 quick（重试回表单，不重载旧详情）
    this.setData({ step: 'loading', submitting: true, submitLabel: '星空中…', errorMsg: '' });

    const payload = {
      relation: this.data.relationKey,
      zodiac_b: this.data.zodiacKey,
    };
    if (this.data.birthDate) payload.b_birth_date = this.data.birthDate;
    // 出生时间需配合出生日期（后端口径）：只有时间没日期 → 不发送，避免 400
    if (this.data.birthDate && this.data.birthTime) payload.b_birth_time = this.data.birthTime;

    request('/meet/quick', { method: 'POST', data: payload })
      .then((res) => {
        if (seq !== this._reqSeq) return; // 已被新请求覆盖
        this._meetId = res.meet_id || '';
        this._showResult(res);
        analytics.trackEvent('meet_quick', {
          relation: payload.relation,
          zodiac_b: payload.zodiac_b,
          with_birth: !!payload.b_birth_date,
          score: res && res.score,
        });
        // 有新相遇 → 刷新我的相遇列表（静默，失败不影响）
        this._loadList(true);
      })
      .catch((err) => {
        if (seq !== this._reqSeq) return;
        this.setData({
          step: 'error',
          errorMsg: getFriendlyError(err),
          submitting: false,
          submitLabel: '开始合盘 ✦',
        });
      });
  },

  /* ── 结果渲染（quick / 详情共用归一化）── */

  _showResult(raw) {
    if (!raw || !raw.a || !raw.b) {
      this.setData({ step: 'error', errorMsg: '结果数据异常，请稍后重试', submitting: false, submitLabel: '开始合盘 ✦' });
      return;
    }
    const score = typeof raw.score === 'number' ? raw.score : null;

    // 三要素分解（role 中文名 + 相容度条宽度；barWidth 预计算避免 WXML 内联换算）
    const factors = Array.isArray(raw.factors)
      ? raw.factors
          .filter((f) => f && ROLE_NAMES[f.role])
          .map((f) => ({
            role: f.role,
            roleName: ROLE_NAMES[f.role],
            score: Math.max(0, Math.min(100, Number(f.score) || 0)),
            barWidth: `${Math.max(4, Math.min(100, Number(f.score) || 0))}%`,
            reason: f.reason || '',
          }))
      : [];

    // 三牌：牌图 CDN 路径 + 名称 + 一句（tip/meaning_snippet 来自后端，前端零自造）
    const cards = Array.isArray(raw.cards)
      ? raw.cards
          .filter((c) => c && c.name_zh)
          .map((c) => {
            const image = cardImageOf(c.name_zh);
            return {
              position: c.position || '',
              name_zh: c.name_zh,
              snippet: c.tip || c.meaning_snippet || '',
              image,
              hasImage: !!image,
              // 可见性预计算（WXML 不写 && / || 复合布尔）
              cardVisible: !!image,
              cardFallback: !image,
            };
          })
      : [];

    // 相处提示（直接来自后端 MEET_TIPS 池）
    const tips = Array.isArray(raw.tips) ? raw.tips.filter((t) => typeof t === 'string' && t) : [];

    const estimated = !!raw.estimated;
    const estimateNote = estimated
      ? (raw.estimate_note || '月亮落座未知，共鸣度按太阳星座估算')
      : '';

    // 双星徽章（a=我 / b=对方）
    const a = this._sideOf(raw.a);
    const b = this._sideOf(raw.b);

    this.setData({
      step: 'result',
      submitting: false,
      submitLabel: '开始合盘 ✦',
      res: {
        a,
        b,
        score,
        scoreText: score == null ? '--' : String(score),
        levelName: raw.level_name || '',
        factors,
        cards,
        tips,
        estimated,
        estimateNote,
        disclaimer: DISCLAIMER,
      },
      hasResult: true,
      hasFactors: factors.length > 0,
      hasCards: cards.length > 0,
      hasTips: tips.length > 0,
      estimated,
      expandedFactors: false,
      whyLabel: '为什么',
    });
  },

  /** 一侧徽章：zodiac 展示对象（含三要素小字，缺要素不展示） */
  _sideOf(side) {
    const z = zodiacOf(side && side.zodiac);
    return {
      name: (side && side.name_zh) || (z && z.name) || '',
      emoji: (z && z.emoji) || '✦',
      zodiac: (side && side.zodiac) || '',
      elementBg: ELEMENT_BG[ZODIAC_ELEMENT[(side && side.zodiac) || '']] || '',
      // 三要素摘要：太阳必有；月亮/上升缺 → null（结果页标注估算）
      sunName: side && side.sun && side.sun.name_zh ? side.sun.name_zh : '',
      hasSun: !!(side && side.sun && side.sun.name_zh),
      moonName: side && side.moon && side.moon.name_zh ? side.moon.name_zh : '',
      hasMoon: !!(side && side.moon && side.moon.name_zh),
      risingName: side && side.rising && side.rising.name_zh ? side.rising.name_zh : '',
      hasRising: !!(side && side.rising && side.rising.name_zh),
    };
  },

  /* ── 我的相遇（GET /meet/list）── */

  _loadList(silent) {
    if (!silent) this.setData({ meetsLoading: true });
    request('/meet/list')
      .then((res) => {
        const items = Array.isArray(res && res.meetings) ? res.meetings : [];
        const meets = items
          .filter((m) => m && m.meet_id)
          .slice(0, 5)
          .map((m) => ({
            meet_id: m.meet_id,
            relation: m.relation || '',
            relationLabel: (RELATION_BY_KEY[m.relation] || {}).name || '',
            bName: m.b_name || '',
            score: typeof m.score === 'number' ? m.score : null,
            scoreText: typeof m.score === 'number' ? String(m.score) : '--',
            levelName: m.level_name || '',
            dateText: fmtShort(String(m.created_at || '').slice(0, 10)),
          }));
        this.setData({ meets, hasMeets: meets.length > 0, meetsLoading: false });
      })
      .catch(() => {
        // 静默降级：列表拉不到不阻塞主流程
        this.setData({ meets: [], hasMeets: false, meetsLoading: false });
      });
  },

  /** 点我的相遇项 → GET /meet/{meet_id} 回看结果 */
  onMeetItemTap(e) {
    const meetId = e.currentTarget.dataset.id;
    if (!meetId) return;
    this._meetId = meetId;
    this._loadMeet(meetId);
  },

  /** GET /meet/{meet_id} 详情（直链/回看共用；404 → 表单+提示；其余 → 错误屏可重试） */
  _loadMeet(meetId) {
    const seq = ++this._reqSeq;
    this._lastOp = 'detail'; // 错误态重试目标：本次是详情（重试重拉详情）
    this.setData({ step: 'loading', errorMsg: '' });
    request(`/meet/${meetId}`)
      .then((res) => {
        if (seq !== this._reqSeq) return;
        this._showResult(res);
      })
      .catch((err) => {
        if (seq !== this._reqSeq) return;
        if (err && err.statusCode === 404) {
          // 404/越权：直链分享给未加入的好友 → 优雅回落输入屏并提示
          this.setData({ step: 'form', errorMsg: '', submitting: false });
          wx.showToast({ title: '这场相遇还没开始，来发起一场吧 ✦', icon: 'none', duration: 2600 });
          this._loadList(true);
        } else {
          // 500/网络错误 → 错误屏（重新连接 = 重拉详情，与 quick 错误态同款）
          this.setData({ step: 'error', errorMsg: getFriendlyError(err), submitting: false });
        }
      });
  },

  /* ── 邀请 ta 相遇：POST /meet/invite → 小程序码 PNG ── */

  onInvite() {
    if (this.data.inviting || !this._meetId) return;
    const token = wx.getStorageSync('token');
    this.setData({ inviting: true, inviteLabel: '生成邀请码…' });

    wx.request({
      url: `${BASE_URL}/meet/invite`,
      method: 'POST',
      data: { meet_id: this._meetId },
      header: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : '',
      },
      responseType: 'arraybuffer',
      timeout: 15000,
      success: (res) => {
        if (res.statusCode === 401) {
          // 会话失效 → 与 api.js 统一口径：清 token 回登录（结果页 invite 兜底）
          this.setData({ inviting: false, inviteLabel: '邀请 TA 相遇 ✦' });
          wx.removeStorageSync('token');
          wx.reLaunch({ url: '/pages/index/index' });
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300 && res.data && res.data.byteLength > 0) {
          this._saveQrToFile(res.data);
          analytics.trackEvent('meet_invite', { meet_id: this._meetId });
        } else {
          // 错误响应为 JSON（如「好友已加入，无需再次邀请」）→ 解码后展示
          const msg = bufferToUtf8(res.data || '');
          let detail = '';
          try {
            detail = (JSON.parse(msg) || {}).detail || '';
          } catch (e) { /* 非 JSON 忽略 */ }
          this.setData({ inviting: false, inviteLabel: '邀请 TA 相遇 ✦' });
          wx.showToast({ title: detail || '邀请生成失败，请稍后重试', icon: 'none' });
        }
      },
      fail: () => {
        this.setData({ inviting: false, inviteLabel: '邀请 TA 相遇 ✦' });
        wx.showToast({ title: '网络连接异常，请稍后重试', icon: 'none' });
      },
    });
  },

  /** 小程序码 ArrayBuffer → 临时文件 → 弹层预览 */
  _saveQrToFile(buf) {
    const fs = wx.getFileSystemManager();
    const filePath = `${wx.env.USER_DATA_PATH}/meet-invite-${this._meetId}.png`;
    fs.writeFile({
      filePath,
      data: buf,
      encoding: 'binary',
      success: () => {
        this._qrPath = filePath;
        this.setData({ inviting: false, inviteLabel: '邀请 TA 相遇 ✦', inviteVisible: true, inviteQrPath: filePath });
      },
      fail: () => {
        this.setData({ inviting: false, inviteLabel: '邀请 TA 相遇 ✦' });
        wx.showToast({ title: '邀请码生成失败，请稍后重试', icon: 'none' });
      },
    });
  },

  /** 弹层保存邀请码到相册（分享给好友扫码） */
  onSaveInviteQr() {
    if (this.data.inviteSaving || !this._qrPath) return;
    this.setData({ inviteSaving: true, saveLabel: '保存中…' });
    wx.saveImageToPhotosAlbum({
      filePath: this._qrPath,
      success: () => {
        this.setData({ inviteSaving: false, saveLabel: '保存到相册' });
        wx.showToast({ title: '已保存，发给 TA 扫码相遇 ✦', icon: 'none' });
      },
      fail: (err) => {
        this.setData({ inviteSaving: false, saveLabel: '保存到相册' });
        if (err && err.errMsg && err.errMsg.indexOf('auth') >= 0) {
          // 未授权相册 → 引导设置；用户可长按弹层二维码保存
          wx.showModal({
            title: '需要相册权限',
            content: '保存邀请码需要相册权限，也可以在弹层里长按二维码保存',
            confirmText: '去设置',
            success: (r) => {
              if (r.confirm) wx.openSetting();
            },
          });
        } else {
          wx.showToast({ title: '保存失败，请长按二维码保存', icon: 'none' });
        }
      },
    });
  },

  onCloseInvite() {
    this.setData({ inviteVisible: false });
  },

  onPreviewInvite() {
    if (this._qrPath) {
      wx.previewImage({ urls: [this._qrPath], current: this._qrPath });
    }
  },

  /* ── 合盘海报（T2-5）：GET /meet/{meet_id}/poster → share-poster mode="meet" ── */

  onSharePoster() {
    if (this.data.posterLoading || !this._meetId) return;
    this.setData({ posterLoading: true, posterLabel: '海报生成中…' });
    wx.showLoading({ title: '生成合盘海报...', mask: true });

    request(`/meet/${this._meetId}/poster`)
      .then((res) => {
        if (!res || !res.meet_id) {
          throw Object.assign(new Error('海报数据异常'), { statusCode: 0 });
        }
        // 归一化：双人徽章 emoji 由 meet-poster.js 内部按 zodiac key 查 energy 表
        this.setData({
          posterData: {
            meet_id: res.meet_id,
            relation: res.relation || '',
            a: res.a || {},
            b: res.b || {},
            score: typeof res.score === 'number' ? res.score : null,
            level_name: res.level_name || '',
            cards: Array.isArray(res.cards) ? res.cards.filter((c) => c && c.name_zh) : [],
            share_text: res.share_text || '我和TA的星辰共鸣度 · 看看你和谁星光相映 ✦',
          },
          showPoster: true,
          posterLoading: false,
          posterLabel: '合盘海报',
        });
        wx.hideLoading();
        analytics.trackEvent('meet_poster', { meet_id: this._meetId, score: res.score });
      })
      .catch((err) => {
        this.setData({ posterLoading: false, posterLabel: '合盘海报' });
        wx.hideLoading();
        wx.showToast({ title: getFriendlyError(err) || '海报生成失败，请稍后重试', icon: 'none' });
      });
  },

  onClosePoster() {
    this.setData({ showPoster: false });
  },

  /** 海报「分享给朋友」：分享打点 + 分享奖励（fire-and-forget，与晚安卡/手账同款） */
  onShareMeetPosterToFriend(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'meet_poster');
    const poster = this.data.posterData || {};
    request('/share/track', {
      method: 'POST',
      data: { channel: 'wechat_friend', share_type: 'meet_poster', ref_id: this._meetId || '' },
    }).then((res) => {
      if (res && res.rewarded) {
        wx.showToast({ title: '分享成功！奖励已发放 ✦', icon: 'success', duration: 2000 });
      }
    }).catch(() => {});
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: poster.share_text || '我和TA的星辰共鸣度 · 看看你和谁星光相映 ✦',
      });
    } catch (err) {
      // 降级：先保存海报，再从相册分享
      wx.showToast({ title: '请先保存海报，再从相册分享', icon: 'none', duration: 2000 });
    }
  },

  /* ── 分享（结果页分享卡片；分享文案与后端 poster share_text 同款，单一来源）── */

  /** 分享标题（单点维护，防合规文案漂移） */
  _shareTitle() {
    const res = this.data.res;
    const score = res && res.score;
    return score == null
      ? '我和TA的星光相遇了 · 看看你和谁星光相映 ✦'
      : `我和 TA 的星辰共鸣度是 ${score} · 看看你和谁星光相映 ✦`;
  },

  onShareAppMessage() {
    const res = this.data.res;
    const score = res && res.score;
    analytics.trackEvent('meet_share', { meet_id: this._meetId || '', has_score: score != null });
    return {
      title: this._shareTitle(),
      path: this._meetId ? `/pages/meet/meet?meet_id=${this._meetId}` : '/pages/meet/meet',
    };
  },

  onShareTimeline() {
    return {
      title: this._shareTitle(),
      query: this._meetId ? `meet_id=${this._meetId}` : '',
    };
  },

  /* ── 结果页辅助 ── */

  /** 三牌图片加载失败 → 占位（星徽），不破版（可见性布尔随失败翻转） */
  onCardImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx == null) return;
    this.setData({
      [`res.cards[${idx}].imgError`]: true,
      [`res.cards[${idx}].cardVisible`]: false,
      [`res.cards[${idx}].cardFallback`]: true,
    });
  },

  /** 三要素分解卡「为什么」展开/收起 */
  onToggleFactors() {
    this.setData({
      expandedFactors: !this.data.expandedFactors,
      whyLabel: this.data.expandedFactors ? '为什么' : '收起',
    });
  },

  /** 重新计算：回输入屏（保留已选，方便调整） */
  onBackToForm() {
    this.setData({ step: 'form', errorMsg: '', submitting: false, submitLabel: '开始合盘 ✦' });
  },

  /** 错误态重试：按最近一次结果来源（quick=回表单；detail=重拉详情） */
  onRetry() {
    if (this._lastOp === 'detail' && this._meetId) {
      this._loadMeet(this._meetId);
    } else {
      this.setData({ step: 'form', errorMsg: '' });
    }
  },
});
