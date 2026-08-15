// pages/academy/academy.js —— 星灵学堂主页（SDD P2 阶段3 · T6-5）
//
// 页面 = 星空书卷：
//   1. 顶部「我的星图」——78 颗星点排成环（大阿卡纳 22 亮金 + 小阿卡纳 56
//      按四元素配色），已学点亮 / 未学淡星尘点（与手账夜空同语言）
//   2. 进度文案「78 颗星里，你已经点亮了 N 颗」；未开始时空态
//      「78 颗星在书卷里等你——从愚者之行走起」
//   3. 今日学牌卡（overview.today_card → lesson 页）
//   4. 四路径卡：愚者之旅 / 四元素庭院 / 今日之牌 / 与你相遇的牌
//      （点选 = 选定计划路径 → POST /academy/plan → lesson/next → 学习卡页）
//   5. 计划设置面板：每日 N 张（1/3/5）+ 提醒开关（默认关 + 明示
//      「学习提醒日，当天星光晨讯/星语将换成今日学牌」+ quota_warning
//      → maybePromptSubscribe 授权引导）
//
// 接口：GET /academy/overview · GET/POST /academy/plan · GET /academy/lesson/next
// 数据降级：overview/plan 失败 → 错误态可重试，不白屏。
//
// 注：星图按「已学 N 颗 → 环上前 N 颗点亮」渲染（overview 只回总数，
// 不回逐张已学列表；若未来需要逐星精确点亮，后端需补已学 card_id 列表）。

const { request, getFriendlyError } = require('../../utils/api');
const { maybePromptSubscribe } = require('../../utils/subscribe');
const analytics = require('../../utils/analytics');
const { navTo } = require('../../utils/nav-guard');

// 星点配色（E3 奶油治愈色系派生）：大阿卡纳亮金，小阿卡纳按四元素
const STAR_COLORS = {
  major: '#C9A97C',    // 亮金 — 大阿卡纳 22 颗
  wands: '#D9A36B',    // 暖杏 — 权杖·火
  cups: '#A3B8D6',     // 雾蓝 — 圣杯·水
  swords: '#B0A0CC',   // 灰紫 — 宝剑·风
  pentacles: '#A3C0A2',// 苔绿 — 星币·土
};

// 星环上星点组序：大阿卡纳 22 → 权杖 14 → 圣杯 14 → 宝剑 14 → 星币 14
const RING_ORDER = ['major', 'wands', 'cups', 'swords', 'pentacles'];
const GROUP_SIZES = { major: 22, wands: 14, cups: 14, swords: 14, pentacles: 14 };

// 环半径（容器百分比）：横 46 / 竖 38，留出四角呼吸
const RX = 46;
const RY = 38;

// 路径展示数据（名称/副题 verbatim 设计 1.2）
const PATH_META = {
  major: { name: '愚者之旅', sub: '大阿卡纳 0 → 21', emoji: '🃏' },
  minor: { name: '四元素庭院', sub: '权杖火 · 圣杯水 · 宝剑风 · 星币土', emoji: '🌿' },
  random: { name: '今日之牌', sub: '与今日抽牌同源', emoji: '✨' },
  related: { name: '与你相遇的牌', sub: '读牌历史里的高频之牌', emoji: '💫' },
};

// ===================== 全通庆祝（T6-6） =====================
// 称号 → 庆祝信息（与后端 MILESTONES 表 title_name 对齐：
// fool_journey 全通大阿卡纳 22 → 星辉学者；full_78 全通 78 → 星光塔罗师）
// rewards 与 lesson 里程碑弹层 reward chip 同语言（wall=true 走粉色壁纸变体，
// 与 lesson.wxml 的 milestone.wallpaper_granted chip 对齐）
const CELEBRATE_META = {
  '星辉学者': {
    storageKey: 'academy_celebrated_fool_journey',
    title: '称号解锁 · 星辉学者',
    sub: '全通大阿卡纳 22 张，愚者之旅圆满 ✦',
    rewards: [
      { text: '星尘 +3', wall: false },
    ],
  },
  '星光塔罗师': {
    storageKey: 'academy_celebrated_full_78',
    title: '称号解锁 · 星光塔罗师',
    sub: '点亮全部 78 颗星，星空书卷为你合上 ✦',
    rewards: [
      { text: '星尘 +10', wall: false },
      { text: '星光壁纸解锁', wall: true },
    ],
  },
};

// 星光雨配色（E3 派生：亮金/暖杏/雾蓝/灰紫）
const RAIN_COLORS = ['#C9A97C', '#D9A36B', '#A3B8D6', '#B0A0CC'];
const RAIN_CHARS = ['✦', '✧', '✦', '✧', '✦'];

/** 生成星光雨星点（确定性伪随机：同一次生成结果可复现，便于审查） */
function _buildRainStars() {
  const stars = [];
  const count = 28;
  let seed = 20260813;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  for (let i = 0; i < count; i++) {
    stars.push({
      key: `rain-${i}`,
      left: (rand() * 100).toFixed(1),
      delay: (rand() * 1.2).toFixed(2),
      duration: (2.0 + rand() * 1.6).toFixed(2),
      size: (22 + rand() * 30).toFixed(0),
      color: RAIN_COLORS[Math.floor(rand() * RAIN_COLORS.length)],
      char: RAIN_CHARS[Math.floor(rand() * RAIN_CHARS.length)],
    });
  }
  return stars;
}

/** 生成 78 颗星点（环状排布，坐标为容器百分比） */
function _buildStars(learnedCount) {
  const stars = [];
  let seq = 0;
  RING_ORDER.forEach((group) => {
    const size = GROUP_SIZES[group];
    const color = STAR_COLORS[group];
    for (let i = 0; i < size; i++) {
      // 从正上方开始顺时针均匀排布
      const angle = (seq / 78) * Math.PI * 2 - Math.PI / 2;
      const x = 50 + RX * Math.cos(angle);
      const y = 50 + RY * Math.sin(angle);
      stars.push({
        key: `${group}-${i}`,
        x: x.toFixed(2),
        y: y.toFixed(2),
        color,
        major: group === 'major',
        learned: seq < learnedCount, // 已学点亮前 N 颗（确定性顺序）
      });
      seq++;
    }
  });
  return stars;
}

Page({
  data: {
    pageLoading: true,
    pageError: null,
    isLoggedIn: false,
    needLogin: false, // 未登录空态（取消登录弹窗后仍可停留，有内容有出口）

    // 星图
    stars: [],
    total: 78,
    learned: 0,
    percent: 0,
    titles: [],
    starColors: STAR_COLORS,

    // 今日学牌
    todayCard: null, // {card_id, name_zh, reason}

    // 四路径
    paths: [],

    // 计划设置
    plan: null,       // {cards_per_day, reminder_on, path, cursor_pos}
    planCounts: [     // 0=关闭（后端 Literal 0|1|3|5）
      { value: 0, label: '关闭' },
      { value: 1, label: '1 张' },
      { value: 3, label: '3 张' },
      { value: 5, label: '5 张' },
    ],
    savingPlan: false,

    // 订阅授权引导（quota_warning → maybePromptSubscribe）
    showSubscribeGuide: false,

    // 全通庆祝（T6-6）：全屏星光雨 + 称号授予弹层
    showCelebrate: false,
    celebrateTitle: '',
    celebrateSub: '',
    celebrateRewards: [], // [{text, wall}] 奖励 chip（壁纸解锁对齐 lesson 里程碑弹层）
    rainStars: [],
  },

  _busy: false,       // 路径进入防连点
  _loading: false,    // 首屏/下拉加载中（防并发）
  _loadedOnce: false, // 首次数据已到（onShow 静默刷新门槛）
  _destroyed: false,  // 页面销毁守卫（异步回调不再 setData）

  onLoad() {
    this._destroyed = false;
    const isLoggedIn = !!wx.getStorageSync('token');
    if (!isLoggedIn) {
      // 未登录：渲染「登录后点亮星图」空态（有内容有出口），不卡骨架屏
      this.setData({ isLoggedIn: false, pageLoading: false, needLogin: true });
      this._promptLogin('登录后即可点亮你的星图 ✦');
      return;
    }
    this.setData({ isLoggedIn: true });
    this._loadAll();
  },

  onUnload() {
    // 页面销毁守卫：异步回调/静默刷新不再触发 setData
    this._destroyed = true;
  },

  /** 学完返回 / 从其他页回来：静默刷新星图与计划（不闪骨架） */
  onShow() {
    if (!this.data.isLoggedIn || this.data.needLogin) return;
    if (this.data.pageLoading || this._loading || !this._loadedOnce) return;
    this._refreshSilent();
  },

  onPullDownRefresh() {
    const isLoggedIn = !!wx.getStorageSync('token');
    if (!isLoggedIn) {
      wx.stopPullDownRefresh();
      return;
    }
    if (this.data.needLogin) this.setData({ needLogin: false });
    this._loadAll().then(() => wx.stopPullDownRefresh());
  },

  /** 并发拉取概览 + 计划 */
  async _loadAll() {
    if (this._loading) return;
    this._loading = true;
    try {
      const [overview, plan] = await Promise.all([
        request('/academy/overview'),
        request('/academy/plan'),
      ]);
      if (this._destroyed) return;
      this._applyOverview(overview || {});
      this._applyPlan(plan || {});
      this.setData({ pageLoading: false, pageError: null, needLogin: false });
      this._loadedOnce = true;
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    } finally {
      this._loading = false;
    }
  },

  /** 静默刷新（onShow 触发）：失败保留当前内容，下拉可重试 */
  async _refreshSilent() {
    try {
      const [overview, plan] = await Promise.all([
        request('/academy/overview'),
        request('/academy/plan'),
      ]);
      if (this._destroyed) return;
      this._applyOverview(overview || {});
      this._applyPlan(plan || {});
    } catch (err) {
      console.warn('[academy] 静默刷新失败（保留当前内容）:', err.statusCode || err.message);
    }
  },

  /** overview 响应 → 星图 + 路径卡 + 今日学牌 */
  _applyOverview(ov) {
    const learned = ov.learned || 0;
    const paths = (['major', 'minor', 'random', 'related']).map((key) => {
      const p = (ov.paths && ov.paths[key]) || {};
      const meta = PATH_META[key];
      return {
        key,
        name: meta.name,
        sub: meta.sub,
        emoji: meta.emoji,
        learned: p.learned || 0,
        total: p.total, // random/related 后端 total=null
        hasTotal: typeof p.total === 'number',
      };
    });
    const todayCard = ov.today_card
      ? {
          card_id: ov.today_card.card_id,
          name_zh: ov.today_card.name_zh || '',
          reason: ov.today_card.reason || '',
        }
      : null;
    this.setData({
      stars: _buildStars(learned),
      total: ov.total || 78,
      learned,
      percent: ov.percent || 0,
      titles: ov.titles || [],
      paths,
      todayCard,
    });
    this._maybeCelebrate(ov.titles || []);
  },

  /**
   * 全通庆祝（T6-6）：overview 称号含「星辉学者/星光塔罗师」且本地
   * 未庆祝过 → 全屏星光雨 + 称号授予弹层（每称号仅一次，storage 旗标）。
   * 跨页去重契约：卡页里程碑弹层展示时已写旗标（lesson.js onRemember
   * 写 `academy_celebrated_<milestone.key>`）→ 本页跳过；本页庆祝仅在
   * 旗标缺失时兜底触发一次（写入方与读取方同键同语义，自洽）。
   */
  _maybeCelebrate(titles) {
    for (const title of Object.keys(CELEBRATE_META)) {
      if (titles.indexOf(title) < 0) continue;
      const meta = CELEBRATE_META[title];
      let celebrated = false;
      try { celebrated = !!wx.getStorageSync(meta.storageKey); } catch (_e) { celebrated = false; }
      if (celebrated) continue;
      try { wx.setStorageSync(meta.storageKey, true); } catch (_e) { /* 存失败不阻塞展示 */ }
      if (this._destroyed) return;
      this.setData({
        showCelebrate: true,
        celebrateTitle: meta.title,
        celebrateSub: meta.sub,
        celebrateRewards: meta.rewards || [],
        rainStars: _buildRainStars(),
      });
      analytics.trackEvent('academy_milestone_celebrate', { title });
      return;
    }
  },

  /** 庆祝弹层关闭（星光雨已播完，直接收起） */
  onCloseCelebrate() {
    this.setData({ showCelebrate: false });
  },

  /** plan 响应 → 计划面板（保持已有路径选择不变） */
  _applyPlan(plan) {
    this.setData({
      plan: {
        cards_per_day: plan.cards_per_day || 0,
        reminder_on: !!plan.reminder_on,
        path: plan.path || 'major',
        cursor_pos: plan.cursor_pos || 0,
      },
    });
  },

  // ===================== 四路径进入 =====================

  /** 点选路径卡：先落计划路径，再取下一张进学习卡页 */
  async onPathTap(e) {
    const { path } = e.currentTarget.dataset;
    if (this._busy) return;
    if (!this.data.isLoggedIn) {
      this._promptLogin('登录后即可开始学习 ✦');
      return;
    }
    this._busy = true;
    const plan = this.data.plan || {};
    try {
      const planRes = await request('/academy/plan', {
        method: 'POST',
        data: {
          cards_per_day: plan.cards_per_day || 0,
          reminder_on: !!plan.reminder_on,
          path,
        },
      });
      // 游标以 POST 响应为准（切路径后服务端 upsert 的 cursor_pos 才是权威值，
      // 本地 plan.cursor_pos 可能是旧路径/旧时刻的，直接用它请求 next 会错位）
      const cursorPos =
        planRes && typeof planRes.cursor_pos === 'number'
          ? planRes.cursor_pos
          : plan.cursor_pos || 0;
      // 同步本地计划（path/游标已切换，返回本页时高亮一致）
      if (planRes && !this._destroyed) this._applyPlan(planRes);
      const next = await request(
        `/academy/lesson/next?path=${encodeURIComponent(path)}&pos=${cursorPos}`
      );
      if (this._destroyed) return;
      if (next && next.card_id) {
        analytics.trackEvent('academy_path_enter', { path });
        navTo(`/pages/academy/lesson/lesson?card_id=${next.card_id}`);
      }
    } catch (err) {
      if (this._destroyed) return;
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    } finally {
      this._busy = false;
    }
  },

  /** 今日学牌 → 学习卡页 */
  onTodayCardTap() {
    const tc = this.data.todayCard;
    if (!tc || !tc.card_id) return;
    navTo(`/pages/academy/lesson/lesson?card_id=${tc.card_id}`);
  },

  // ===================== 计划设置 =====================

  /** 每日 N 张 点选（1/3/5/关闭） */
  onPlanCountTap(e) {
    const count = Number(e.currentTarget.dataset.count);
    if (count === this.data.plan.cards_per_day) return;
    this._savePlan({ cards_per_day: count });
  },

  /** 学习提醒开关（默认关；开启时若每日 0 张 → 一并设为 1 张） */
  onReminderChange(e) {
    const next = !!(e && e.detail && e.detail.value);
    const patch = { reminder_on: next };
    if (next && this.data.plan.cards_per_day === 0) {
      patch.cards_per_day = 1;
    }
    this._savePlan(patch);
  },

  async _savePlan(patch) {
    if (this.data.savingPlan) return;
    this.setData({ savingPlan: true });
    const cur = this.data.plan || {};
    const data = Object.assign(
      {
        cards_per_day: cur.cards_per_day || 0,
        reminder_on: !!cur.reminder_on,
        path: cur.path || 'major',
      },
      patch
    );
    try {
      const res = await request('/academy/plan', { method: 'POST', data });
      if (this._destroyed) return;
      const quotaWarning = !!res.quota_warning;
      this.setData({
        plan: {
          cards_per_day: res.cards_per_day,
          reminder_on: !!res.reminder_on,
          path: res.path || 'major',
          cursor_pos: res.cursor_pos || 0,
        },
        savingPlan: false,
      });
      analytics.trackEvent('academy_plan_save', {
        cards_per_day: res.cards_per_day,
        reminder_on: res.reminder_on ? 1 : 0,
      });
      if (quotaWarning) {
        // 提醒已开但无订阅额度 → 引导授权（不硬拦，见后端契约）
        this.setData({ showSubscribeGuide: true });
        return;
      }
      wx.showToast({
        title: data.reminder_on ? '已保存 · 学习提醒已开启 ✦' : '已保存 ✦',
        icon: 'none',
      });
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ savingPlan: false });
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  /** 订阅授权引导：确认 → maybePromptSubscribe（模板未配置时不弹，静默） */
  onGuideConfirm() {
    this.setData({ showSubscribeGuide: false });
    maybePromptSubscribe();
  },

  onGuideCancel() {
    this.setData({ showSubscribeGuide: false });
  },

  /** 引导弹层滚动穿透拦截（无操作） */
  noop() {},

  // ===================== 通用 =====================

  onRetry() {
    this.setData({ pageLoading: true, pageError: null });
    this._loadAll();
  },

  /** 未登录空态的「去登录」按钮 */
  onGoLogin() {
    wx.reLaunch({ url: '/pages/index/index' });
  },

  _promptLogin(content) {
    wx.showModal({
      title: '需要登录',
      content: content || '登录后即可点亮你的星图',
      confirmText: '去登录',
      cancelText: '先看看',
      success: (r) => {
        if (r.confirm) wx.reLaunch({ url: '/pages/index/index' });
        // 取消 → 停留在未登录空态（needLogin），有内容有出口，不再卡骨架屏
      },
    });
  },

  onShareAppMessage() {
    return {
      title: `我已点亮 ${this.data.learned} 颗星 ✦ 一起来星灵学堂`,
      path: '/pages/academy/academy',
    };
  },
});
