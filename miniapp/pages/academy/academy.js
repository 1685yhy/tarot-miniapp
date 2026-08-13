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

    // 星图
    stars: [],
    total: 78,
    learned: 0,
    percent: 0,
    titles: [],
    starColors: STAR_COLORS,
    hasLegend: true,

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
    guideReminderOn: false, // 引导确认后回写的提醒状态
  },

  _busy: false,      // 路径进入防连点
  _loaded: false,    // 首页首次数据已到（避免骨架闪烁）

  onLoad() {
    const isLoggedIn = !!wx.getStorageSync('token');
    this.setData({ isLoggedIn });
    if (!isLoggedIn) {
      this._promptLogin('登录后即可点亮你的星图 ✦');
      return;
    }
    this._loadAll();
  },

  onPullDownRefresh() {
    if (!this.data.isLoggedIn) {
      wx.stopPullDownRefresh();
      return;
    }
    this._loadAll().then(() => wx.stopPullDownRefresh());
  },

  /** 并发拉取概览 + 计划 */
  async _loadAll() {
    try {
      const [overview, plan] = await Promise.all([
        request('/academy/overview'),
        request('/academy/plan'),
      ]);
      this._applyOverview(overview || {});
      this._applyPlan(plan || {});
      this.setData({ pageLoading: false, pageError: null });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
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
      await request('/academy/plan', {
        method: 'POST',
        data: {
          cards_per_day: plan.cards_per_day || 0,
          reminder_on: !!plan.reminder_on,
          path,
        },
      });
      const next = await request(
        `/academy/lesson/next?path=${encodeURIComponent(path)}&pos=${plan.cursor_pos || 0}`
      );
      if (next && next.card_id) {
        analytics.trackEvent('academy_path_enter', { path });
        wx.navigateTo({ url: `/pages/academy/lesson/lesson?card_id=${next.card_id}` });
      }
    } catch (err) {
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    } finally {
      this._busy = false;
    }
  },

  /** 今日学牌 → 学习卡页 */
  onTodayCardTap() {
    const tc = this.data.todayCard;
    if (!tc || !tc.card_id) return;
    wx.navigateTo({ url: `/pages/academy/lesson/lesson?card_id=${tc.card_id}` });
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

  _promptLogin(content) {
    wx.showModal({
      title: '需要登录',
      content: content || '登录后即可点亮你的星图',
      confirmText: '去登录',
      cancelText: '先看看',
      success: (r) => {
        if (r.confirm) wx.reLaunch({ url: '/pages/index/index' });
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
