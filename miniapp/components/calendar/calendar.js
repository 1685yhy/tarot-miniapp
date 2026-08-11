// components/calendar/calendar.js
// 共用月历组件 —— T1-4 星光手账（星点模式）首发；T2-4 星象日历复用（事件模式）
//
// 设计为"可配置数据源"：
//   - markMode='stars'（默认）→ 每天读 `starColorField`/`brightnessField` 渲染星点，
//     未记录且非未来的天渲染"极淡星尘点"（留一颗星的位子）
//   - markMode='events'（阶段 2 星象日历）→ 每天读 `days[i].events` 渲染事件徽标
//     （`eventEmojiField`/`eventLabelField` 可配置，默认 'emoji'/'label'）
//   - 今天高亮环、左右滑切月、月头 ‹ 年月 › 翻页均由组件自带；切换月触发
//     `monthchange` 事件，父层拉取新数据后回传 `days` 属性即可（组件按日期归位）
//
// 事件：
//   daytap:     detail {date: 'YYYY-MM-DD', hasStar: bool}
//   monthchange: detail {year, month}

function pad(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

function fmtDate(y, m, d) {
  return `${y}-${pad(m)}-${pad(d)}`;
}

function todayStr() {
  const now = new Date();
  return fmtDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

Component({
  properties: {
    year: { type: Number, value: 0 },
    month: { type: Number, value: 0 },
    days: { type: Array, value: [] },
    today: { type: String, value: '' },
    // 标记模式：stars=星点（手账）；events=事件徽标（星象日历复用）
    markMode: { type: String, value: 'stars' },
    // 数据源字段可配置（复用阶段可指向不同字段名）
    starColorField: { type: String, value: 'star_color' },
    brightnessField: { type: String, value: 'brightness' },
    eventEmojiField: { type: String, value: 'emoji' },
    eventLabelField: { type: String, value: 'label' },
  },

  data: {
    WEEKDAYS: ['一', '二', '三', '四', '五', '六', '日'],
    displayYear: 0,
    displayMonth: 0,
    cells: [],
  },

  observers: {
    'year, month': function (y, m) {
      if (y && m) {
        this.setData({ displayYear: y, displayMonth: m });
        this._rebuild();
      }
    },
    'days, markMode, today': function () {
      this._rebuild();
    },
  },

  lifetimes: {
    attached() {
      if (this.data.year && this.data.month) {
        this.setData({ displayYear: this.data.year, displayMonth: this.data.month });
      }
      this._rebuild();
    },
  },

  methods: {
    /** 由 props（days）＋当前展示年月重建 42 格网格 */
    _rebuild() {
      const { displayYear: y, displayMonth: m, markMode } = this.data;
      if (!y || !m) return;
      const tStr = this.data.today || todayStr();
      const firstWeekday = (new Date(y, m - 1, 1).getDay() + 6) % 7; // 周一=0
      const daysInMonth = new Date(y, m, 0).getDate();

      const dayMap = {};
      (this.data.days || []).forEach((d) => {
        if (d && d.date) dayMap[d.date] = d;
      });

      const cells = [];
      const total = 42; // 6 行 × 7 列，保证任意月首对齐
      for (let i = 0; i < total; i++) {
        const dayNum = i - firstWeekday + 1;
        if (dayNum < 1 || dayNum > daysInMonth) {
          cells.push({ key: `pad-${i}`, day: '', date: '', inMonth: false });
          continue;
        }
        const date = fmtDate(y, m, dayNum);
        const info = dayMap[date] || {};
        const brightness = Number(info[this.data.brightnessField]) || 0;
        const starColor = info[this.data.starColorField] || '';
        const events = Array.isArray(info.events) ? info.events : [];
        const hasStar = markMode === 'events' ? events.length > 0 : !!(starColor && brightness > 0);
        // 事件模式的展示字段在 JS 预计算（避免 wxml 按动态 key 取对象）
        const firstEvent = events.length > 0 ? events[0] : null;
        cells.push({
          key: date,
          day: dayNum,
          date,
          inMonth: true,
          isToday: date === tStr,
          isFuture: date > tStr,
          hasStar,
          brightness,
          starColor,
          events,
          eventEmoji: firstEvent ? firstEvent[this.data.eventEmojiField] : '',
          eventLabel: firstEvent ? firstEvent[this.data.eventLabelField] : '',
          // 极淡星尘点：未记录、非未来——"留一颗星的位子"
          dust: !hasStar && date <= tStr,
        });
      }
      this.setData({ cells });
    },

    _changeMonth(delta) {
      let y = this.data.displayYear;
      let m = this.data.displayMonth + delta;
      if (m < 1) { m = 12; y -= 1; }
      if (m > 12) { m = 1; y += 1; }
      if (y < 2000 || y > 2100) return;
      this.setData({ displayYear: y, displayMonth: m });
      this._rebuild();
      this.triggerEvent('monthchange', { year: y, month: m });
    },

    onPrevMonth() {
      this._changeMonth(-1);
    },

    onNextMonth() {
      this._changeMonth(1);
    },

    _touchX: 0,

    onTouchStart(e) {
      this._touchX = e.touches && e.touches[0] ? e.touches[0].clientX : 0;
    },

    onTouchEnd(e) {
      const touch = e.changedTouches && e.changedTouches[0];
      if (!touch) return;
      const dx = touch.clientX - this._touchX;
      if (Math.abs(dx) < 40) return; // 低于阈值视为点击，不切月
      this._changeMonth(dx < 0 ? 1 : -1);
    },

    onDayTap(e) {
      const { date, hasStar } = e.currentTarget.dataset;
      if (!date) return;
      this.triggerEvent('daytap', { date, hasStar });
    },
  },
});
