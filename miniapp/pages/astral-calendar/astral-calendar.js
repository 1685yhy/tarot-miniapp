// pages/astral-calendar/astral-calendar.js —— 星空时刻表（SDD P1 · T3-4）
//
// 星象日历页，双视图：
//   - 月历视图：共用 calendar 组件（mark-mode="events"）——事件日符号徽标、
//     无事件日月相小字（全月每天都有月相）、今天高亮环；左右滑/翻页切月
//   - 事件列表视图：当月事件分组列表（逆行等区间事件显示起止，触月界加 …）
// 顶部"下一节点倒计时"卡：数据来自后端 next_event（days_until 纯函数计算）
// 点事件日/列表行/倒计时卡 → 事件详情底部弹层（GET /astral/events/{date}：
//   事件卡 note + 星象宜忌 + 活动形态）→ "进入节点活动" 跳
//   /pages/astral-event/astral-event?type=xxx（T3-5 建页；页未建时降级 toast）
// 数据降级：月历接口失败 → 错误态+重试；日详情失败 → 用月历已有数据渲染弹层
//   并提示；next_event 缺失 → 隐藏倒计时卡；月内无事件 → 「星空从不缺席，
//   只是有时安静。」

const { request, getFriendlyError } = require('../../utils/api');
const analytics = require('../../utils/analytics');

// 事件类型 → 符号徽标（设计 3.2：新月🌑/满月🌕/水逆☿/日月食/节气）
const EVENT_EMOJI = {
  new_moon: '🌑',
  full_moon: '🌕',
  mercury_retrograde: '☿',
  venus_retrograde: '♀',
  solar_eclipse: '🌘',
  lunar_eclipse: '🌗',
  solar_term: '🍃',
};

// 活动形态命名（设计 3.5 星光叙事：新月=许愿之夜、满月=复盘之夜、水逆=慢行期）
const ACTIVITY_NAMES = {
  wish: '许愿之夜',
  review: '复盘之夜',
  mercury_guide: '慢行期指南',
  info: '星象资讯',
};

function pad(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

function fmtDate(y, m, d) {
  return `${y}-${pad(m)}-${pad(d)}`;
}

/** 'YYYY-MM-DD' 的次日（字符串比较安全的日期推进） */
function nextDayStr(dateStr) {
  const p = dateStr.split('-');
  const d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]) + 1);
  return fmtDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

/** 'YYYY-MM-DD' → '8.12' */
function fmtShort(dateStr) {
  const p = dateStr.split('-');
  return `${Number(p[1])}.${Number(p[2])}`;
}

/** 'YYYY-MM-DD' → '2026年8月12日 · 周三' */
function fmtDateLabel(dateStr) {
  const p = dateStr.split('-');
  const d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  return `${Number(p[0])}年${Number(p[1])}月${Number(p[2])}日 · ${week}`;
}

Page({
  data: {
    todayStr: '',
    year: 0,
    month: 0,
    viewMode: 'calendar', // calendar | list
    loading: true,
    error: null,
    calDays: [], // {date, phase_emoji, phase_label, events:[{type,label,emoji,moon_sign}]}
    eventList: [], // 事件列表视图行
    hasMonthEvents: false, // WXML 编译环境不认 .length > 0，JS 预计算
    hasNoEvents: false, // 本月零事件（空态文案用）
    nextEvent: null, // {type,label,date,days_until,emoji,countdownText,dateLabel}

    // 事件详情底部弹层
    detailVisible: false,
    detailLoading: false,
    detailError: '',
    detailDate: '',
    detailDateLabel: '',
    detailIsToday: false,
    detailPhaseEmoji: '',
    detailPhaseLabel: '',
    detailEvents: [], // {type,label,note,emoji}
    detailHasEvents: false, // T1-5 教训：WXML 编译环境不认 .length > 0，JS 预计算
    detailGuidance: null, // {do, dont}
    detailActivity: '', // wish | review | mercury_guide | info | ''
    detailActivityName: '',
  },

  onLoad() {
    const now = new Date();
    this.setData({
      todayStr: fmtDate(now.getFullYear(), now.getMonth() + 1, now.getDate()),
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    });
    this._loadCalendar(false);
  },

  onShow() {
    // 静默刷新：从节点活动页打卡返回后倒计时/月历状态保持最新
    if (this._loadedOnce) {
      this._loadCalendar(true);
    }
    this._loadedOnce = true;
  },

  onShareAppMessage() {
    return {
      title: '星光映照 · 星空时刻表',
      path: '/pages/index/index',
    };
  },

  // ============================================================
  // 月历数据（GET /astral/calendar）
  // ============================================================

  async _loadCalendar(silent) {
    if (!silent) this.setData({ loading: true, error: null });
    try {
      const data = await request(
        `/astral/calendar?year=${this.data.year}&month=${this.data.month}`
      );
      // 事件模式展示字段在 JS 预计算（组件按字段名取值，避免动态 key）
      const days = (data.days || []).map((d) => ({
        date: d.date,
        phase_emoji: d.phase ? d.phase.emoji : '',
        phase_label: d.phase ? d.phase.label : '',
        events: (d.events || []).map((ev) => ({
          type: ev.type,
          label: ev.label,
          emoji: EVENT_EMOJI[ev.type] || '✦',
          moon_sign: ev.moon_sign || '',
        })),
      }));
      const eventList = this._buildEventList(days);
      this.setData({
        loading: false,
        error: null,
        calDays: days,
        eventList,
        hasMonthEvents: eventList.length > 0,
        hasNoEvents: eventList.length === 0,
        nextEvent: this._prepareNextEvent(data.next_event || null),
      });
    } catch (err) {
      if (!silent) {
        this.setData({ loading: false, error: getFriendlyError(err) });
      }
    }
  },

  onRetry() {
    this.setData({ error: null, loading: true });
    this._loadCalendar(false);
  },

  onMonthChange(e) {
    const { year, month } = e.detail;
    this.setData({ year, month });
    this._loadCalendar(true);
  },

  /** 下一节点倒计时卡数据（days_until: 0=今夜 / 1=明天 / N天后） */
  _prepareNextEvent(next) {
    if (!next || !next.date) return null;
    const d = Number(next.days_until);
    const countdownText = d <= 0 ? '今夜' : d === 1 ? '明天' : `${d} 天后`;
    const p = next.date.split('-');
    const dt = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][dt.getDay()];
    return {
      type: next.type,
      label: next.label,
      date: next.date,
      days_until: d,
      emoji: EVENT_EMOJI[next.type] || '✦',
      countdownText,
      dateLabel: `${Number(p[1])}月${Number(p[2])}日 · ${week}`,
    };
  },

  // ============================================================
  // 事件列表视图（由当月 days 聚合：同类型连续日期合并为区间）
  // ============================================================

  _buildEventList(days) {
    if (!days || days.length === 0) return [];
    // 按事件类型聚合出现记录 (date, label)——同日多事件各自独立成组；
    // 同类型非连续日各自成组（如 立秋/处暑 同为 solar_term 但独立展示）
    const byType = {};
    days.forEach((d) => {
      (d.events || []).forEach((ev) => {
        (byType[ev.type] = byType[ev.type] || []).push({
          date: d.date,
          label: ev.label,
        });
      });
    });

    // 每类型内按日期升序，连续日期合并为区间（水逆等区间事件显示起止；
    // 区间不与同日其他事件（如节气）互相打断）
    const spans = [];
    Object.keys(byType).forEach((type) => {
      const occ = byType[type].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
      let start = occ[0].date;
      let end = occ[0].date;
      let label = occ[0].label;
      const flush = () => spans.push({ type, label, start, end });
      for (let i = 1; i < occ.length; i++) {
        if (nextDayStr(end) === occ[i].date) {
          end = occ[i].date;
          label = occ[i].label; // 区间内以最新 label 为准（逆行区间标签恒一致）
        } else {
          flush();
          start = occ[i].date;
          end = occ[i].date;
          label = occ[i].label;
        }
      }
      flush();
    });

    const firstDay = `${this.data.year}-${pad(this.data.month)}-01`;
    const lastDay = days[days.length - 1].date;
    return spans
      .map((s) => {
        const isRange = s.start !== s.end;
        let dateText;
        if (isRange) {
          dateText = `${fmtShort(s.start)} – ${fmtShort(s.end)}`;
          // 区间触月界：起于月初/止于月末 → 用 … 提示跨月延续
          if (s.start === firstDay) dateText = `…${dateText}`;
          if (s.end === lastDay) dateText = `${dateText}…`;
        } else {
          dateText = fmtShort(s.start);
        }
        return {
          key: `${s.type}-${s.start}-${s.end}`,
          type: s.type,
          emoji: EVENT_EMOJI[s.type] || '✦',
          label: s.label,
          start: s.start,
          end: s.end,
          dateText,
          isRange,
        };
      })
      .sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
  },

  onSwitchView(e) {
    const mode = e.currentTarget.dataset.mode;
    if (mode === this.data.viewMode) return;
    this.setData({ viewMode: mode });
    analytics.trackEvent('astral_view_switch', { mode });
  },

  // ============================================================
  // 事件详情弹层（GET /astral/events/{date}）
  // ============================================================

  onDayTap(e) {
    const { date } = e.detail || {};
    if (!date) return;
    this._openDayDetail(date);
  },

  onEventItemTap(e) {
    const date = e.currentTarget.dataset.date;
    if (date) this._openDayDetail(date);
  },

  onCountdownTap() {
    const ne = this.data.nextEvent;
    if (!ne || !ne.date) return;
    analytics.trackEvent('astral_countdown_tap', { type: ne.type });
    this._openDayDetail(ne.date);
  },

  /** 打开某日事件详情：先用月历已有数据铺底，再拉日详情补 note/宜忌/活动形态 */
  async _openDayDetail(date) {
    const day = (this.data.calDays || []).find((d) => d.date === date) || null;
    const dayEvents = day ? day.events : [];
    this.setData({
      detailVisible: true,
      detailLoading: true,
      detailError: '',
      detailDate: date,
      detailDateLabel: fmtDateLabel(date),
      detailIsToday: date === this.data.todayStr,
      detailPhaseEmoji: day ? day.phase_emoji : '',
      detailPhaseLabel: day ? day.phase_label : '',
      detailEvents: dayEvents.map((ev) => ({
        type: ev.type,
        label: ev.label,
        emoji: EVENT_EMOJI[ev.type] || '✦',
        note: '',
      })),
      detailHasEvents: dayEvents.length > 0,
      detailGuidance: null,
      detailActivity: '',
      detailActivityName: '',
    });
    try {
      const res = await request(`/astral/events/${date}`);
      const activity = res.activity || '';
      const resEvents = res.events || [];
      this.setData({
        detailLoading: false,
        detailEvents: resEvents.map((ev) => ({
          type: ev.type,
          label: ev.label,
          emoji: EVENT_EMOJI[ev.type] || '✦',
          note: ev.note || '',
        })),
        detailHasEvents: resEvents.length > 0,
        detailGuidance: res.guidance || null,
        detailActivity: activity,
        detailActivityName: ACTIVITY_NAMES[activity] || '星象资讯',
      });
    } catch (err) {
      // 降级：月历已有数据渲染（无 note/宜忌，活动入口隐藏）
      this.setData({
        detailLoading: false,
        detailError: '详情加载失败，已展示当日概览',
      });
    }
  },

  /** 进入节点活动页（T3-5 建页后直达；页未建时降级 toast） */
  onEnterNode() {
    const type = this.data.detailActivity;
    if (!type || type === 'info') return;
    analytics.trackEvent('astral_node_entry', { type, source: 'astral_calendar' });
    wx.navigateTo({
      url: `/pages/astral-event/astral-event?type=${type}`,
      fail: () => {
        wx.showToast({ title: '节点活动即将上线 ✦', icon: 'none' });
      },
    });
  },

  closeDetail() {
    this.setData({ detailVisible: false });
  },

  preventClose() {
    // 阻止事件冒泡——防止点击弹层内部元素时关闭
  },
});
