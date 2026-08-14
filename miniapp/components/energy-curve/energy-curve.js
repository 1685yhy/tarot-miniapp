/**
 * Energy Curve 组件 —— 周报「星运曲线」canvas 绘制
 * =================================================================
 * 7 天能量总分折线 + 每日星光色点（build_today_guidance 星光色）。
 * 复用 canvas-poster 的 E3 调色板常量（单一色彩来源，无第二套奶油色）。
 *
 * Props:
 *   curve  [{date, total}]  7 天能量总分（无记录日 total=null，不崩溃）
 *   colors [{date, star_color}] 每日星光色（缺失日回退细金）
 *
 * 空态：全周无记录 → 画布内温柔引导「本周夜空还在等待星光 ✦」，不白屏。
 */
const { PALETTE } = require('../../utils/canvas-poster');

const { C_GOLD, C_MUTED } = PALETTE;

const WEEKDAY_LABELS = ['日', '一', '二', '三', '四', '五', '六'];

/** 微信组件属性数组退化形态归一（数字键对象 → 数组） */
function _toArray(v) {
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') return Object.keys(v).map((k) => v[k]);
  return [];
}

Component({
  properties: {
    curve: { type: Array, value: [] },
    colors: { type: Array, value: [] },
  },

  data: {
    canvasW: 0,
    canvasH: 0,
  },

  observers: {
    'curve, colors': function () {
      this._scheduleDraw();
    },
  },

  lifetimes: {
    attached() {
      this._initSize();
    },
    ready() {
      this._draw();
    },
  },

  methods: {
    /* 画布逻辑尺寸（与 WXSS 一致：100% 宽 · 320rpx 高） */
    _initSize() {
      const sys = wx.getSystemInfoSync();
      const width = sys.windowWidth - 64; // 页左右 padding 32rpx*2（750rpx 屏宽换算 px）
      this.setData({
        canvasW: Math.max(width, 250),
        canvasH: Math.round((320 / 750) * (sys.windowWidth || 375)),
      });
    },

    /* 防抖绘制：observer 与 ready 都可能触发 */
    _scheduleDraw() {
      if (this._drawTimer) clearTimeout(this._drawTimer);
      this._drawTimer = setTimeout(() => this._draw(), 60);
    },

    _draw() {
      if (this._drawing) return;
      this._drawing = true;
      const query = wx.createSelectorQuery().in(this);
      query.select('#energyCurveCanvas').fields({ node: true, size: true }).exec((res) => {
        this._drawing = false;
        if (!res || !res[0] || !res[0].node) return;
        const canvas = res[0].node;
        const { width, height } = res[0];
        const dpr = (wx.getSystemInfoSync().pixelRatio) || 2;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        this._drawChart(ctx, width, height);
      });
    },

    _drawChart(ctx, W, H) {
      const curve = _toArray(this.data.curve);
      const colors = _toArray(this.data.colors);

      // 每日星光色映射（build_today_guidance 星光色；缺失日回退细金）
      const colorMap = {};
      colors.forEach((c) => {
        if (c && c.date && c.star_color) colorMap[c.date] = c.star_color;
      });

      ctx.clearRect(0, 0, W, H);

      const padL = 22;
      const padR = 22;
      const padT = 26;
      const padB = 34;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;
      const step = plotW / 6;

      // 7 天补齐（后端保证 7 项，防御性归一）
      const days = [];
      for (let i = 0; i < 7; i++) {
        const p = curve[i] || {};
        days.push({ date: p.date || '', total: p.total == null ? null : p.total });
      }
      const recorded = days.filter((d) => d.total != null);

      const xOf = (i) => padL + step * i;

      // ── 底部星期标注 ──
      days.forEach((d, i) => {
        if (!d.date) return;
        const wd = WEEKDAY_LABELS[new Date(d.date + 'T12:00:00').getDay()] || '';
        ctx.save();
        ctx.fillStyle = C_MUTED;
        ctx.globalAlpha = 0.72;
        ctx.font = '10px "PingFang SC", "Helvetica Neue", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(wd, xOf(i), padT + plotH + 8);
        ctx.restore();
      });

      // ── 空态：全周无记录（统计 0 + 温柔引导，不挫败）──
      if (recorded.length === 0) {
        ctx.save();
        ctx.fillStyle = C_MUTED;
        ctx.globalAlpha = 0.85;
        ctx.font = '12px "PingFang SC", "Helvetica Neue", sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('本周夜空还在等待星光 ✦', W / 2, H / 2);
        ctx.restore();
        return;
      }

      const totals = recorded.map((d) => d.total);
      const min = Math.min.apply(null, totals);
      const max = Math.max.apply(null, totals);
      const yOf = (v) => {
        // 单值周（max==min）→ 居中水平线，避免除零
        if (max === min) return padT + plotH * 0.45;
        return padT + plotH - ((v - min) / (max - min)) * plotH + 2;
      };

      // ── 细金折线（null 日断线，不臆造）──
      ctx.save();
      ctx.strokeStyle = C_GOLD;
      ctx.globalAlpha = 0.9;
      ctx.lineWidth = 1.5;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      ctx.beginPath();
      let penDown = false;
      days.forEach((d, i) => {
        if (d.total == null) {
          penDown = false;
          return;
        }
        const x = xOf(i);
        const y = yOf(d.total);
        if (!penDown) {
          ctx.moveTo(x, y);
          penDown = true;
        } else {
          ctx.lineTo(x, y);
        }
      });
      ctx.stroke();
      ctx.restore();

      // ── 每日星光色点（有记录日 = 星光色实心点；无记录日 = 淡紫小点）──
      days.forEach((d, i) => {
        const x = xOf(i);
        if (d.total != null) {
          const y = yOf(d.total);
          const color = colorMap[d.date] || C_GOLD;
          ctx.save();
          ctx.beginPath();
          ctx.arc(x, y, 4.5, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = '#FFFDF8';
          ctx.stroke();
          ctx.restore();
        } else {
          ctx.save();
          ctx.beginPath();
          ctx.arc(x, padT + plotH * 0.5, 2.4, 0, Math.PI * 2);
          ctx.fillStyle = C_MUTED;
          ctx.globalAlpha = 0.35;
          ctx.fill();
          ctx.restore();
        }
      });
    },
  },
});
