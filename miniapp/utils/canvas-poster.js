/**
 * Canvas 海报绘制工具
 * 生成包含牌面图片、解读精华、小程序码的分享海报
 * 基于 WeChat Canvas 2D API (type="2d")
 */

/**
 * 绘制圆角矩形路径
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} x
 * @param {number} y
 * @param {number} w
 * @param {number} h
 * @param {number} r - 圆角半径 (px)
 */
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

/**
 * 自动换行：将长文本按指定宽度分割为多行
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} text
 * @param {number} maxWidth - 最大行宽 (px)
 * @returns {string[]} 行数组
 */
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

/**
 * 绘制解读语录区块
 */
function _drawQuoteSection(ctx, W, H, nameBottomY, cardName, quote, cardW) {
  const quoteMarginTop = 24;
  const quoteY = nameBottomY + quoteMarginTop + 16;
  const quoteCardW = Math.round(W * 0.84);
  const quoteCardX = Math.round((W - quoteCardW) / 2);
  const quotePadding = 20;
  const quoteInnerW = quoteCardW - quotePadding * 2;
  const quoteFontSize = Math.round(W * 0.037);   // ≈ 28rpx
  const quoteLineHeight = Math.round(quoteFontSize * 1.8);
  const quoteMarkSize = Math.round(W * 0.064);    // ≈ 48rpx

  // Measure quote text lines
  ctx.font = `${quoteFontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  const quoteLines = quote ? _wrapText(ctx, quote, quoteInnerW) : [''];

  // Quote card height: opening mark + lines + closing mark + padding
  const quoteContentH = quoteLines.length * quoteLineHeight + quoteMarkSize + 8;
  const quoteCardH = quotePadding * 2 + quoteContentH;

  // Semi-transparent white card background
  ctx.save();
  _roundRect(ctx, quoteCardX, quoteY, quoteCardW, quoteCardH, 8);
  ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.fill();
  ctx.restore();

  // Opening quote mark
  ctx.save();
  ctx.fillStyle = '#F4D48C';
  ctx.font = `${quoteMarkSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('❝', quoteCardX + quotePadding, quoteY + quotePadding);
  ctx.restore();

  // Quote text
  ctx.save();
  ctx.fillStyle = '#F0EDE8';
  ctx.font = `${quoteFontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  let lineY = quoteY + quotePadding + quoteMarkSize + 4;
  for (const line of quoteLines) {
    ctx.fillText(line, quoteCardX + quotePadding, lineY);
    lineY += quoteLineHeight;
  }
  ctx.restore();

  // Closing quote mark
  const closeQuoteY = lineY - quoteLineHeight + 4;
  ctx.save();
  ctx.fillStyle = '#F4D48C';
  ctx.font = `${quoteMarkSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  ctx.fillText('❞', quoteCardX + quoteCardW - quotePadding, closeQuoteY + quoteMarkSize);
  ctx.restore();

  return quoteY + quoteCardH; // return bottom of quote section
}

/**
 * 绘制底部分享区域
 */
function _drawBottomSection(ctx, W, H, spreadType) {
  const bottomY = H - 100;

  // "星光映照 · {spreadType}" — 品牌标识
  ctx.save();
  ctx.fillStyle = '#F4D48C';
  ctx.font = `${Math.round(W * 0.037)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const brandText = '星光映照 · ' + (spreadType || '三牌占卜');
  ctx.fillText(brandText, W / 2, bottomY);
  ctx.restore();

  // Subtitle — 引导文字
  const subtitleY = bottomY + Math.round(W * 0.048);
  ctx.save();
  ctx.fillStyle = '#B8A9E0';
  ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('扫描小程序码，探索你的命运', W / 2, subtitleY);
  ctx.restore();

  // QR code placeholder — white rounded square
  const qrSize = Math.round(W * 0.16);   // ≈ 120rpx
  const qrX = Math.round((W - qrSize) / 2);
  const qrY = subtitleY + Math.round(W * 0.048) + 4;

  ctx.save();
  _roundRect(ctx, qrX, qrY, qrSize, qrSize, 10);
  ctx.fillStyle = '#FFFFFF';
  ctx.fill();
  ctx.restore();

  // QR placeholder text
  ctx.save();
  ctx.fillStyle = '#1A1A3E';
  ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('小程序码', W / 2, qrY + qrSize / 2);
  ctx.restore();
}

/**
 * 绘制分享海报
 *
 * 在指定 Canvas 上完整绘制海报，绘制完成后通过 onSuccess 返回临时文件路径。
 *
 * @param {string} canvasId - Canvas 元素 ID
 * @param {Object} options
 * @param {Object}   options.context       - 组件或页面的 this 引用（用于 SelectorQuery）
 * @param {string}   options.cardImagePath - 牌面图片 URL
 * @param {string}   options.cardName      - 牌名（含中英文），如 "愚者 · The Fool"
 * @param {string}   options.quote         - 解读精华（建议 120 字内）
 * @param {string}   options.spreadType    - 占卜类型，如 "三牌占卜"
 * @param {Function} options.onSuccess     - 绘制成功回调，参数为 (tempFilePath)
 * @param {Function} options.onError       - 绘制失败回调，参数为 (Error)
 */
function drawSharePoster(canvasId, options) {
  const { context, cardImagePath, cardName, quote, spreadType, onSuccess, onError } = options || {};

  if (!context || !canvasId) {
    if (onError) onError(new Error('缺少必要参数: context / canvasId'));
    return;
  }

  const sysInfo = wx.getSystemInfoSync();
  const W = sysInfo.screenWidth || 375;
  const dpr = sysInfo.pixelRatio || 2;
  const H = Math.round(W * (1334 / 750));

  const query = wx.createSelectorQuery().in(context);
  query.select('#' + canvasId).fields({ node: true, size: true }).exec(function (res) {
    if (!res || !res[0] || !res[0].node) {
      if (onError) onError(new Error('Canvas 节点未找到'));
      return;
    }

    const canvas = res[0].node;
    const ctx = canvas.getContext('2d');

    // Set canvas buffer size to physical pixels
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.scale(dpr, dpr);

    // ---- 1. Background: deep indigo gradient ----
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, '#1A1A3E');
    gradient.addColorStop(0.5, '#12122E');
    gradient.addColorStop(1, '#0B0B16');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);

    // ---- 2. Card image ----
    const cardW = Math.round(W * 0.8);      // ≈ 600rpx
    const cardH = Math.round(cardW * 1.5);   // ≈ 900rpx
    const cardX = Math.round((W - cardW) / 2);
    const cardY = Math.round(H * 0.05);      // top margin ≈ 5%
    const borderRadius = Math.round(cardW * 0.015);  // ≈ 10rpx

    function drawCardImage(imgElement) {
      // Clip + draw image with rounded corners
      ctx.save();
      _roundRect(ctx, cardX, cardY, cardW, cardH, borderRadius);
      ctx.clip();
      if (imgElement) {
        ctx.drawImage(imgElement, cardX, cardY, cardW, cardH);
      } else {
        // Fallback: colored rectangle
        ctx.fillStyle = '#252550';
        ctx.fill();
      }
      ctx.restore();

      // Golden border
      ctx.save();
      _roundRect(ctx, cardX, cardY, cardW, cardH, borderRadius);
      ctx.strokeStyle = '#F4D48C';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();
    }

    function drawRemaining() {
      // ---- 3. Card name below image ----
      const nameY = cardY + cardH + Math.round(H * 0.022);
      ctx.save();
      ctx.fillStyle = '#F4D48C';
      ctx.font = `bold ${Math.round(W * 0.048)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(cardName || '', W / 2, nameY);
      ctx.restore();

      // ---- 4. Quote section ----
      const nameBottomY = nameY + Math.round(W * 0.048);
      const quoteBottomY = _drawQuoteSection(ctx, W, H, nameBottomY, cardName, quote, cardW);

      // ---- 5. Bottom area ----
      _drawBottomSection(ctx, W, H, spreadType);

      // ---- Export ----
      wx.canvasToTempFilePath({
        canvas: canvas,
        success: function (res2) {
          if (onSuccess) onSuccess(res2.tempFilePath);
        },
        fail: function (err) {
          if (onError) onError(err);
        },
      }, context);
    }

    // Load card image then draw everything
    if (cardImagePath) {
      const img = canvas.createImage();
      img.onload = function () {
        drawCardImage(img);
        drawRemaining();
      };
      img.onerror = function () {
        // Image failed — draw placeholder
        drawCardImage(null);
        drawRemaining();
      };
      img.src = cardImagePath;
    } else {
      // No image path — draw placeholder
      drawCardImage(null);
      drawRemaining();
    }
  });
}

module.exports = { drawSharePoster };
