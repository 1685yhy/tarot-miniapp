/**
 * Weekly Report Poster Component
 * Canvas-based "我的星光一周" AI weekly report long image — 9:16 portrait
 * (phone wallpaper style).
 *
 * Layout (top → bottom):
 *   1. "我的星光一周" title + date range
 *   2. Mood trend — 7-day emoji row (one per day)
 *   3. Most frequent card — card image + name + "本周你最常遇到它"
 *   4. AI summary — one-line warm reflection
 *   5. Brand "星光映照" + mini-program code
 *
 * Usage:
 *   <weekly-report-poster
 *     visible="{{showWeeklyPoster}}"
 *     weeklyData="{{weeklyReportData}}"
 *     cardImagePath="{{weeklyCardImage}}"
 *     nickname="{{userNickname}}"
 *     bind:close="onCloseWeeklyPoster"
 *     bind:share="onShareWeeklyPoster"
 *   />
 *
 * weeklyData shape (from GET /report/weekly):
 *   {
 *     week_range: "07.25 ~ 07.31",
 *     week_dates: ["2026-07-25", ...],          // 7 slots
 *     mood_trends: [{ date, mood_score, mood_label, mood_emoji }],
 *     most_frequent_card: { name, count, meaning, keywords },
 *     ai_summary: "一行温暖寄语",
 *     total_readings, diary_count, has_data
 *   }
 */
const { BASE_URL } = require('../../utils/api');

// ── Configuration ────────────────────────────────────────────────────
const TARGET_ASPECT = 9 / 16;         // width / height → 9:16 portrait
const QR_SIZE_RATIO = 0.13;           // QR code as fraction of canvas width
const CARD_WIDTH_RATIO = 0.32;        // card image ~32% of canvas width
const CARD_ASPECT = 1.5;              // tarot card height / width

// ── Colour palette · E3 奶油疗愈明亮主题 ──
// 奶油底渐变 · 墨字 #3D3A36 · 金深标题 #8A6B3D (≈4.6:1) · 三级文字 #6E6A96 (≈4.68:1)
const C_GOLD = '#C9A97C';        // 细金 — decorative (border / star dots)
const C_GOLD_INK = '#8A6B3D';    // 金深 — title / label text on cream
const C_WHITE = '#3D3A36';       // 墨 — body text on cream (12:1)
const C_MUTED = '#6E6A96';       // 深灰紫 — secondary text (4.68:1)
const C_BG_TOP = '#FAF6EF';      // 奶油
const C_BG_MID = '#F7F0E3';
const C_BG_BOT = '#F2ECDF';
const C_PLACEHOLDER = '#F7F0E3'; // card image fallback fill
const C_GLOW = 'rgba(201, 169, 124, 0.18)';   // soft gold glow on cream

const WEEKDAY_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

// =====================================================================
//  Helpers
// =====================================================================

function _roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

function _wrapText(ctx, text, maxWidth) {
  const lines = [];
  let current = '';
  for (const char of text) {
    const test = current + char;
    const metrics = ctx.measureText(test);
    if (metrics.width > maxWidth && current.length > 0) {
      lines.push(current);
      current = char;
    } else {
      current = test;
    }
  }
  if (current) lines.push(current);
  return lines;
}

// =====================================================================
//  Drawing functions
// =====================================================================

/** Decorative star particles sprinkled over the full canvas height. */
function _drawStars(ctx, W, H) {
  const starCount = 14;
  for (let i = 0; i < starCount; i++) {
    const x = ((i * 47) % 100) / 100 * W + ((i % 5) - 2) * 4;
    const y = ((i * 29) % 100) / 100 * H;
    const r = 1.2 + (i % 3) * 0.3;
    ctx.save();
    ctx.fillStyle = i % 2 === 0 ? C_GOLD : C_MUTED;
    ctx.globalAlpha = 0.35 + (i % 3) * 0.15;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

/** Small brand line at the very top. Returns Y just below it. */
function _drawBrand(ctx, W, Y) {
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.globalAlpha = 0.9;
  ctx.font = `bold ${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('✦ 星光映照 ✦', W / 2, Y);
  ctx.restore();
  return Y + Math.round(W * 0.040);
}

/** Section label (金深, letter-spaced). */
function _drawSectionLabel(ctx, W, Y, label) {
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.globalAlpha = 0.95;
  ctx.font = `bold ${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(label, W / 2, Y);
  ctx.restore();
  return Y + Math.round(W * 0.048);
}

/** Thin gold divider line (cream 上加透明). */
function _drawDivider(ctx, W, Y) {
  const lineW = Math.round(W * 0.22);
  ctx.save();
  ctx.strokeStyle = C_GOLD;
  ctx.globalAlpha = 0.5;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo((W - lineW) / 2, Y);
  ctx.lineTo((W + lineW) / 2, Y);
  ctx.stroke();
  ctx.restore();
}

/**
 * Mood trend — 7 emoji slots (one per day). Missing days get a dim dot.
 * Returns Y just below the row.
 */
function _drawMoodRow(ctx, W, Y, weekDates, moodMap, moodCount) {
  const slotW = W / 7;
  const emojiFont = Math.round(W * 0.066);
  const labelFont = Math.round(W * 0.022);
  const emojiY = Y;
  const labelY = Y + Math.round(W * 0.084);

  for (let i = 0; i < 7; i++) {
    const cx = slotW * i + slotW / 2;
    const dateStr = weekDates[i] || '';
    const trend = moodMap[dateStr];
    const weekday = WEEKDAY_LABELS[new Date(dateStr + 'T12:00:00').getDay()];

    if (trend && trend.mood_emoji) {
      ctx.save();
      ctx.font = `${emojiFont}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(trend.mood_emoji, cx, emojiY);
      ctx.restore();
    } else {
      // Unrecorded day — dim star dot
      ctx.save();
      ctx.fillStyle = C_MUTED;
      ctx.globalAlpha = 0.35;
      ctx.font = `${emojiFont}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('·', cx, emojiY + Math.round(W * 0.012));
      ctx.restore();
    }

    ctx.save();
    ctx.fillStyle = trend ? C_WHITE : C_MUTED;
    ctx.globalAlpha = trend ? 0.85 : 0.4;
    ctx.font = `${labelFont}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(weekday, cx, labelY);
    ctx.restore();
  }

  // Recorded-day count line (only when the week is partially recorded)
  const summaryY = labelY + Math.round(W * 0.034);
  if (moodCount > 0 && moodCount < 7) {
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.globalAlpha = 0.7;
    ctx.font = `${Math.round(W * 0.023)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`本周记录了 ${moodCount} 天的星光心情`, W / 2, summaryY);
    ctx.restore();
    return summaryY + Math.round(W * 0.042);
  }
  if (moodCount === 7) {
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.globalAlpha = 0.7;
    ctx.font = `${Math.round(W * 0.023)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('七天星光心情，一天不落 ✦', W / 2, summaryY);
    ctx.restore();
    return summaryY + Math.round(W * 0.042);
  }
  return labelY + Math.round(W * 0.038);
}

/**
 * Most frequent card — card image (gold glow + border), name, caption.
 * Returns Y just below the block.
 */
function _drawTopCard(ctx, W, Y, card, cardImg) {
  if (!card || !card.name) return Y + Math.round(W * 0.004);

  const cardW = Math.round(W * CARD_WIDTH_RATIO);
  const cardH = Math.round(cardW * CARD_ASPECT);
  const cardX = Math.round((W - cardW) / 2);
  const r = Math.round(cardW * 0.02);

  // Soft golden glow behind the card (E3)
  const glowPad = Math.round(W * 0.014);
  ctx.save();
  ctx.fillStyle = C_GLOW;
  _roundRect(ctx, cardX - glowPad, Y - glowPad, cardW + glowPad * 2, cardH + glowPad * 2, r + glowPad);
  ctx.fill();
  ctx.restore();

  // Card image (clipped to rounded rect) + gold border
  ctx.save();
  _roundRect(ctx, cardX, Y, cardW, cardH, r);
  ctx.clip();
  if (cardImg) {
    ctx.drawImage(cardImg, cardX, Y, cardW, cardH);
  } else {
    ctx.fillStyle = C_PLACEHOLDER;
    ctx.fillRect(cardX, Y, cardW, cardH);
  }
  ctx.restore();

  ctx.save();
  _roundRect(ctx, cardX, Y, cardW, cardH, r);
  ctx.strokeStyle = C_GOLD;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.75;
  ctx.stroke();
  ctx.restore();

  // Card name (金深 — 4.6:1 on cream)
  const nameY = Y + cardH + Math.round(W * 0.030);
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.font = `bold ${Math.round(W * 0.040)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(card.name, W / 2, nameY);
  ctx.restore();

  // Caption — "本周你最常遇到它 · N次"
  const capY = nameY + Math.round(W * 0.058);
  ctx.save();
  ctx.fillStyle = C_MUTED;
  ctx.globalAlpha = 0.85;
  ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(
    `本周你最常遇到它 · ${card.count || 1}次`,
    W / 2,
    capY
  );
  ctx.restore();

  return capY + Math.round(W * 0.046);
}

/**
 * AI summary — one-line warm reflection (wrapped, capped to fit above QR).
 */
function _drawAISummary(ctx, W, Y, summary, qrAreaY) {
  if (!summary) return Y + Math.round(W * 0.004);

  const maxW = Math.round(W * 0.76);
  const x = Math.round((W - maxW) / 2);
  const fontSize = Math.round(W * 0.030);
  const lineH = Math.round(fontSize * 1.6);
  const maxLines = Math.max(
    1,
    Math.min(4, Math.floor((qrAreaY - Y - Math.round(W * 0.010)) / lineH))
  );

  ctx.save();
  ctx.fillStyle = C_WHITE;
  ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';

  const lines = _wrapText(ctx, summary, maxW);
  let textY = Y;
  for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
    ctx.fillText(lines[i], x, textY);
    textY += lineH;
  }
  ctx.restore();

  return Y + Math.min(lines.length, maxLines) * lineH;
}

/** QR code (mini-program code) + call-to-action. */
function _drawQRCode(ctx, W, Y, qrImg) {
  const qrSize = Math.round(W * QR_SIZE_RATIO);
  const qrX = Math.round((W - qrSize) / 2);
  const gap = Math.round(W * 0.020);
  const qrAreaY = Y + gap;

  ctx.save();
  _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
  ctx.clip();
  if (qrImg) {
    ctx.drawImage(qrImg, qrX, qrAreaY, qrSize, qrSize);
  } else {
    ctx.fillStyle = C_WHITE;
    ctx.fillRect(qrX, qrAreaY, qrSize, qrSize);
  }
  ctx.restore();

  ctx.save();
  _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
  ctx.strokeStyle = 'rgba(201, 169, 124, 0.50)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();

  const ctaY = qrAreaY + qrSize + 4;
  ctx.save();
  ctx.fillStyle = C_MUTED;
  ctx.globalAlpha = 0.8;
  ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('扫码 · 记录你的星光日常', W / 2, ctaY);
  ctx.restore();
}

/** Brand footer (金深). */
function _drawFooter(ctx, W, Y) {
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.globalAlpha = 0.85;
  ctx.font = `${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('星光映照 · 塔罗占卜', W / 2, Y);
  ctx.restore();
}

// =====================================================================
//  Component
// =====================================================================

Component({
  properties: {
    visible: {
      type: Boolean,
      value: false,
      observer: '_onVisibleChange',
    },
    weeklyData: {
      type: Object,
      value: null,
    },
    cardImagePath: {
      type: String,
      value: '',
    },
    nickname: {
      type: String,
      value: '',
    },
  },

  data: {
    previewPath: '',
    drawError: false,
    isDrawing: false,
    canvasW: 0,
    canvasH: 0,
  },

  methods: {
    /* ---------------------------------------------------------------
       Lifecycle: when visible changes to true, trigger drawing
       --------------------------------------------------------------- */
    _onVisibleChange(visible) {
      if (visible) {
        this._initCanvasSize();
        this._drawPoster();
      } else {
        this.setData({
          previewPath: '',
          drawError: false,
          isDrawing: false,
        });
      }
    },

    /* ---------------------------------------------------------------
       Canvas logical size — 9:16 portrait (phone wallpaper style)
       --------------------------------------------------------------- */
    _initCanvasSize() {
      const sysInfo = wx.getSystemInfoSync();
      const screenWidth = sysInfo.screenWidth || 375;
      const posterW = screenWidth;
      const posterH = Math.round(posterW / TARGET_ASPECT);
      this.setData({
        canvasW: posterW,
        canvasH: posterH,
      });
    },

    /* ---------------------------------------------------------------
       Draw the poster on the canvas
       --------------------------------------------------------------- */
    _drawPoster() {
      const { weeklyData, cardImagePath } = this.properties;
      if (!weeklyData || typeof weeklyData !== 'object') {
        this.setData({ drawError: true });
        return;
      }

      this.setData({ isDrawing: true, drawError: false });

      const sysInfo = wx.getSystemInfoSync();
      const W = sysInfo.screenWidth || 375;
      const dpr = sysInfo.pixelRatio || 2;
      const H = Math.round(W / TARGET_ASPECT);

      const query = wx.createSelectorQuery().in(this);
      query.select('#weeklyCanvas').fields({ node: true, size: true }).exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          this.setData({ drawError: true, isDrawing: false });
          return;
        }

        const canvas = res[0].node;
        const ctx = canvas.getContext('2d');
        canvas.width = Math.round(W * dpr);
        canvas.height = Math.round(H * dpr);
        ctx.scale(dpr, dpr);

        // ── 1. Background gradient ──
        const gradient = ctx.createLinearGradient(0, 0, 0, H);
        gradient.addColorStop(0, C_BG_TOP);
        gradient.addColorStop(0.5, C_BG_MID);
        gradient.addColorStop(1, C_BG_BOT);
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, W, H);

        // ── 2. Decorative stars ──
        _drawStars(ctx, W, H);

        // ── 3. Load card image + QR, then draw everything ──
        let cardImageLoaded = !cardImagePath;
        let qrImageLoaded = false;
        let cardImg = null;
        let qrImg = null;
        let drawAttempted = false;

        const _tryDraw = () => {
          if (drawAttempted) return;
          if (!cardImageLoaded || !qrImageLoaded) return;
          drawAttempted = true;

          // Build mood map keyed by date
          const moodMap = {};
          (weeklyData.mood_trends || []).forEach((t) => {
            if (t && t.date) moodMap[t.date] = t;
          });
          const weekDates = weeklyData.week_dates && weeklyData.week_dates.length === 7
            ? weeklyData.week_dates
            : Array.from({ length: 7 }, (_, i) => {
                const d = new Date();
                d.setDate(d.getDate() - (6 - i));
                return d.toISOString().slice(0, 10);
              });

          // ── 4. Header: brand + title + date range ──
          let y = _drawBrand(ctx, W, Math.round(W * 0.028));
          y += Math.round(W * 0.006);

          ctx.save();
          ctx.fillStyle = C_GOLD_INK;
          ctx.font = `bold ${Math.round(W * 0.064)}px "PingFang SC", "Helvetica Neue", sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText('我的星光一周', W / 2, y);
          ctx.restore();
          y += Math.round(W * 0.082);

          if (weeklyData.week_range) {
            ctx.save();
            ctx.fillStyle = C_MUTED;
            ctx.globalAlpha = 0.85;
            ctx.font = `${Math.round(W * 0.027)}px "PingFang SC", "Helvetica Neue", sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText(weeklyData.week_range, W / 2, y);
            ctx.restore();
            y += Math.round(W * 0.044);
          }

          _drawDivider(ctx, W, y);
          y += Math.round(W * 0.040);

          // ── 5. Mood trend — 7-day emoji row ──
          y = _drawSectionLabel(ctx, W, y, '本周心情轨迹');
          y = _drawMoodRow(ctx, W, y, weekDates, moodMap, (weeklyData.mood_trends || []).length);
          y += Math.round(W * 0.008);

          // ── 6. Most frequent card ──
          if (weeklyData.most_frequent_card && weeklyData.most_frequent_card.name) {
            y = _drawSectionLabel(ctx, W, y, '本周常遇之牌');
            y = _drawTopCard(ctx, W, y, weeklyData.most_frequent_card, cardImg);
          }
          y += Math.round(W * 0.012);

          // ── 7. AI summary ──
          const qrAreaY = H - Math.round(W * 0.26);
          if (weeklyData.ai_summary) {
            y = _drawSectionLabel(ctx, W, y, 'AI 周语');
            _drawAISummary(ctx, W, y, weeklyData.ai_summary, qrAreaY);
          }

          // ── 8. QR + footer ──
          _drawQRCode(ctx, W, qrAreaY, qrImg);
          _drawFooter(ctx, W, H - Math.round(W * 0.036));

          // Export
          wx.canvasToTempFilePath({
            canvas: canvas,
            success: (res2) => {
              this.setData({
                previewPath: res2.tempFilePath,
                isDrawing: false,
                drawError: false,
              });
            },
            fail: (err) => {
              console.error('[weekly-report-poster] Export error:', err);
              this.setData({ drawError: true, isDrawing: false });
            },
          }, this);
        };

        // Load card image
        if (cardImagePath) {
          const img = canvas.createImage();
          img.onload = () => {
            cardImg = img;
            cardImageLoaded = true;
            _tryDraw();
          };
          img.onerror = () => {
            // Card image failed — still draw with placeholder
            cardImageLoaded = true;
            _tryDraw();
          };
          img.src = cardImagePath;
        }

        // Load QR (mini-program code) from backend
        /* UX 修复: 痛点#3 — tabbar 页不能生成小程序码（微信返回 41030，静默降级成无码图）；
           改用非 tabbar 的 share-center 页（与已修复的 canvas-poster 对齐） */
        wx.downloadFile({
          url: BASE_URL + '/share/wxa-code?path=' + encodeURIComponent('pages/share-center/share-center') + '&width=280',
          success: (dlRes) => {
            if (dlRes.statusCode !== 200) {
              qrImageLoaded = true;
              _tryDraw();
              return;
            }
            const q = canvas.createImage();
            q.onload = () => {
              qrImg = q;
              qrImageLoaded = true;
              _tryDraw();
            };
            q.onerror = () => {
              qrImageLoaded = true;
              _tryDraw();
            };
            q.src = dlRes.tempFilePath;
          },
          fail: () => {
            qrImageLoaded = true;
            _tryDraw();
          },
        });

        // Safety timeout: if images haven't loaded in 5s, draw anyway
        setTimeout(() => {
          cardImageLoaded = true;
          qrImageLoaded = true;
          _tryDraw();
        }, 5000);
      });
    },

    /* ---------------------------------------------------------------
       Save poster to photo album
       --------------------------------------------------------------- */
    onSave() {
      const { previewPath } = this.data;
      if (!previewPath) return;

      wx.saveImageToPhotosAlbum({
        filePath: previewPath,
        success: () => {
          wx.showToast({ title: '已保存到相册', icon: 'success' });
        },
        fail: (err) => {
          if (err.errMsg && err.errMsg.indexOf('auth deny') !== -1) {
            wx.showModal({
              title: '需要相册权限',
              content: '请在设置中开启相册权限，以便保存周报长图到相册',
              confirmText: '去设置',
              success: (res) => {
                if (res.confirm) {
                  wx.openSetting();
                }
              },
            });
          } else {
            wx.showToast({ title: '保存失败，请重试', icon: 'none' });
          }
        },
      });
    },

    /* ---------------------------------------------------------------
       Share poster to friends — user-initiated only (no 诱导分享)
       --------------------------------------------------------------- */
    onShare() {
      const { previewPath } = this.data;
      if (!previewPath) return;
      this.triggerEvent('share', { imagePath: previewPath });
    },

    onClose() {
      this.triggerEvent('close');
    },

    onRetry() {
      this._drawPoster();
    },
  },
});
