// utils/journal-poster.js —— 月度星光手账海报（T1-5）
//
// 复用 canvas-poster.js 的 E3 调色板常量与绘制辅助（单一色彩/圆角/码位来源），
// 版式（3:4 竖版 · 奶油底）：
//   夜空标题（"八月 · 我的星光夜空"）
//   + 星阶徽章（金深 pill，空值省略——绝不降级印「微光」）
//   + 点亮天数 / 亮星 / 暗星 / 亮暗比例
//   + 月度星光夜空缩略（亮星/暗星分布星点 + 本月星空色带）
//   + AI 摘要（截断在二维码区之上）
//   + 小程序码（复用 /share/wxacode：scene=用户邀请码 → card-landing）
//   + 页脚「仅供娱乐 · 星光映照」
//
// 数据源：GET /journal/review/share-preview（脱敏：无昵称、无日记原文、
// 无 user_id），星阶徽章由页面从 /tasks/status 单独取（用户本人设备）。

const { BASE_URL } = require('./api');
const { PALETTE, DRAW_HELPERS, LAYOUT } = require('./canvas-poster');

const {
  C_GOLD,
  C_GOLD_INK,
  C_WHITE,
  C_MUTED,
  C_BG_TOP,
  C_BG_MID,
  C_BG_BOT,
  C_GLOW,
} = PALETTE;

const {
  roundRect,
  wrapText,
  drawStars,
  drawHeader,
  drawQRCode,
  drawFooter,
  toArray,
} = DRAW_HELPERS;

const FONT = '"PingFang SC", "Helvetica Neue", sans-serif';

/** 亮星/暗星分布 + 本月星空色带（月度星光夜空缩略面板），返回面板底部 Y。 */
function _drawNightSky(ctx, W, y, recorded, bright, dim, starColorCounts) {
  const panelX = Math.round(W * 0.10);
  const panelW = Math.round(W * 0.80);
  const radius = 10;
  const dotRowH = Math.round(W * 0.10);
  const bandH = Math.round(W * 0.055);
  const bandGap = Math.round(W * 0.020);
  const labelPad = Math.round(W * 0.030);
  const panelH = dotRowH + bandGap + bandH + labelPad;

  // 面板底（奶油白）+ 细金描边
  ctx.save();
  roundRect(ctx, panelX, y, panelW, panelH, radius);
  ctx.fillStyle = 'rgba(255, 253, 248, 0.85)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(201, 169, 124, 0.45)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();

  const innerX = panelX + Math.round(W * 0.045);
  const innerW = panelW - Math.round(W * 0.090);

  // 亮星/暗星分布：确定位置铺开（亮=金+细光晕，暗=深灰紫半透明，不评判）
  const maxDots = Math.min(recorded, 31);
  const step = maxDots > 0 ? innerW / maxDots : innerW;
  const dotR = Math.round(W * 0.009);
  ctx.save();
  for (let i = 0; i < maxDots; i++) {
    const isBright = i < bright;
    const dx = innerX + step * i + step / 2;
    const dy = y + dotRowH / 2;
    if (isBright) {
      ctx.fillStyle = C_GLOW;
      ctx.beginPath();
      ctx.arc(dx, dy, dotR * 2.1, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = isBright ? C_GOLD : C_MUTED;
    ctx.globalAlpha = isBright ? 0.95 : 0.55;
    ctx.beginPath();
    ctx.arc(dx, dy, isBright ? dotR : Math.round(dotR * 0.72), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();

  // 本月星空色带：星光色统计按次数占比铺段（圆头段，最多 8 色）
  const bandY = y + dotRowH + bandGap;
  const counts = toArray(starColorCounts).filter((c) => c && c.color);
  if (counts.length > 0) {
    const total = counts.reduce((s, c) => s + (Number(c.count) || 0), 0) || 1;
    const segGap = 2;
    const availW = innerW - segGap * (counts.length - 1);
    let sx = innerX;
    ctx.save();
    for (const seg of counts) {
      const segW = Math.max(Math.round(availW * ((Number(seg.count) || 0) / total)) - segGap, 6);
      roundRect(ctx, sx, bandY, segW, bandH, bandH / 2);
      ctx.fillStyle = seg.color || C_GOLD;
      ctx.globalAlpha = 0.92;
      ctx.fill();
      sx += segW + segGap;
    }
    ctx.restore();

    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.globalAlpha = 0.9;
    ctx.font = `${Math.round(W * 0.022)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('本月星空色带', W / 2, bandY + bandH + Math.round(W * 0.008));
    ctx.restore();
  }

  return y + panelH;
}

/**
 * 生成月度星光手账海报（3:4 竖版 · E3 奶油底）。
 *
 * @param {Object} opts - {
 *   monthLabel: '八月',                       // 夜空标题前缀
 *   stats: {days_recorded, bright_count, dim_count, bright_ratio},
 *   starColorCounts: [{color, count}],        // 本月星空色带
 *   summary: 'AI/降级 复盘摘要（一句话）',
 *   starTierName: '星光',                     // 星阶徽章（空串省略）
 *   onSuccess(tempFilePath), onError(err)
 * }
 */
function drawJournalPoster(canvasId, pageContext, opts) {
  const {
    monthLabel,
    stats,
    starColorCounts,
    summary,
    starTierName,
    onSuccess,
    onError,
  } = opts || {};

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

    // 画布缓冲 = 物理像素；逻辑坐标按 dpr 缩放
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.scale(dpr, dpr);

    // 1. 背景奶油渐变 + 装饰星点
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, C_BG_TOP);
    gradient.addColorStop(0.5, C_BG_MID);
    gradient.addColorStop(1, C_BG_BOT);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
    drawStars(ctx, W);

    // 2. 品牌头（匿名海报：不带昵称，与 share-preview 脱敏口径一致）
    let y = drawHeader(ctx, W, '');
    y += Math.round(W * 0.030);

    // 3. 夜空标题
    const title = monthLabel ? `${monthLabel} · 我的星光夜空` : '我的星光夜空';
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.042)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(title, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.060);

    // 4. 星阶徽章（空值省略——绝不降级印「微光」，与星光名片海报 F-3 一致）
    const hasTier = typeof starTierName === 'string' && starTierName.trim().length > 0;
    if (hasTier) {
      const chipH = Math.round(W * 0.062);
      ctx.save();
      ctx.font = `bold ${Math.round(W * 0.028)}px ${FONT}`;
      const chipText = `✦ ${starTierName} · 星阶`;
      const chipW = ctx.measureText(chipText).width + Math.round(W * 0.056);
      const chipX = Math.round((W - chipW) / 2);
      roundRect(ctx, chipX, y, chipW, chipH, chipH / 2);
      ctx.fillStyle = 'rgba(255, 253, 248, 0.92)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(201, 169, 124, 0.55)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = C_GOLD_INK;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(chipText, chipX + chipW / 2, y + chipH / 2 + 1);
      ctx.restore();
      y += chipH + Math.round(W * 0.024);
    }

    // 5. 点亮天数 / 亮暗比例
    const d = stats || {};
    const recorded = Number(d.days_recorded) || 0;
    const bright = Number(d.bright_count) || 0;
    const dim = Number(d.dim_count) || 0;
    const ratio = Math.round((Number(d.bright_ratio) || 0) * 100);
    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `bold ${Math.round(W * 0.031)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`点亮 ${recorded} 天 · 亮星 ${bright} · 暗星 ${dim}`, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.050);
    if (recorded > 0) {
      ctx.save();
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.027)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(`${ratio}% 的夜晚，星光满溢或明亮`, W / 2, y);
      ctx.restore();
      y += Math.round(W * 0.046);
    }

    // 6. 月度星光夜空缩略（亮星/暗星分布 + 本月星空色带）
    if (recorded > 0) {
      y = _drawNightSky(ctx, W, y, recorded, bright, dim, starColorCounts);
      y += Math.round(W * 0.030);
    }

    // 7. AI 摘要（换行，截断在二维码区之上，最多 5 行）
    if (summary) {
      const qrZoneY = H - Math.round(W * 0.26);
      const maxW = Math.round(W * 0.78);
      const x = Math.round((W - maxW) / 2);
      const fontSize = Math.round(W * 0.031);
      const lineH = Math.round(fontSize * 1.6);
      const available = qrZoneY - y - Math.round(W * 0.014);
      const maxLines = Math.max(1, Math.min(5, Math.floor(available / lineH)));
      ctx.save();
      ctx.fillStyle = C_WHITE;
      ctx.font = `${fontSize}px ${FONT}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      const lines = wrapText(ctx, summary, maxW);
      let ty = y;
      for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
        ctx.fillText(lines[i], x, ty);
        ty += lineH;
      }
      ctx.restore();
    }

    // 8. 小程序码（/share/wxacode · 登录态）+ 页脚「仅供娱乐 · 星光映照」
    const qrZoneY = H - Math.round(W * 0.26);
    let qrImg = null;
    let qrImageLoaded = false;
    let drawAttempted = false;

    function _tryFinish() {
      if (drawAttempted) return;
      if (!qrImageLoaded) return;
      drawAttempted = true;
      drawQRCode(ctx, W, qrZoneY, qrImg, '扫码 · 写下你的星光日记');
      drawFooter(ctx, W, H - Math.round(W * 0.040), '仅供娱乐 · 星光映照');
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

    // 名片码：scene=用户邀请码 → card-landing，需要登录 token（复用 /share/wxacode）
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

module.exports = { drawJournalPoster };
