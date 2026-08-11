// pages/resonance/resonance.js —— 今日星光共鸣（星友圈 · T8-4）
//
// 页面 = 共鸣墙（零 UGC 结构化轻互动）：
//   1. 首次进入弹「星光公约」弹窗（wx.setStorageSync('resonance_pact_v1')）
//   2. 页头「今日共鸣墙」+ 今日活跃星光数
//   3. 我的今日卡片置顶（星名/星座/星光数/今日牌/星阶 + 今日收到共鸣数）
//   4. 三分组横滑（同星座 / 同星光数 / 同一张牌）+ 兜底组「同星光的星」
//   5. 点 ✦ 共鸣：星点飞出上浮消散动效 + 计数 +1（成功后实心星）
//      已共鸣卡片实心 + 点击 toast「已共鸣过这颗星 ✦」；超 10 次 400 原样展示
//   6. 我的共鸣统计（stats）+ 今日剩余次数提示
//   7. 隐身开关（默认开，一键关：确认弹窗 + 即时生效）
//   8. 共鸣海报分享（GET /resonance/poster → share-poster mode="resonance"）
//
// 接口：GET /resonance/wall（公开限流）· GET /resonance/alias（进页确保星名落库）
//       GET /resonance/stats · POST /resonance/give · POST /resonance/visibility
//       GET /resonance/poster
// 数据降级：墙 404/429/网络异常 → 优雅空墙/错误条，不白屏；alias/stats 失败静默。

const { request, getFriendlyError } = require('../../utils/api');
const { findCard, computeImagePath } = require('../../utils/cards');
const { ZODIAC_BY_KEY } = require('../../utils/energy');
const analytics = require('../../utils/analytics');

const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';
const PACT_KEY = 'resonance_pact_v1';
const GIVE_LIMIT = 10; // 与后端 _RESONANCE_DAILY_LIMIT 一致（响应 limit 为准）

/** 今日牌小图路径（墙/我的卡只有 name_zh，经 findCard 反查注册表再算图） */
function _cardImage(card) {
  if (!card || !card.name_zh) return '';
  const found = findCard(card.name_zh);
  if (!found) return '';
  return computeImagePath(found, IMAGE_BASE);
}

/** 星座 key → { emoji, name }（缺省 ✦ / 空名） */
function _zodiacOf(key) {
  const z = ZODIAC_BY_KEY[key] || null;
  return {
    emoji: (z && z.emoji) || '✦',
    name: (z && z.name) || '',
  };
}

Page({
  data: {
    pageLoading: true,
    pageError: null,

    isLoggedIn: false,
    alias: '',

    // 墙
    activeCount: 0,
    groups: [], // [{type,label,icon,members:[{uid,key,alias,zodiacEmoji,zodiacText,starNumber,cardName,cardImage,tierName,resonateCount,resonatedByMe,imgError}]}]
    hasGroups: false, // 布尔预计算（规避 wxml .length 缺陷）
    hasMyCard: false,
    myCard: null, // {alias,zodiacEmoji,zodiacText,starNumber,cardName,cardImage,tierName,receivedToday,imgError}

    // 我的共鸣（stats）
    hasStats: false,
    stats: null, // {givenTotal,receivedTotal,receivedToday}
    remainToday: GIVE_LIMIT, // 今日剩余可送出次数（give 响应 count_today 校准）

    // 隐身开关
    visible: true,

    // 公约弹窗
    showPact: false,

    // 共鸣动效（单实例：点击的卡片内渲染上浮星点）
    flyStar: null, // {uid, seed}

    // 共鸣海报
    showPoster: false,
    posterLoading: false,
    posterData: null,
  },

  // 乐观锁（防连点重复送出）
  _giving: false,
  _posterBusy: false,

  onLoad() {
    // 首次进入弹「星光公约」（三行说明 + 可随时在本页关闭展示）
    if (!wx.getStorageSync(PACT_KEY)) {
      this.setData({ showPact: true });
    }
    const isLoggedIn = !!wx.getStorageSync('token');
    this.setData({ isLoggedIn });
    this._loadWall();
  },

  onPullDownRefresh() {
    this._loadWall(true).then(() => wx.stopPullDownRefresh());
  },

  /** 拉共鸣墙（公开免登录；失败优雅降级不白屏） */
  async _loadWall(fromPull) {
    try {
      const wall = await request('/resonance/wall');
      this._applyWall(wall || {});
      this.setData({ pageLoading: false, pageError: null });
      // 登录后进页先确保星名落库（后端规则：无星名不上墙）+ 拉统计
      if (this.data.isLoggedIn) {
        this._loadAlias();
        this._loadStats();
      }
    } catch (err) {
      if (fromPull) {
        this.setData({ pageError: null });
        wx.showToast({ title: getFriendlyError(err), icon: 'none' });
        return;
      }
      // 公开接口 404（尚未部署）或限流 429：仍展示空墙框架，给出温和提示
      this.setData({
        pageLoading: false,
        pageError: err.statusCode === 404 ? '星光墙暂未点亮，稍后再来 ✦' : getFriendlyError(err),
        activeCount: 0,
        groups: [],
        hasGroups: false,
        hasMyCard: false,
      });
    }
  },

  /** 墙响应 → 页面数据（布尔字段预计算 + 每颗星归一化） */
  _applyWall(wall) {
    const groups = (wall.groups || []).map((g, gidx) => ({
      type: g.type,
      label: g.label || '',
      icon: this._groupIcon(g),
      members: (g.members || []).map((m, midx) => this._memberView(m, gidx, midx)),
    }));
    const myCardRaw = wall.my_card || null;
    const myCard = myCardRaw
      ? {
          alias: myCardRaw.alias || '',
          zodiacEmoji: _zodiacOf(myCardRaw.zodiac).emoji,
          zodiacText: _zodiacOf(myCardRaw.zodiac).name,
          starNumber: myCardRaw.star_number,
          cardName: (myCardRaw.card && myCardRaw.card.name_zh) || '',
          cardImage: _cardImage(myCardRaw.card),
          tierName: myCardRaw.tier_name || '',
          receivedToday: myCardRaw.received_today || 0,
          imgError: false,
        }
      : null;
    this.setData({
      activeCount: wall.active_count || 0,
      groups,
      hasGroups: groups.length > 0,
      myCard,
      hasMyCard: !!myCard,
    });
  },

  _memberView(m, gidx, midx) {
    return {
      uid: m.uid,
      key: `${gidx}-${midx}-${m.uid}`,
      alias: m.alias || '无名星',
      zodiacEmoji: _zodiacOf(m.zodiac).emoji,
      zodiacText: _zodiacOf(m.zodiac).name,
      starNumber: m.star_number,
      cardName: (m.card && m.card.name_zh) || '',
      cardImage: _cardImage(m.card),
      tierName: m.tier_name || '',
      resonateCount: m.resonate_count || 0,
      resonatedByMe: !!m.resonated_by_me,
      imgError: false,
    };
  },

  /** 组标题星图标：同星座=星座符、同星光数=✦、同一张牌=🃏、兜底=✦ */
  _groupIcon(g) {
    if (g.type === 'zodiac') {
      const first = (g.members || []).find((m) => m.zodiac);
      return _zodiacOf(first && first.zodiac).emoji;
    }
    if (g.type === 'card') return '🃏';
    return '✦';
  },

  /** 进页确保星名（GET /resonance/alias：首次生成落库，此后恒定；失败静默） */
  async _loadAlias() {
    try {
      const data = await request('/resonance/alias');
      if (data && data.alias) this.setData({ alias: data.alias });
    } catch (err) {
      console.warn('[resonance] alias 拉取失败（不影响看墙）:', err.statusCode || err.message);
    }
  },

  /** 我的共鸣统计（失败静默——不影响墙主流程） */
  async _loadStats() {
    try {
      const s = await request('/resonance/stats');
      this.setData({
        hasStats: true,
        stats: {
          givenTotal: s.given_total || 0,
          receivedTotal: s.received_total || 0,
          receivedToday: s.received_today || 0,
        },
      });
    } catch (err) {
      console.warn('[resonance] stats 拉取失败（静默）:', err.statusCode || err.message);
    }
  },

  /** 点 ✦ 送出共鸣：动效 + 计数 +1 + 今日剩余校准；防重/超限/隐身原样反馈 */
  async onGiveResonance(e) {
    const { uid, gidx, midx } = e.currentTarget.dataset;
    const group = this.data.groups[gidx];
    if (!group || !group.members[midx]) return;
    const member = group.members[midx];

    if (member.resonatedByMe) {
      wx.showToast({ title: '已共鸣过这颗星 ✦', icon: 'none' });
      return;
    }
    if (!this.data.isLoggedIn) {
      this._promptLogin('登录后即可为同频的星送出共鸣 ✦');
      return;
    }
    if (this._giving) return; // 防连点
    this._giving = true;

    try {
      const res = await request('/resonance/give', {
        method: 'POST',
        data: { to_user_id: uid },
      });
      // 本地更新：实心星 + 计数 +1 + 剩余次数校准 + stats 累计给出 +1
      const groups = this.data.groups.slice();
      const members = (groups[gidx].members || []).slice();
      members[midx] = Object.assign({}, members[midx], {
        resonatedByMe: true,
        resonateCount: (members[midx].resonateCount || 0) + 1,
      });
      groups[gidx] = Object.assign({}, groups[gidx], { members });
      const remainToday = Math.max(0, (res.limit || GIVE_LIMIT) - (res.count_today || 0));
      const stats = this.data.stats
        ? Object.assign({}, this.data.stats, { givenTotal: this.data.stats.givenTotal + 1 })
        : null;
      this.setData({ groups, remainToday, stats, flyStar: { uid, seed: Date.now() } });
      analytics.trackEvent('resonance_give', { source: 'wall' });
      if (remainToday <= 0) {
        wx.showToast({ title: '今天已经送出 10 颗星，明天再来 ✦', icon: 'none' });
      } else {
        wx.showToast({ title: `共鸣成功 ✦ 今日还剩 ${remainToday} 次`, icon: 'none' });
      }
    } catch (err) {
      this._handleGiveError(err, gidx, midx);
    } finally {
      this._giving = false;
    }
  },

  /** give 失败分支：409 幂等 / 400 超限 / 404 隐身 / 401 过期 / 其余网络 */
  _handleGiveError(err, gidx, midx) {
    const status = err.statusCode;
    const msg = err.message || '';
    if (status === 409 || msg.indexOf('已共鸣') !== -1) {
      wx.showToast({ title: '已共鸣过这颗星 ✦', icon: 'none' });
      this._markResonated(gidx, midx); // 本地对齐实心（并发/重复点击兜底）
    } else if (status === 400) {
      // 超 10 次：后端消息原样展示（设计要点）
      wx.showToast({ title: msg || '今天已经送出 10 颗星，明天再来 ✦', icon: 'none' });
      this.setData({ remainToday: 0 });
    } else if (status === 404) {
      // 目标已隐身/不存在：原样展示 + 本地置为不可再点
      wx.showToast({ title: msg || '这颗星不在夜空中 ✦', icon: 'none' });
      this._markResonated(gidx, midx);
    } else if (status === 401) {
      wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' });
      this.setData({ isLoggedIn: false });
    } else {
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  /** 将某颗星本地标记为已共鸣（实心 + 不可再点），与服务端状态对齐 */
  _markResonated(gidx, midx) {
    const group = this.data.groups[gidx];
    if (!group || !group.members[midx]) return;
    const groups = this.data.groups.slice();
    const members = groups[gidx].members.slice();
    if (members[midx].resonatedByMe) return;
    members[midx] = Object.assign({}, members[midx], { resonatedByMe: true });
    groups[gidx] = Object.assign({}, groups[gidx], { members });
    this.setData({ groups });
  },

  /** 星点上浮动效结束 → 清理动画节点 */
  onFlyStarEnd() {
    this.setData({ flyStar: null });
  },

  /** 卡片牌图加载失败 → 回退纯文字色块（不破坏卡片版式） */
  onCardImgError(e) {
    const key = e.currentTarget.dataset.key;
    const groups = this.data.groups.map((g) => ({
      type: g.type,
      label: g.label,
      icon: g.icon,
      members: g.members.map((m) =>
        m.key === key ? Object.assign({}, m, { imgError: true }) : m
      ),
    }));
    this.setData({ groups });
  },

  /** 我的卡片牌图加载失败 → 回退纯文字色块 */
  onMyCardImgError() {
    if (!this.data.myCard) return;
    this.setData({ myCard: Object.assign({}, this.data.myCard, { imgError: true }) });
  },

  /** 公约弹窗滚动穿透拦截（无操作） */
  noop() {},

  /** 隐身开关：关闭需确认（影响对外展示），开启即时生效 */
  onToggleVisibility(e) {
    const next = !!(e && e.detail && e.detail.value);
    if (next) {
      this._setVisibility(true);
      return;
    }
    wx.showModal({
      title: '确认隐身',
      content: '关闭后，你的星将从共鸣墙与共鸣海报中消失；你仍可看墙、收共鸣与送共鸣。随时可再点亮。',
      confirmText: '确认隐身',
      cancelText: '取消',
      success: (r) => {
        if (r.confirm) this._setVisibility(false);
        else this.setData({ visible: true }); // 取消 → 开关拨回
      },
    });
  },

  async _setVisibility(v) {
    try {
      await request('/resonance/visibility', { method: 'POST', data: { visible: v } });
      this.setData({ visible: v });
      analytics.trackEvent('resonance_visibility', { visible: v ? 1 : 0 });
      wx.showToast({ title: v ? '你的星重新点亮 ✦' : '已隐身 ✦', icon: 'none' });
    } catch (err) {
      // 请求失败回滚开关状态（即时生效语义以服务端为准）
      this.setData({ visible: !v });
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  /** 生成共鸣海报（GET /resonance/poster；404 隐身 → 原样展示） */
  async onGeneratePoster(e) {
    const { uid } = e.currentTarget.dataset;
    if (!this.data.isLoggedIn) {
      this._promptLogin('登录后即可生成你们的共鸣海报 ✦');
      return;
    }
    if (this._posterBusy) return;
    this._posterBusy = true;
    this.setData({ posterLoading: true });
    try {
      const data = await request(`/resonance/poster?to_user_id=${encodeURIComponent(uid)}`);
      this.setData({ posterData: this._normalizePoster(data || {}), posterLoading: false, showPoster: true });
    } catch (err) {
      this.setData({ posterLoading: false });
      if (err.statusCode === 404) {
        wx.showToast({ title: err.message || '这颗星不在夜空中 ✦', icon: 'none' });
      } else {
        wx.showToast({ title: getFriendlyError(err), icon: 'none' });
      }
    } finally {
      this._posterBusy = false;
    }
  },

  /** /resonance/poster 响应 → 海报绘制归一化数据 */
  _normalizePoster(p) {
    const za = _zodiacOf(p.zodiac_a);
    const zb = _zodiacOf(p.zodiac_b);
    return {
      aliasA: p.alias_a || '',
      aliasB: p.alias_b || '',
      zodiacA: p.zodiac_a,
      zodiacB: p.zodiac_b,
      zodiacEmojiA: za.emoji,
      zodiacEmojiB: zb.emoji,
      zodiacNameA: za.name,
      zodiacNameB: zb.name,
      starNumberA: p.star_number_a,
      starNumberB: p.star_number_b,
      cardAName: (p.card_a && p.card_a.name_zh) || '',
      cardBName: (p.card_b && p.card_b.name_zh) || '',
      tierNameA: p.tier_name_a || '',
      tierNameB: p.tier_name_b || '',
      dimension: p.dimension || 'number',
      caption: p.caption || '两颗星在同一片夜空相遇 ✦',
      disclaimer: p.disclaimer || '仅供娱乐 · 星光映照',
    };
  },

  onClosePoster() {
    this.setData({ showPoster: false, posterData: null });
  },

  onSharePosterToFriend(e) {
    const imagePath = (e.detail && e.detail.imagePath) || '';
    wx.showShareImageMenu({
      path: imagePath,
      fail: () => {},
    });
  },

  /** 公约弹窗：确认后写 storage（本次不再弹） */
  onPactConfirm() {
    wx.setStorageSync(PACT_KEY, true);
    this.setData({ showPact: false });
    analytics.trackEvent('resonance_pact_seen', {});
  },

  onRetry() {
    this.setData({ pageLoading: true, pageError: null });
    this._loadWall();
  },

  _promptLogin(content) {
    wx.showModal({
      title: '需要登录',
      content: content || '登录后即可参与共鸣',
      confirmText: '去登录',
      cancelText: '先看看',
      success: (r) => {
        if (r.confirm) wx.reLaunch({ url: '/pages/index/index' });
      },
    });
  },

  onShareAppMessage() {
    return {
      title: '看看今天谁与你同星 ✦',
      path: '/pages/resonance/resonance',
    };
  },
});
