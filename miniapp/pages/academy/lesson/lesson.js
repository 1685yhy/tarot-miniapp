// pages/academy/lesson/lesson.js —— 学习卡页（SDD P2 阶段3 · T6-5）
//
// 页面 = 一屏一张学习卡：
//   1. 牌面大图 + 左侧星光色描边（取牌元素色：大阿卡纳金/权杖火/圣杯水/宝剑风/星币土）
//   2. 四区块渐进展开：关键词（星光词）→ 符号解读 → 典故 → 生活关联
//   3. 底部「我已记住 ✦」→ POST /academy/learned → toast「这颗星，为你点亮 ✦」
//      + 星点转亮动效 + 里程碑弹层（milestone 响应）
//   4. 已学状态：已点亮角标 + 「复习一次 ✦」（POST /academy/review）
//   5. 「问小星」胶囊 → pages/academy/chat（T6-6 将建对话页，先链接不阻塞）
//   6. 「百科中查看」互链 → pages/card-detail（百科 ↔ 学堂两页互相跳转）
//
// 接口：GET /academy/lesson/{card_id}（公开免登录可看牌库，登录附带 my 进度）
//       POST /academy/learned · POST /academy/review
// 数据降级：lesson 404/网络异常 → 错误态可重试；牌图失败 → PNG 兜底 → 文字色块。

const { request, getFriendlyError } = require('../../../utils/api');
const { findCard, computeImagePath, pngFallbackPath } = require('../../../utils/cards');
const analytics = require('../../../utils/analytics');

// 牌面大图 base（lesson 接口 image_url 已是完整 URL，此为兜底路径）
const IMAGE_BASE_FALLBACK = 'https://xingxiang.chat/images/cards_full';

// 元素色（与学堂主页星图同语言：E3 奶油系派生）
const SUIT_COLOR = {
  major: '#C9A97C',     // 亮金 — 大阿卡纳
  wands: '#D9A36B',     // 暖杏 — 权杖·火
  cups: '#A3B8D6',      // 雾蓝 — 圣杯·水
  swords: '#B0A0CC',    // 灰紫 — 宝剑·风
  pentacles: '#A3C0A2', // 苔绿 — 星币·土
};

const SUIT_ZH = { wands: '火', cups: '水', swords: '风', pentacles: '土' };

// 四区块（渐进展开：首块默认展开，点击标题切换）
const BLOCKS = [
  { key: 'keywords', title: '关键词 · 星光词', open: true },
  { key: 'symbols', title: '符号解读', open: false },
  { key: 'story', title: '典故', open: false },
  { key: 'life', title: '生活关联', open: false },
];

Page({
  data: {
    pageLoading: true,
    pageError: null,
    cardId: null,
    isLoggedIn: false,

    card: null,       // {id, name_zh, arcana, suit, card_number, imageUrl, imgError}
    elementColor: '', // 星光色描边色
    elementName: '',  // 火/水/风/土（大阿卡纳空）
    teaching: null,   // {symbols, story, keywordsLearning, lifeConnection, elementAssociation}
    blocks: BLOCKS,

    learned: false,   // 已学状态
    reviewCount: 0,
    saving: false,    // learned 防连点
    litUp: false,     // 星点转亮动效触发

    // 里程碑弹层
    showMilestone: false,
    milestone: null,  // {key, title, stardust_gained, wallpaper_granted}
  },

  async onLoad(options) {
    this._destroyed = false;
    const cardId = Number(options.card_id);
    if (!cardId) {
      this.setData({ pageLoading: false, pageError: '缺少卡牌编号' });
      return;
    }
    const isLoggedIn = !!wx.getStorageSync('token');
    this.setData({ cardId, isLoggedIn });
    await this._loadLesson(cardId);
  },

  onUnload() {
    // 页面销毁守卫：异步回调/延时 setData 不再触发
    this._destroyed = true;
  },

  async _loadLesson(cardId) {
    try {
      const data = await request(`/academy/lesson/${cardId}`);
      if (this._destroyed) return;
      this._applyLesson(data || {});
      this.setData({ pageLoading: false, pageError: null });
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  /** lesson 响应 → 页面数据（元素色 + 图片兜底 + 四区块归一化） */
  _applyLesson(data) {
    const rawCard = data.card || {};
    const teaching = data.teaching || {};
    const my = data.my || null;

    const suit = rawCard.arcana === 'major' ? 'major' : (rawCard.suit || 'major');
    const elementColor = SUIT_COLOR[suit] || SUIT_COLOR.major;
    const elementName = SUIT_ZH[rawCard.suit] || '';

    // 图片：接口 image_url 优先；缺失时经 findCard 反查注册表算兜底路径
    let imageUrl = rawCard.image_url || '';
    if (!imageUrl) {
      const found = findCard(rawCard.name_zh);
      if (found) imageUrl = computeImagePath(found, IMAGE_BASE_FALLBACK);
    }

    this.setData({
      card: {
        id: rawCard.id,
        name_zh: rawCard.name_zh || '',
        arcana: rawCard.arcana || 'major',
        suit: rawCard.suit || '',
        card_number: rawCard.card_number,
        imageUrl,
        imgError: false,
      },
      elementColor,
      elementName,
      teaching: {
        symbols: teaching.symbols || [],
        story: teaching.story || '',
        keywordsLearning: teaching.keywords_learning || [],
        lifeConnection: teaching.life_connection || '',
        elementAssociation: teaching.element_association || '',
      },
      learned: !!(my && my.learned),
      reviewCount: (my && my.review_count) || 0,
    });
    if (rawCard.name_zh) {
      wx.setNavigationBarTitle({ title: `学习 · ${rawCard.name_zh}` });
    }
  },

  // ===================== 四区块渐进展开 =====================

  onBlockTap(e) {
    const key = e.currentTarget.dataset.key;
    const blocks = this.data.blocks.map((b) =>
      b.key === key ? Object.assign({}, b, { open: !b.open }) : b
    );
    this.setData({ blocks });
  },

  // ===================== 我已记住 ✦ =====================

  /** 「我已记住 ✦」→ POST /academy/learned → 点亮动效 + toast + 里程碑弹层 */
  async onRemember() {
    if (this.data.saving) return;
    if (!this.data.isLoggedIn) {
      this._promptLogin('登录后即可点亮这颗星 ✦');
      return;
    }
    if (!this.data.cardId) return;
    this.setData({ saving: true });
    try {
      const res = await request('/academy/learned', {
        method: 'POST',
        data: { card_id: this.data.cardId },
      });
      if (this._destroyed) return;
      analytics.trackEvent('academy_learned', { card_id: this.data.cardId });
      if (res.learned) {
        // 点亮动效：星点转亮（1.2s 后清除，只保留静态点亮态；页面销毁守卫）
        this.setData({ litUp: true });
        setTimeout(() => {
          if (!this._destroyed) this.setData({ litUp: false });
        }, 1400);
        wx.showToast({ title: '这颗星，为你点亮 ✦', icon: 'none' });
        if (res.milestone) {
          // T6-6 跨页去重：卡页里程碑弹层展示即落旗标（academy 主页同一
          // 里程碑的全屏庆祝据此跳过，避免同一成就双重庆祝）
          try { wx.setStorageSync('academy_celebrated_' + res.milestone.key, true); } catch (_e) {}
          this.setData({ milestone: res.milestone, showMilestone: true });
        }
      } else {
        // 幂等：已学过
        wx.showToast({ title: '这颗星早已为你点亮 ✦', icon: 'none' });
      }
      this.setData({ learned: true, saving: false });
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ saving: false });
      if (err.statusCode === 401) {
        this._promptLogin('登录已过期，请重新登录');
      } else {
        wx.showToast({ title: getFriendlyError(err), icon: 'none' });
      }
    }
  },

  /** 复习一次（已学态）→ POST /academy/review */
  async onReview() {
    if (this.data.saving || !this.data.cardId) return;
    this.setData({ saving: true });
    try {
      const res = await request('/academy/review', {
        method: 'POST',
        data: { card_id: this.data.cardId },
      });
      if (this._destroyed) return;
      analytics.trackEvent('academy_review', { card_id: this.data.cardId });
      this.setData({ reviewCount: res.review_count || this.data.reviewCount + 1, saving: false });
      wx.showToast({ title: '复习一次，星更亮 ✦', icon: 'none' });
    } catch (err) {
      if (this._destroyed) return; // 页面销毁守卫（与 onRemember 对齐）
      this.setData({ saving: false });
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  /** 里程碑弹层关闭 */
  onCloseMilestone() {
    this.setData({ showMilestone: false, milestone: null });
  },

  /** 里程碑弹层滚动穿透拦截（无操作） */
  noop() {},

  // ===================== 互链 =====================

  /** 问小星 → 陪学对话页（T6-6 将注册并构建 pages/academy/chat） */
  onAskXiaoXing() {
    if (!this.data.cardId) return;
    analytics.trackEvent('academy_ask_xiaoxing', { card_id: this.data.cardId });
    wx.navigateTo({ url: `/pages/academy/chat/chat?card_id=${this.data.cardId}` });
  },

  /** 百科互链：去百科详情卡 */
  onGoEncyclopedia() {
    if (!this.data.cardId) return;
    wx.navigateTo({ url: `/pages/card-detail/card-detail?id=${this.data.cardId}` });
  },

  // ===================== 牌图降级 =====================

  /** 牌图加载失败：WebP → PNG 兜底 → 文字色块 */
  onImgError() {
    const card = this.data.card;
    if (!card || card.imgError) return;
    if (card.imageUrl && card.imageUrl.endsWith('.webp')) {
      this.setData({ 'card.imageUrl': pngFallbackPath(card.imageUrl) });
      return;
    }
    this.setData({ 'card.imgError': true });
  },

  // ===================== 通用 =====================

  onRetry() {
    this.setData({ pageLoading: true, pageError: null });
    this._loadLesson(this.data.cardId);
  },

  _promptLogin(content) {
    wx.showModal({
      title: '需要登录',
      content: content || '登录后即可点亮你的星',
      confirmText: '去登录',
      cancelText: '先看看',
      success: (r) => {
        if (r.confirm) wx.reLaunch({ url: '/pages/index/index' });
      },
    });
  },

  onShareAppMessage() {
    const name = (this.data.card && this.data.card.name_zh) || '';
    return {
      title: name ? `我在星灵学堂学习了「${name}」✦` : '星灵学堂 · 点亮你的 78 颗星',
      path: this.data.cardId
        ? `/pages/academy/lesson/lesson?card_id=${this.data.cardId}`
        : '/pages/academy/academy',
    };
  },
});
