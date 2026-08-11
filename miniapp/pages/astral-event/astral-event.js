// pages/astral-event/astral-event.js —— 星象节点活动页三形态（SDD P1 · T3-5）
//
// 三形态（设计 3.2 / 3.5 星光叙事）：
//   - wish（许愿之夜）      新月窗口倒计时 + 许愿引导卡 + 愿望状态总览
//                            → 跳转现有 pages/wish/wish（流程复用不重做）
//   - review（复盘之夜）    愿望状态总览预览（active/grown/answered 计数）
//                            → 跳转现有 pages/review/review
//   - mercury_guide（慢行期）水逆区间倒计时 + 「慢下来的 7 件小事」清单勾选
//                            点亮星星 + 每日一句；全部点亮 → POST /astral/activity
//                            打卡 +1 星尘（幂等）。合规：只谈自我关怀，无
//                            化解/转运/防小人/避开类措辞
//   - info（星象资讯）      其余事件类型（日月食/节气）直达时的说明卡片兜底
//
// 数据：GET /astral/event/{事件类型}（注意：接口入参是**事件类型**
//   new_moon/full_moon/mercury_retrograde，而日历页跳转携带的是**活动形态**
//   wish/review/mercury_guide → 本页先做词汇表双向映射再请求）
// 打卡：POST /astral/activity {event_key} → {ok, rewarded, stardust_total}
//   rewarded=false = 当天已打卡（幂等，不重复 toast 奖励）；本地按日记录
//   已打卡态，同日重进直接展示完成态
// 约定：WXML 不用 .length > 0 表达式（T1-5 教训），所有布尔一律 JS 预计算

const { request, getFriendlyError } = require('../../utils/api');
const analytics = require('../../utils/analytics');

// 活动形态 → 接口入参所需的事件类型（日历页跳转携带的是活动形态）
const NODE_TO_EVENT = {
  wish: 'new_moon',
  review: 'full_moon',
  mercury_guide: 'mercury_retrograde',
};

// 事件类型 → 活动形态（直接以事件类型打开本页（如订阅消息直达）时反向映射）
const EVENT_TO_NODE = {
  new_moon: 'wish',
  full_moon: 'review',
  mercury_retrograde: 'mercury_guide',
};

// 活动形态 → 页面叙事元数据（设计 3.5：新月=许愿之夜、满月=复盘之夜、水逆=慢行期）
const NODE_META = {
  wish: { title: '许愿之夜', subtitle: '写给月亮的三行愿望', emoji: '🌑' },
  review: { title: '复盘之夜', subtitle: '满月照见 · 愿望回望', emoji: '🌕' },
  mercury_guide: { title: '慢行期', subtitle: '这段日子，允许自己慢一点', emoji: '☿' },
  info: { title: '星象资讯', subtitle: '今夜星空笔记', emoji: '✦' },
};

// 愿望状态展示（与 wish 页 STATUS_META 同语义）
const WISH_STATUS_META = [
  { key: 'active', label: '生长中', cls: 'count-chip--active' },
  { key: 'grown', label: '已生长', cls: 'count-chip--grown' },
  { key: 'answered', label: '待回应', cls: 'count-chip--answered' },
];

// 本地已打卡记录：{wish: 'YYYY-MM-DD', review: ..., mercury_guide: ...}
const CHECKIN_STORAGE_KEY = 'astral_node_checkin';

function pad(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

/** 'YYYY-MM-DD' → '8.12'（空/非法回退 ''；年段允许 4 位） */
function fmtShort(dateStr) {
  const p = String(dateStr || '').split('-');
  if (p.length !== 3 || !p.every((s) => /^\d{1,4}$/.test(s))) return '';
  return `${Number(p[1])}.${Number(p[2])}`;
}

/** 倒计时文案：0=今天结束 / 1=明天结束 / N=还有 N 天；非法回退 '' */
function daysLeftText(days, tail) {
  const d = days == null || !Number.isFinite(Number(days)) ? null : Number(days);
  if (d == null) return '';
  if (d <= 0) return `今天${tail}`;
  if (d === 1) return `明天${tail}`;
  return `还有 ${d} 天${tail}`;
}

Page({
  // 本页形态（onLoad 从 query 解析后固定），请求序号守卫（防静默刷新竞态）
  _nodeType: '',
  _eventType: '',
  _today: '',
  _reqId: 0,

  data: {
    loading: true,
    error: null,
    nodeType: '',        // wish | review | mercury_guide | info
    meta: null,          // {title, subtitle, emoji}

    // 许愿窗口（wish）
    windowText: '',      // '8.12 – 8.14'
    windowDaysText: '',
    content: '',         // 引导卡主文案

    // 愿望状态总览（wish / review 复用；计数 0 时展示空态文案）
    wishStatus: [],      // [{key, label, cls, count}]
    hasAnyWish: false,

    // 慢行期（mercury_guide）
    rangeText: '',       // '8.14 – 9.04'
    rangeDaysText: '',
    rangeActive: false,  // range 有数据（后端空对象规格化 {start:"",end:"",days_left:0}）
    dailySentence: '',
    careItems: [],       // [{text, done}]
    stars: [],           // [{lit}] 星星排（与 careItems 同长）
    hasCareItems: false, // WXML 不认 .length > 0，JS 预计算
    litCount: 0,
    totalItems: 0,
    allLit: false,
    canCheckIn: false,   // 区间有效且今天在区间内才可打卡

    // 资讯兜底（info）
    infoNotes: [],       // [String]
    hasInfoNotes: false,

    // 打卡态
    checkedToday: false,
    checking: false,
  },

  onLoad(options) {
    const raw = String((options && options.type) || '').trim();
    this._today = this._todayStr();
    // 双向词汇表映射：形态直传（日历页）或事件类型直传（订阅消息）均可达
    const nodeType = NODE_TO_EVENT[raw] ? raw : EVENT_TO_NODE[raw] || 'info';
    const eventType = NODE_TO_EVENT[raw] || raw;
    this._nodeType = nodeType;
    this._eventType = eventType;
    const meta = NODE_META[nodeType] || NODE_META.info;
    this.setData({ nodeType, meta });
    wx.setNavigationBarTitle({ title: meta.title });
    this._loadContent(false);
  },

  onShow() {
    // 从 wish/review 页做完动作返回 → 静默刷新愿望计数与已打卡态；
    // 慢行期不刷新（保留清单勾选进度）
    if (this._loadedOnce && (this.data.nodeType === 'wish' || this.data.nodeType === 'review')) {
      this._loadContent(true);
    }
    this._loadedOnce = true;
  },

  onShareAppMessage() {
    return {
      title: `星光映照 · ${(this.data.meta && this.data.meta.title) || '星象节点'}`,
      path: `/pages/astral-event/astral-event?type=${this.data.nodeType}`,
    };
  },

  // ============================================================
  // 节点内容（GET /astral/event/{事件类型}）
  // ============================================================

  async _loadContent(silent) {
    const reqId = ++this._reqId; // 序号守卫：静默刷新与首次加载竞态时丢弃过期响应
    if (!silent) this.setData({ loading: true, error: null });
    try {
      const data = await request(`/astral/event/${this._eventType}`);
      if (reqId !== this._reqId) return;
      this._renderContent(data);
    } catch (err) {
      if (reqId !== this._reqId) return;
      if (silent) {
        // 静默失败：保留现有内容，不清空页面
        return;
      }
      this.setData({ loading: false, error: getFriendlyError(err) });
    }
  },

  onRetry() {
    this.setData({ error: null, loading: true });
    this._loadContent(false);
  },

  /** 后端节点内容 → 页面展示数据（所有布尔/派生文本在 JS 预计算） */
  _renderContent(data) {
    const type = data.type || this._nodeType;
    const meta = NODE_META[type] || NODE_META.info;
    const patch = { loading: false, error: null, nodeType: type, meta };
    wx.setNavigationBarTitle({ title: meta.title });

    if (type === 'wish') {
      const win = data.window || {};
      const start = fmtShort(win.start);
      const end = fmtShort(win.end);
      patch.windowText = start && end ? `${start} – ${end}` : '';
      patch.windowDaysText = win.days_left != null ? daysLeftText(win.days_left, '结束') : '';
      patch.content = data.content || '写给月亮的三行愿望';
    }

    if (type === 'wish' || type === 'review') {
      const counts = data.wish_counts || {};
      patch.wishStatus = WISH_STATUS_META.map((s) => ({
        key: s.key,
        label: s.label,
        cls: s.cls,
        count: counts[s.key] || 0,
      }));
      patch.hasAnyWish =
        (counts.active || 0) + (counts.grown || 0) + (counts.answered || 0) > 0;
    }

    if (type === 'mercury_guide') {
      const range = data.range || {};
      const rangeActive = !!(range.start && range.end);
      const items = Array.isArray(data.items) ? data.items : [];
      const inRange =
        rangeActive && this._today >= range.start && this._today <= range.end;
      patch.rangeActive = rangeActive;
      patch.rangeText = rangeActive ? `${fmtShort(range.start)} – ${fmtShort(range.end)}` : '';
      patch.rangeDaysText = rangeActive ? daysLeftText(range.days_left, '结束') : '';
      patch.dailySentence = data.daily_sentence || '';
      patch.careItems = items.map((t) => ({ text: t, done: false }));
      patch.stars = items.map(() => ({ lit: false }));
      patch.hasCareItems = items.length > 0;
      patch.totalItems = items.length;
      patch.litCount = 0;
      patch.allLit = false;
      patch.canCheckIn = rangeActive && inRange;
    }

    if (type === 'info') {
      const notes = Array.isArray(data.notes) ? data.notes : [];
      patch.infoNotes = notes;
      patch.hasInfoNotes = notes.length > 0;
    }

    patch.checkedToday = this._readCheckin() === this._today;
    this.setData(patch);
  },

  // ============================================================
  // 引导跳转（复用现有许愿/复盘流程，本页只做引导）
  // ============================================================

  onGoWish() {
    analytics.trackEvent('astral_node_go', { from: 'astral_event', node: 'wish' });
    wx.navigateTo({ url: '/pages/wish/wish' });
  },

  onGoReview() {
    analytics.trackEvent('astral_node_go', { from: 'astral_event', node: 'review' });
    wx.navigateTo({ url: '/pages/review/review' });
  },

  onGoCalendar() {
    wx.navigateBack({
      fail: () => wx.navigateTo({ url: '/pages/astral-calendar/astral-calendar' }),
    });
  },

  // ============================================================
  // 慢行期清单：勾选点亮星星
  // ============================================================

  onToggleItem(e) {
    if (this.data.checking) return;
    const idx = Number(e.currentTarget.dataset.index);
    const items = this.data.careItems.slice();
    if (!Number.isFinite(idx) || idx < 0 || idx >= items.length) return;
    items[idx] = { ...items[idx], done: !items[idx].done };
    const litCount = items.filter((i) => i.done).length;
    this.setData({
      careItems: items,
      stars: items.map((i) => ({ lit: i.done })),
      litCount,
      allLit: litCount === items.length && items.length > 0,
    });
    analytics.trackEvent('astral_care_toggle', { index: idx, done: items[idx].done, lit: litCount });
  },

  // ============================================================
  // 节点打卡（POST /astral/activity，幂等）
  // ============================================================

  async onCheckIn() {
    const { nodeType, checking, checkedToday, allLit } = this.data;
    if (checking || checkedToday) return;
    if (nodeType === 'mercury_guide' && !allLit) return;
    this.setData({ checking: true });
    try {
      const res = await request('/astral/activity', {
        method: 'POST',
        data: { event_key: nodeType },
      });
      // 无论 rewarded 与否，服务端状态已定（重复=已打卡）→ 本地按日标记
      this._writeCheckin();
      this.setData({ checking: false, checkedToday: true });
      analytics.trackEvent('astral_checkin', { type: nodeType, rewarded: !!res.rewarded });
      if (res.rewarded) {
        wx.vibrateShort && wx.vibrateShort({ type: 'light' });
        wx.showToast({ title: '节点已点亮 · 星尘 +1 ✦', icon: 'none', duration: 2000 });
      } else {
        wx.showToast({ title: '今天已经点亮过啦 ✦', icon: 'none' });
      }
    } catch (err) {
      this.setData({ checking: false });
      wx.showToast({ title: getFriendlyError(err) || '打卡失败，请稍后再试', icon: 'none', duration: 2200 });
    }
  },

  // ── 本地按日已打卡记录（同日重进展示完成态；次日自动失效可再次打卡）──

  _todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  },

  _readCheckin() {
    try {
      const map = wx.getStorageSync(CHECKIN_STORAGE_KEY) || {};
      return map[this.data.nodeType] || null;
    } catch (e) {
      return null;
    }
  },

  _writeCheckin() {
    try {
      const map = wx.getStorageSync(CHECKIN_STORAGE_KEY) || {};
      map[this.data.nodeType] = this._today;
      wx.setStorageSync(CHECKIN_STORAGE_KEY, map);
    } catch (e) {
      /* 存储失败不影响服务端幂等 */
    }
  },
});
