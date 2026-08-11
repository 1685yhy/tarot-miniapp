// utils/moon-card-poster.js —— 月光卡晚安卡海报（T4-5 完整版）
//
// 版式（3:4 竖版 · 深空底「晚安版星光名片」，设计 4.2）：
//   深空底（深紫罗兰夜空渐变 + 星点）+ 品牌头（✦ 星光映照 ✦ 金线）
//   + 日期行（"2026年8月11日 · 晚安"）
//   + 当夜月相（大 emoji + 金色柔光晕，星光色叠加光晕）
//   + 月相名（phase.label）
//   + 星语（换行居中，截断在二维码区之上，最多 4 行）
//   + 星光色描边小卡（描边 = 今日星光色，内文 "星光色 #XXXX · 星光数 N"）
//   + 小程序码（复用 /share/wxacode：scene=邀请码 → card-landing）+ CTA
//   + 页脚「仅供娱乐 · 星光映照」
//
// 数据源：GET /moon-card/today（页面已取，仅透传绘制）。
// 与 journal-poster.js 同构：复用 canvas-poster.js 的结构辅助
// （roundRect/wrapText/drawStars/drawQRCode），色彩为深空专属调色板。

const { BASE_URL } = require('./api');
const { DRAW_HELPERS, LAYOUT } = require('./canvas-poster');

const { roundRect, wrapText, drawStars, drawQRCode } = DRAW_HELPERS;

// ── 深空调色板（晚安版星光名片 · 深紫罗兰夜空 + 金色月光） ──
const N_BG_TOP = '#241A3E';   // 夜空上（月晕处稍亮）
const N_BG_MID = '#1A1230';
const N_BG_BOT = '#150F28';   // 夜空底（深）
const N_GOLD = '#F5D48F';     // 金色月光（标题/品牌，深底上亮金）
const N_GOLD_DEEP = '#D9AF6B';
const N_CREAM = '#F3ECFF';    // 正文（深底上的暖白）
const N_MUTED = '#A89FC9';    // 二级文字（灰紫）
const N_GLOW = 'rgba(245, 212, 143, 0.22)'; // 金色柔光晕
const N_LINE = 'rgba(245, 212, 143, 0.55)'; // 细金线（深底）

const FONT = '"PingFang SC", "Helvetica Neue", sans-serif';

/**
 * 生成月光卡晚安卡海报（3:4 竖版 · 深空底）。
 *
 * @param {string} canvasId - Canvas 节点 id
 * @param {Object} pageContext - 页面 this（SelectorQuery 作用域）
 * @param {Object} opts - {
 *   dateText: '2026年8月11日 · 晚安',        // 日期行（页面预格式化）
 *   card: {date, phase:{emoji,label}, phrase, star_color, star_number, source},
 *   onSuccess(tempFilePath), onError(err)
 * }
 */
function drawMoonCardPoster(canvasId, pageContext, opts) {
  const { dateText, card, onSuccess, onError } = opts || {};

  if (!pageContext || !canvasId) {
    if (onError) onError(new Error('Missing required params: context / canvasId'));
    return;
  }

  const sysInfo = wx.getSystemInfoSync();
  const W = sysInfo.screenWidth || 375;
  const dpr = sysInfo.pixelRatio || 2;
  const H = Math.round(W / LAYOUT.TARGET_ASPECT);

  const query = wx.createSelectorQuery().in(pageContext);
  query.select('#' + canvasId).fields({ node: true, size: true }).exec(function (res) {
    if (!res || !res[0] || !res[0].node) {
      if (onError) onError(new Error('Canvas node not found'));
      return;
    }

    const canvas = res[0].node;
    const ctx = canvas.getContext('2d');

    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.scale(dpr, dpr);

    // ── 1. 深空底渐变 + 星点 ──
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, N_BG_TOP);
    gradient.addColorStop(0.5, N_BG_MID);
    gradient.addColorStop(1, N_BG_BOT);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
    drawStars(ctx, W);

    // ── 2. 品牌头（深底亮金） ──
    let y = Math.round(W * 0.055);
    ctx.save();
    ctx.fillStyle = N_GOLD;
    ctx.font = `bold ${Math.round(W * 0.043)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('✦ 星光映照 ✦', W / 2, y);
    ctx.restore();

    const lineW = Math.round(W * 0.30);
    const lineX = Math.round((W - lineW) / 2);
    const lineY = y + Math.round(W * 0.058);
    ctx.save();
    ctx.strokeStyle = N_LINE;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(lineX, lineY);
    ctx.lineTo(lineX + lineW, lineY);
    ctx.stroke();
    ctx.restore();
    y = lineY + Math.round(W * 0.030);

    // ── 3. 日期行（灰紫） ──
    if (dateText) {
      ctx.save();
      ctx.fillStyle = N_MUTED;
      ctx.font = `${Math.round(W * 0.029)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(dateText, W / 2, y);
      ctx.restore();
      y += Math.round(W * 0.050);
    }

    // ── 4. 当夜月相（大 emoji + 金晕 + 星光色叠加晕） ──
    const phase = (card && card.phase) || {};
    const emoji = phase.emoji || '🌙';
    const starColor = (card && card.star_color) || N_GOLD;

    const emojiSize = Math.round(W * 0.175);
    const emojiY = y + Math.round(W * 0.008);
    const emojiX = W / 2;

    // 金色柔光晕（大）+ 星光色光晕（小，叠加）
    const haloR = Math.round(emojiSize * 1.05);
    let halo = ctx.createRadialGradient(emojiX, emojiY + emojiSize / 2, 4, emojiX, emojiY + emojiSize / 2, haloR);
    halo.addColorStop(0, N_GLOW);
    halo.addColorStop(1, 'rgba(245, 212, 143, 0)');
    ctx.save();
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(emojiX, emojiY + emojiSize / 2, haloR, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    try {
      // 星光色光晕（半透明叠加）
      const halo2R = Math.round(haloR * 0.72);
      const rgba = hexToRgba(starColor, 0.16);
      if (rgba) {
        let halo2 = ctx.createRadialGradient(emojiX, emojiY + emojiSize / 2, 4, emojiX, emojiY + emojiSize / 2, halo2R);
        halo2.addColorStop(0, rgba);
        halo2.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.save();
        ctx.fillStyle = halo2;
        ctx.beginPath();
        ctx.arc(emojiX, emojiY + emojiSize / 2, halo2R, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    } catch (e) {
      // 非法色值 → 跳过叠加晕（不影响成图）
    }

    ctx.save();
    ctx.font = `${emojiSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(emoji, emojiX, emojiY);
    ctx.restore();
    y = emojiY + emojiSize + Math.round(W * 0.018);

    // 月相名
    if (phase.label) {
      ctx.save();
      ctx.fillStyle = N_GOLD;
      ctx.font = `${Math.round(W * 0.027)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(phase.label, W / 2, y);
      ctx.restore();
      y += Math.round(W * 0.050);
    }

    // ── 5. 星语（居中换行，截断在星光色小卡之上，最多 4 行） ──
    const phrase = (card && card.phrase) || '';
    if (phrase) {
      const maxW = Math.round(W * 0.76);
      const x = Math.round((W - maxW) / 2);
      const fontSize = Math.round(W * 0.036);
      const lineH = Math.round(fontSize * 1.7);
      // 星光色小卡高度 + 码区预留
      const chipZoneY = H - Math.round(W * 0.42);
      const available = chipZoneY - y - Math.round(W * 0.012);
      const maxLines = Math.max(1, Math.min(4, Math.floor(available / lineH)));

      ctx.save();
      ctx.fillStyle = N_CREAM;
      ctx.font = `${fontSize}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      const lines = wrapText(ctx, phrase, maxW);
      let ty = y;
      for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
        ctx.fillText(lines[i], W / 2, ty);
        ty += lineH;
      }
      ctx.restore();
      y = ty + Math.round(W * 0.020);
    }

    // ── 6. 星光色描边小卡（描边 = 今日星光色） ──
    const chipH = Math.round(W * 0.086);
    const chipText = `星光色 ${starColor} · 星光数 ${card && card.star_number != null ? card.star_number : 0}`;
    ctx.save();
    ctx.font = `${Math.round(W * 0.026)}px ${FONT}`;
    const chipW = ctx.measureText(chipText).width + Math.round(W * 0.064);
    const chipX = Math.round((W - chipW) / 2);
    roundRect(ctx, chipX, y, chipW, chipH, chipH / 2);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.fill();
    // 星光色描边（今日星光色 0.85 不透明）
    ctx.strokeStyle = starColor;
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillStyle = N_CREAM;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(chipText, chipX + chipW / 2, y + chipH / 2 + 1);
    ctx.restore();

    // ── 7. 小程序码（复用 /share/wxacode，登录态）+ 页脚 ──
    const qrZoneY = H - Math.round(W * 0.245);
    let qrImg = null;
    let qrImageLoaded = false;
    let drawAttempted = false;

    function _tryFinish() {
      if (drawAttempted) return;
      if (!qrImageLoaded) return;
      drawAttempted = true;
      // 深空底上用浅色 CTA（N_MUTED 系亮紫，dark bg 对比度达标）
      drawQRCode(ctx, W, qrZoneY, qrImg, '扫码收下你的晚安卡 ✦', undefined, '#B8ACD9');
      // 页脚（深底亮金）
      ctx.save();
      ctx.fillStyle = N_GOLD;
      ctx.globalAlpha = 0.85;
      ctx.font = `${Math.round(W * 0.028)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('仅供娱乐 · 星光映照', W / 2, H - Math.round(W * 0.040));
      ctx.restore();
      wx.canvasToTempFilePath({
        canvas: canvas,
        success: function (res2) {
          if (onSuccess) onSuccess(res2.tempFilePath);
        },
        fail: function (err) {
          if (onError) onError(err);
        },
      }, pageContext);
    }

    // 名片码：scene=用户邀请码 → card-landing，需登录 token（复用 /share/wxacode）
    const token = wx.getStorageSync('token');
    wx.downloadFile({
      url: BASE_URL + '/share/wxacode',
      header: token ? { Authorization: 'Bearer ' + token } : {},
      success: function (dlRes) {
        if (dlRes.statusCode !== 200) {
          // 码拉取失败：海报仍可生成（无码版式），不阻塞保存/分享
          qrImageLoaded = true;
          _tryFinish();
          return;
        }
        const q = canvas.createImage();
        q.onload = function () {
          qrImg = q;
          qrImageLoaded = true;
          _tryFinish();
        };
        q.onerror = function () {
          qrImageLoaded = true;
          _tryFinish();
        };
        q.src = dlRes.tempFilePath;
      },
      fail: function () {
        qrImageLoaded = true;
        _tryFinish();
      },
    });

    // 安全超时：码 5 秒未就绪也照常成图
    setTimeout(function () {
      qrImageLoaded = true;
      _tryFinish();
    }, 5000);
  });
}

/** '#RRGGBB' → 'rgba(r,g,b,a)'（非法输入返回 null） */
function hexToRgba(hex, alpha) {
  if (typeof hex !== 'string') return null;
  let h = hex.trim();
  if (h[0] === '#') h = h.slice(1);
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

module.exports = { drawMoonCardPoster };
