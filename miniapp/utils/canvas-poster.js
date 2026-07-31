/**
 * Canvas poster drawing utility
 *
 * Generates a share poster for WeChat Moments / friends, including:
 *   - Decorative star particles
 *   - User nickname
 *   - Card image (rounded, with golden border)
 *   - Card name
 *   - Key insight excerpt from the AI interpretation
 *   - Real WeChat mini-program code (wxacode) from our backend
 *   - Brand footer
 *
 * Poster aspect ratio: 3:4 (optimal for Moments sharing)
 *
 * Canvas 2D API (type="2d")
 */

// ── Import BASE_URL from the API client ──────────────────────────────
const { BASE_URL } = require('./api');

// ── Configuration ────────────────────────────────────────────────────
const TARGET_ASPECT = 3 / 4;         // width / height → 3:4 portrait
const QR_SIZE_RATIO = 0.13;          // QR code as fraction of canvas width
const CARD_WIDTH_RATIO = 0.56;       // card image ~56% of canvas width
const CARD_ASPECT = 1.5;             // tarot card height / width

// ── Colour palette ───────────────────────────────────────────────────
const C_GOLD      = '#F4D48C';
const C_GOLD_MUTED = '#C4A46C';
const C_WHITE     = '#F0EDE8';
const C_MUTED     = '#B8A9E0';
const C_DARK      = '#1A1A3E';
const C_BG_TOP    = '#1A1A3E';
const C_BG_MID    = '#12122E';
const C_BG_BOT    = '#0B0B16';

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

/**
 * Draw the decorative star particles at the top of the poster.
 */
function _drawStars(ctx, W) {
  const starCount = 12;
  // Simple star is a small circle; positions are deterministic relative to W
  for (let i = 0; i < starCount; i++) {
    const x = (W / (starCount + 1)) * (i + 1) + (i % 3 - 1) * 6;
    const y = 6 + (i % 4) * 2;
    const r = 1.2 + (i % 3) * 0.3;
    ctx.save();
    ctx.fillStyle = i % 2 === 0 ? C_GOLD : C_MUTED;
    ctx.globalAlpha = 0.6 + (i % 3) * 0.15;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

/**
 * Draw the brand header and user nickname.
 * Returns the Y coordinate just below the header area.
 */
function _drawHeader(ctx, W, nickname) {
  let y = 14;

  // Brand header
  ctx.save();
  ctx.fillStyle = C_GOLD;
  ctx.font = `bold ${Math.round(W * 0.043)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('✦ 星光映照 ✦', W / 2, y);
  ctx.restore();

  // Decorative line under brand
  const lineW = Math.round(W * 0.3);
  const lineX = Math.round((W - lineW) / 2);
  const lineY = y + Math.round(W * 0.058);
  ctx.save();
  ctx.strokeStyle = C_GOLD;
  ctx.globalAlpha = 0.4;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(lineX, lineY);
  ctx.lineTo(lineX + lineW, lineY);
  ctx.stroke();
  ctx.restore();

  // Nickname
  if (nickname) {
    const nickY = lineY + 6;
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(nickname, W / 2, nickY);
    ctx.restore();
    return nickY + Math.round(W * 0.048);
  }

  return lineY + Math.round(W * 0.045);
}

/**
 * Draw the tarot card image with rounded corners and gold border.
 * Returns the Y coordinate of the bottom of the card image.
 */
function _drawCardImage(ctx, W, Y, imgElement) {
  const cardW = Math.round(W * CARD_WIDTH_RATIO);
  const cardH = Math.round(cardW * CARD_ASPECT);
  const cardX = Math.round((W - cardW) / 2);
  const r = Math.round(cardW * 0.018);

  // Draw card image (clipped to rounded rect)
  ctx.save();
  _roundRect(ctx, cardX, Y, cardW, cardH, r);
  ctx.clip();
  if (imgElement) {
    ctx.drawImage(imgElement, cardX, Y, cardW, cardH);
  } else {
    // Fallback placeholder fill
    ctx.fillStyle = '#252550';
    ctx.fillRect(cardX, Y, cardW, cardH);
  }
  ctx.restore();

  // Gold border
  ctx.save();
  _roundRect(ctx, cardX, Y, cardW, cardH, r);
  ctx.strokeStyle = C_GOLD;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.7;
  ctx.stroke();
  ctx.restore();

  return Y + cardH;
}

/**
 * Draw the card name below the image.
 * Returns the Y coordinate just below the card name.
 */
function _drawCardName(ctx, W, Y, cardName) {
  if (!cardName) return Y + 4;
  const nameY = Y + 6;
  ctx.save();
  ctx.fillStyle = C_GOLD;
  ctx.font = `bold ${Math.round(W * 0.043)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(cardName, W / 2, nameY);
  ctx.restore();
  return nameY + Math.round(W * 0.060);
}

/**
 * Draw the key insight excerpt.
 * Returns the Y coordinate just below the insight text block.
 */
function _drawKeyInsight(ctx, W, Y, insight) {
  if (!insight) return Y + 4;
  const maxW = Math.round(W * 0.78);
  const x = Math.round((W - maxW) / 2);
  const fontSize = Math.round(W * 0.032);
  const lineH = Math.round(fontSize * 1.6);

  ctx.save();
  ctx.fillStyle = C_WHITE;
  ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';

  const lines = _wrapText(ctx, insight, maxW);
  let textY = Y;
  for (let i = 0; i < Math.min(lines.length, 2); i++) {
    ctx.fillText(lines[i], x, textY);
    textY += lineH;
  }
  ctx.restore();

  return Y + Math.min(lines.length, 2) * lineH + 4;
}

/**
 * Draw the QR code image and its call-to-action.
 * Returns the Y coordinate just below the QR area.
 *
 * @param {string} [ctaText] - Optional call-to-action text (defaults to reading-mode copy)
 */
function _drawQRCode(ctx, W, Y, qrImg, ctaText) {
  const qrSize = Math.round(W * QR_SIZE_RATIO);
  const qrX = Math.round((W - qrSize) / 2);
  const gap = Math.round(W * 0.024);

  const qrAreaY = Y + gap;

  // Draw the QR code image (with rounded corners)
  ctx.save();
  _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
  ctx.clip();
  if (qrImg) {
    ctx.drawImage(qrImg, qrX, qrAreaY, qrSize, qrSize);
  } else {
    // Placeholder fallback — so the poster is never blank
    ctx.fillStyle = C_WHITE;
    ctx.fillRect(qrX, qrAreaY, qrSize, qrSize);
  }
  ctx.restore();

  // QR white border (always draw border, so placeholder looks intentional)
  ctx.save();
  _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();

  // Call-to-action text below QR code
  const ctaY = qrAreaY + qrSize + 4;
  ctx.save();
  ctx.fillStyle = C_MUTED;
  ctx.font = `${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(ctaText || '扫码探索你的命运', W / 2, ctaY);
  ctx.restore();

  return ctaY + Math.round(W * 0.042);
}

/**
 * Draw the brand footer.
 */
function _drawFooter(ctx, W, Y) {
  ctx.save();
  ctx.fillStyle = C_GOLD;
  ctx.globalAlpha = 0.6;
  ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('星光映照 · 塔罗占卜', W / 2, Y);
  ctx.restore();
}

/**
 * Draw the "daily card check-in" poster layout.
 *
 * Layout (3:4 portrait):
 *   - Top 60% of the canvas: today's card image (centered, rounded
 *     corners, golden border, soft gold glow)
 *   - Middle: card name + date + "连续第N天 ✦" (date only when no streak)
 *   - Bottom: mini-program code + brand footer
 *
 * Background is a dark indigo gradient #1A1A3E → #12122E.
 *
 * @param {Object} data - { cardImg, qrImg, cardName, dateText, streak }
 */
function _drawDailyLayout(ctx, W, H, data) {
  const { cardImg, qrImg, cardName, dateText, streak } = data;

  // ── Top 60%: card image, centered with gold border + soft glow ──
  const topAreaH = Math.round(H * 0.60);
  const cardW = Math.round(W * 0.52);
  const cardH = Math.round(cardW * CARD_ASPECT);
  const cardX = Math.round((W - cardW) / 2);
  const cardY = Math.round((topAreaH - cardH) / 2) + Math.round(W * 0.004); // keep glow fully inside
  const r = Math.round(cardW * 0.02);

  // Soft golden glow behind the card
  const glowPad = Math.round(W * 0.014);
  ctx.save();
  ctx.fillStyle = 'rgba(244, 212, 140, 0.10)';
  _roundRect(ctx, cardX - glowPad, cardY - glowPad, cardW + glowPad * 2, cardH + glowPad * 2, r + glowPad);
  ctx.fill();
  ctx.restore();

  // Card image (clipped to rounded rect) + gold border
  ctx.save();
  _roundRect(ctx, cardX, cardY, cardW, cardH, r);
  ctx.clip();
  if (cardImg) {
    ctx.drawImage(cardImg, cardX, cardY, cardW, cardH);
  } else {
    ctx.fillStyle = '#252550';
    ctx.fillRect(cardX, cardY, cardW, cardH);
  }
  ctx.restore();

  ctx.save();
  _roundRect(ctx, cardX, cardY, cardW, cardH, r);
  ctx.strokeStyle = C_GOLD;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.75;
  ctx.stroke();
  ctx.restore();

  // ── Middle: card name + date + streak ──
  let y = cardY + cardH + Math.round(W * 0.038);

  // Card name (gold, bold)
  ctx.save();
  ctx.fillStyle = C_GOLD;
  ctx.font = `bold ${Math.round(W * 0.046)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  if (cardName) {
    ctx.fillText(cardName, W / 2, y);
    y += Math.round(W * 0.064);
  }
  ctx.restore();

  // Date (lavender, subtle)
  if (dateText) {
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.globalAlpha = 0.85;
    ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(dateText, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.048);
  }

  // Streak line — "连续第N天 ✦" (only when 2+ consecutive days)
  if (streak >= 2) {
    ctx.save();
    ctx.fillStyle = C_GOLD;
    ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`连续第${streak}天 ✦`, W / 2, y);
    ctx.restore();
  }

  // ── Bottom: mini-program code + brand footer ──
  // Anchor the QR area so its CTA text clears the footer
  const qrAreaY = H - Math.round(W * 0.26);
  _drawQRCode(ctx, W, qrAreaY, qrImg, '扫码 · 每日一牌');
  _drawFooter(ctx, W, H - Math.round(W * 0.040));
}

// =====================================================================
//  Main entry — drawSharePoster
// =====================================================================

/**
 * Draw a share poster on a WeChat Canvas 2D element.
 *
 * @param {string}   canvasId          - Canvas element ID
 * @param {Object}   opts              - Options object
 * @param {Object}   opts.context      - Component/page `this` (for SelectorQuery)
 * @param {string}   opts.mode         - 'reading' (default) | 'daily'
 * @param {string}   opts.cardImagePath - Tarot card image URL
 * @param {string}   opts.cardName     - Card display name (e.g. "愚者 · The Fool")
 * @param {string}   opts.keyInsight   - Short excerpt from the interpretation
 * @param {string}   opts.nickname     - User's display name
 * @param {string}   opts.dateText     - Formatted date for daily mode (e.g. "2026.07.31")
 * @param {number}   opts.streak       - Consecutive draw days for daily mode
 * @param {Function} opts.onSuccess    - Callback (tempFilePath)
 * @param {Function} opts.onError      - Callback (Error)
 */
function drawSharePoster(canvasId, opts) {
  const { context, mode, cardImagePath, cardName, keyInsight, nickname, dateText, streak, onSuccess, onError } = opts || {};

  if (!context || !canvasId) {
    if (onError) onError(new Error('Missing required params: context / canvasId'));
    return;
  }

  const sysInfo = wx.getSystemInfoSync();
  const W = sysInfo.screenWidth || 375;
  const dpr = sysInfo.pixelRatio || 2;
  const H = Math.round(W / TARGET_ASPECT);   // 3:4 portrait

  const query = wx.createSelectorQuery().in(context);
  query.select('#' + canvasId).fields({ node: true, size: true }).exec(function (res) {
    if (!res || !res[0] || !res[0].node) {
      if (onError) onError(new Error('Canvas node not found'));
      return;
    }

    const canvas = res[0].node;
    const ctx = canvas.getContext('2d');

    // Set canvas buffer to physical pixels
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
    _drawStars(ctx, W);

    // ── 3. Header + nickname ──
    const headerBottom = _drawHeader(ctx, W, nickname);

    // ── 4. Load card image, QR code, then draw everything ──
    let cardImageLoaded = false;
    let qrImageLoaded = false;
    let cardImg = null;
    let qrImg = null;
    let drawAttempted = false;

    function _tryDraw() {
      if (drawAttempted) return;
      if (!cardImageLoaded || !qrImageLoaded) return;
      drawAttempted = true;

      if (mode === 'daily') {
        // ── Daily card check-in poster ──
        _drawDailyLayout(ctx, W, H, {
          cardImg: cardImg,
          qrImg: qrImg,
          cardName: cardName,
          dateText: dateText,
          streak: streak || 0,
        });
      } else {
        // ── Reading result poster ──
        // Card image
        const cardBottom = _drawCardImage(ctx, W, headerBottom, cardImg);

        // Card name
        const nameBottom = _drawCardName(ctx, W, cardBottom, cardName);

        // Key insight
        const insightBottom = _drawKeyInsight(ctx, W, nameBottom, keyInsight);

        // QR code (if loaded)
        const qrY = Math.min(insightBottom, H - Math.round(W * 0.22));
        _drawQRCode(ctx, W, qrY, qrImg);

        // Footer
        _drawFooter(ctx, W, H - Math.round(W * 0.040));
      }

      // Export
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

    // Load card image
    if (cardImagePath) {
      const img = canvas.createImage();
      img.onload = function () {
        cardImg = img;
        cardImageLoaded = true;
        _tryDraw();
      };
      img.onerror = function () {
        // Card image failed — still draw with placeholder
        cardImageLoaded = true;
        _tryDraw();
      };
      img.src = cardImagePath;
    } else {
      cardImageLoaded = true;
    }

    // Load QR code from backend
    // We use wx.downloadFile for broad domain compatibility
    const qrUrl = BASE_URL + '/share/wxa-code?path=' + encodeURIComponent('pages/index/index') + '&width=280';
    wx.downloadFile({
      url: qrUrl,
      success: function (dlRes) {
        if (dlRes.statusCode !== 200) {
          // QR download failed — proceed without it
          qrImageLoaded = true;
          _tryDraw();
          return;
        }
        const q = canvas.createImage();
        q.onload = function () {
          qrImg = q;
          qrImageLoaded = true;
          _tryDraw();
        };
        q.onerror = function () {
          qrImageLoaded = true;
          _tryDraw();
        };
        q.src = dlRes.tempFilePath;
      },
      fail: function () {
        // QR download failed — proceed without it
        qrImageLoaded = true;
        _tryDraw();
      },
    });

    // Safety timeout: if either image hasn't loaded in 5s, draw anyway
    setTimeout(function () {
      if (!cardImageLoaded) {
        cardImageLoaded = true;
      }
      if (!qrImageLoaded) {
        qrImageLoaded = true;
      }
      _tryDraw();
    }, 5000);
  });
}

// =====================================================================
//  Diary Card — generateDiaryCard
// =====================================================================

/**
 * Generate a share image card for a diary entry.
 *
 * Creates a temporary canvas, draws the diary content, and returns
 * the temp file path for preview/save.
 *
 * @param {Object} entry      - Diary entry object { date, mood, reflection, card, image_url }
 * @param {Object} pageContext - Page `this` for SelectorQuery
 * @returns {Promise<string>}  tempFilePath
 */
function generateDiaryCard(entry, pageContext) {
  return new Promise((resolve, reject) => {
    const sysInfo = wx.getSystemInfoSync();
    const W = sysInfo.screenWidth || 375;
    const dpr = sysInfo.pixelRatio || 2;
    const PADDING = Math.round(W * 0.06);
    const contentW = W - PADDING * 2;

    // Estimate height based on content
    let estimatedH = Math.round(W * 1.2); // base height
    if (entry.reflection) {
      const lines = Math.ceil(entry.reflection.length / 18);
      estimatedH += lines * 28;
    }
    if (entry.image_url) estimatedH += Math.round(W * 0.5);
    const H = Math.min(estimatedH, Math.round(W * 2.5));

    // Create canvas element
    const query = wx.createSelectorQuery().in(pageContext);
    query.select('#diary-share-canvas').fields({ node: true, size: true }).exec(function (res) {
      if (!res || !res[0] || !res[0].node) {
        // Fallback: try creating offscreen canvas
        try {
          const canvas = wx.createOffscreenCanvas({ type: '2d', width: Math.round(W * dpr), height: Math.round(H * dpr) });
          const ctx = canvas.getContext('2d');
          _drawDiaryCard(ctx, canvas, W, H, dpr, entry, resolve);
          return;
        } catch (e) {
          reject(new Error('Canvas not available'));
          return;
        }
      }

      const canvas = res[0].node;
      const ctx = canvas.getContext('2d');
      _drawDiaryCard(ctx, canvas, W, H, dpr, entry, resolve);
    });
  });
}

/**
 * Draw the diary card content on the given canvas context.
 */
function _drawDiaryCard(ctx, canvas, W, H, dpr, entry, resolve) {
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.scale(dpr, dpr);

  const PADDING = Math.round(W * 0.06);
  const contentW = W - PADDING * 2;
  let y = PADDING;

  // 1. Background
  const gradient = ctx.createLinearGradient(0, 0, 0, H);
  gradient.addColorStop(0, '#1A1A3E');
  gradient.addColorStop(0.5, '#12122E');
  gradient.addColorStop(1, '#0B0B16');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, W, H);

  // 2. Brand header
  ctx.save();
  ctx.fillStyle = '#F4D48C';
  ctx.font = `bold ${Math.round(W * 0.045)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('✦ 星光日记 ✦', W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.065);

  // 3. Date
  ctx.save();
  ctx.fillStyle = '#B8A9E0';
  ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(entry.date || '', W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.050);

  // 4. Mood emoji
  const MOOD_EMOJI_MAP = { happy: '😊', calm: '😌', excited: '🤩', anxious: '😰', sad: '😢', thoughtful: '🤔' };
  const moodEmoji = MOOD_EMOJI_MAP[entry.mood] || '🤔';
  ctx.save();
  ctx.font = `${Math.round(W * 0.080)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(moodEmoji, W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.090);

  // 5. Card name (if available)
  if (entry.card && entry.card.name_zh) {
    ctx.save();
    ctx.fillStyle = '#F4D48C';
    ctx.font = `${Math.round(W * 0.035)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`🃏 ${entry.card.name_zh}`, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.048);
  }

  // 6. Divider line
  y += Math.round(W * 0.020);
  const lineX = PADDING + Math.round(contentW * 0.15);
  const lineW = Math.round(contentW * 0.70);
  ctx.save();
  ctx.strokeStyle = 'rgba(244, 212, 140, 0.2)';
  ctx.lineWidth = 0.5;
  ctx.beginPath();
  ctx.moveTo(lineX, y);
  ctx.lineTo(lineX + lineW, y);
  ctx.stroke();
  ctx.restore();
  y += Math.round(W * 0.035);

  // 7. Reflection text
  if (entry.reflection) {
    // Label
    ctx.save();
    ctx.fillStyle = '#B8A9E0';
    ctx.font = `${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('今日感悟', PADDING, y);
    ctx.restore();
    y += Math.round(W * 0.040);

    // Text content — simple wrap
    const fontSize = Math.round(W * 0.032);
    const lineH = fontSize * 1.6;
    ctx.save();
    ctx.fillStyle = '#F0EDE8';
    ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';

    let text = entry.reflection;
    let line = '';
    let textY = y;
    for (const char of text) {
      const test = line + char;
      if (ctx.measureText(test).width > contentW && line.length > 0) {
        ctx.fillText(line, PADDING, textY);
        line = char;
        textY += lineH;
      } else {
        line = test;
      }
    }
    if (line) ctx.fillText(line, PADDING, textY);
    ctx.restore();
    y = textY + lineH + Math.round(W * 0.025);
  }

  // 8. Diary image (if url is a local path or remote URL)
  if (entry.image_url) {
    // We can't easily load images onto canvas from data URL/local paths here
    // So we skip canvas image rendering and just show a placeholder indicator
    ctx.save();
    ctx.fillStyle = 'rgba(244, 212, 140, 0.08)';
    ctx.strokeStyle = 'rgba(244, 212, 140, 0.15)';
    const imgH = Math.round(W * 0.35);
    const imgW = Math.round(contentW * 0.6);
    const imgX = Math.round((W - imgW) / 2);
    _roundRect(ctx, imgX, y, imgW, imgH, Math.round(W * 0.02));
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#B8A9E0';
    ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('📷', imgX + imgW / 2, y + imgH / 2);
    ctx.restore();
    y += imgH + Math.round(W * 0.030);
  }

  // 9. Footer
  y = Math.max(y, H - Math.round(W * 0.060));
  ctx.save();
  ctx.fillStyle = '#F4D48C';
  ctx.globalAlpha = 0.5;
  ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('星光映照 · 塔罗占卜', W / 2, y);
  ctx.restore();

  // Export
  wx.canvasToTempFilePath({
    canvas: canvas,
    success: function (res) {
      resolve(res.tempFilePath);
    },
    fail: function (err) {
      reject(err);
    },
  });
}

module.exports = { drawSharePoster, generateDiaryCard };
