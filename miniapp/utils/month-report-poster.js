// utils/month-report-poster.js —— 月报封面海报（SDD P2 · T7-6）
//
// 复用 canvas-poster.js 的 E3 调色板常量与绘制辅助（单一色彩/圆角/码位来源），
// 数据源 GET /report/month/poster（脱敏：报告期 + 3 核心数字 + AI 寄语一句
// + 星阶名；无昵称无原文统计明细）。
//
// 版式（3:4 竖版 · 奶油底 · 星空卷轴标题）：
//   ✦ 品牌头（匿名）
//   + 标题「八月 · 星光月度卷轴」
//   + 星阶徽章 pill（空值省略——绝不降级印「微光」，与星光名片海报 F-3 一致）
//   + 3 核心数字（点亮天数 / 解读次数 / 本月星尘）
//   + AI 寄语一句（换行，截断在二维码区之上）
//   + 小程序码（复用 /share/wxacode：scene=用户邀请码 → card-landing）
//   + 页脚「仅供娱乐 · 星光映照」

const { BASE_URL } = require('./api');
const { PALETTE, DRAW_HELPERS, LAYOUT } = require('./canvas-poster');

const {
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
} = DRAW_HELPERS;

const FONT = '"PingFang SC", "Helvetica Neue", sans-serif';

/**
 * 生成月报封面海报（3:4 竖版 · E3 奶油底）。
 *
 * @param {Object} opts - {
 *   periodLabel: '八月',                    // 标题前缀（页面按 period 计算）
 *   tierName: '星光',                       // 星阶徽章（空串省略）
 *   coreNumbers: {active_days, readings_count, stardust_estimated},
 *   aiSentence: 'AI 月度总评一句（≤40 字）',
 *   onSuccess(tempFilePath), onError(err)
 * }
 */
function drawMonthReportPoster(canvasId, pageContext, opts) {
  const {
    periodLabel,
    tierName,
    coreNumbers,
    aiSentence,
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

    // 2. 品牌头（匿名海报：不带昵称，与 poster 脱敏口径一致）
    let y = drawHeader(ctx, W, '');
    y += Math.round(W * 0.030);

    // 3. 星空卷轴标题（「八月 · 星光月度卷轴」）
    const title = periodLabel ? `${periodLabel} · 星光月度卷轴` : '星光月度卷轴';
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.042)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(title, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.062);

    // 4. 星阶徽章（空值省略——绝不降级印「微光」）
    const hasTier = typeof tierName === 'string' && tierName.trim().length > 0;
    if (hasTier) {
      const chipH = Math.round(W * 0.062);
      ctx.save();
      ctx.font = `bold ${Math.round(W * 0.028)}px ${FONT}`;
      const chipText = `✦ ${tierName} · 星阶`;
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
      y += chipH + Math.round(W * 0.030);
    }

    // 5. 3 核心数字（点亮天数 / 解读次数 / 本月星尘）
    const nums = coreNumbers || {};
    const activeDays = Number(nums.active_days) || 0;
    const readingsCount = Number(nums.readings_count) || 0;
    const stardust = Number(nums.stardust_estimated) || 0;

    const numItems = [
      { value: activeDays, label: '点亮天数' },
      { value: readingsCount, label: '解读次数' },
      { value: stardust, label: '本月星尘' },
    ];
    const colW = Math.round(W / 3);
    const numFont = Math.round(W * 0.058);
    const labelFont = Math.round(W * 0.024);

    numItems.forEach((item, i) => {
      const cx = colW * i + colW / 2;
      // 数字（金深 bold）
      ctx.save();
      ctx.fillStyle = C_GOLD_INK;
      ctx.font = `bold ${numFont}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(String(item.value), cx, y);
      ctx.restore();
      // 标签（深灰紫）
      ctx.save();
      ctx.fillStyle = C_MUTED;
      ctx.font = `${labelFont}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(item.label, cx, y + Math.round(W * 0.076));
      ctx.restore();
    });
    y += Math.round(W * 0.128);

    // 6. 分隔细金线
    y += Math.round(W * 0.012);
    const lineX = Math.round(W * 0.20);
    const lineW = Math.round(W * 0.60);
    ctx.save();
    ctx.strokeStyle = 'rgba(201, 169, 124, 0.45)';
    ctx.globalAlpha = 0.6;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(lineX, y);
    ctx.lineTo(lineX + lineW, y);
    ctx.stroke();
    ctx.restore();
    y += Math.round(W * 0.040);

    // 7. AI 寄语一句（换行，截断在二维码区之上，最多 5 行）
    if (aiSentence) {
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
      const lines = wrapText(ctx, aiSentence, maxW);
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
      drawQRCode(ctx, W, qrZoneY, qrImg, '扫码 · 查看我的星象月报');
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

module.exports = { drawMonthReportPoster };
