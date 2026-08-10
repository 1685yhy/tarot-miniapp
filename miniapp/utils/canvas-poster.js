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

// ── Colour palette · E3 奶油疗愈明亮主题 ──────────────────────────────
// 奶油底 #FAF6EF→#F2ECDF 渐变 · 墨字 #3D3A36 · 深金字 #8A6B3D (≈4.6:1)
// 细金 #C9A97C 仅作装饰（描边/光点） · 三级文字 #6E6A96 (≈4.68:1)
const C_GOLD      = '#C9A97C';   // 细金 — decorative (borders / star dots)
const C_GOLD_MUTED = '#A98B5F';  // 深金 — decorative
const C_GOLD_INK  = '#8A6B3D';   // 金深 — title / label text on cream (4.6:1)
const C_WHITE     = '#3D3A36';   // 墨 — body text on cream (12:1)
const C_MUTED     = '#6E6A96';   // 深灰紫 — secondary text (4.68:1)
const C_DARK      = '#8A6B3D';   // 金深 — brand accent text
const C_BG_TOP    = '#FAF6EF';   // 奶油
const C_BG_MID    = '#F7F0E3';
const C_BG_BOT    = '#F2ECDF';
const C_PLACEHOLDER = '#F7F0E3'; // card image fallback fill
const C_GLOW      = 'rgba(201, 169, 124, 0.18)'; // soft gold glow on cream
const C_LINE_GOLD = 'rgba(201, 169, 124, 0.45)'; // visible gold line on cream

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

  // Brand header — 金深字 (4.6:1 on cream)
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.font = `bold ${Math.round(W * 0.043)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('✦ 星光映照 ✦', W / 2, y);
  ctx.restore();

  // Decorative line under brand — 细金，cream 上加透明 (0.55)
  const lineW = Math.round(W * 0.3);
  const lineX = Math.round((W - lineW) / 2);
  const lineY = y + Math.round(W * 0.058);
  ctx.save();
  ctx.strokeStyle = C_GOLD;
  ctx.globalAlpha = 0.55;
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
    ctx.fillStyle = C_PLACEHOLDER;
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
  ctx.fillStyle = C_GOLD_INK;
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
 * @param {string} [ctaText]    - Optional call-to-action text (defaults to reading-mode copy)
 * @param {string} [inviteCode] - Invite mode: draws "邀请码 STAR-XXXX" under the CTA
 */
function _drawQRCode(ctx, W, Y, qrImg, ctaText, inviteCode) {
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

  // QR border — cream 底上用细金描边（白码块在奶油上需描边可见）
  ctx.save();
  _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
  ctx.strokeStyle = 'rgba(201, 169, 124, 0.50)';
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

  // Invite mode: invite code line under the CTA (金深, so friends can also
  // type it in manually — "送好友一张牌" flow, no points / cash reward)
  if (inviteCode) {
    const codeY = ctaY + Math.round(W * 0.032);
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.globalAlpha = 0.95;
    ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`邀请码 ${inviteCode}`, W / 2, codeY);
    ctx.restore();
    return codeY + Math.round(W * 0.044);
  }

  return ctaY + Math.round(W * 0.042);
}

/**
 * Draw the brand footer.
 *
 * @param {string} [brandText] - Optional override (diary mode uses "星光映照 · 塔罗日记")
 */
function _drawFooter(ctx, W, Y, brandText) {
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.globalAlpha = 0.85;
  ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(brandText || '星光映照 · 塔罗占卜', W / 2, Y);
  ctx.restore();
}

/**
 * Draw the "星光名片" star-card poster layout (Task 7).
 *
 * Layout (3:4 portrait, E3 cream palette):
 *   - Top: brand header + nickname
 *   - 星阶徽章 + 星光数 two pill chips (金深 on cream, gold stroke)
 *   - The tarot card (smaller than the reading poster — 名片式)
 *   - Card name + key insight (capped above the QR zone, max 2 lines)
 *   - Bottom: mini-program code (from /share/wxacode, scene=邀请码)
 *             + footer "仅供娱乐 · 星光映照"
 *
 * @param {Object} data - { cardImg, qrImg, cardName, keyInsight, nickname,
 *                          starTierName, stardustTotal }
 */
function _drawCardLayout(ctx, W, H, data) {
  const { cardImg, qrImg, cardName, keyInsight, starTierName, stardustTotal } = data;

  // ── Header: brand + nickname ──
  let y = _drawHeader(ctx, W, data.nickname);
  y += Math.round(W * 0.020);

  // ── Star identity chips: 星阶徽章 + 星光数 ──
  const chipH = Math.round(W * 0.070);
  const chipGap = Math.round(W * 0.028);
  const stardustText = '星光 ' + (stardustTotal || 0);
  ctx.save();
  ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  // 星阶徽章：starTierName 为空（如 /tasks/status 失败）时省略徽章，
  // 绝不降级印「微光」——宁缺毋滥，避免非微光用户被错印（最终审查 F-3）。
  const hasTier = typeof starTierName === 'string' && starTierName.trim().length > 0;
  const tierW = hasTier
    ? ctx.measureText('✦ ' + starTierName + ' · 星阶').width + Math.round(W * 0.048)
    : 0;
  const sdW = ctx.measureText('✦ ' + stardustText).width + Math.round(W * 0.048);
  const chipsW = tierW + sdW + (hasTier ? chipGap : 0);
  const chipsX = Math.round((W - chipsW) / 2);
  const chipY = y;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  if (hasTier) {
    // tier chip — 金深字，奶油表面底，细金描边
    _roundRect(ctx, chipsX, chipY, tierW, chipH, chipH / 2);
    ctx.fillStyle = 'rgba(255, 253, 248, 0.92)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(201, 169, 124, 0.55)';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.fillText('✦ ' + starTierName + ' · 星阶', chipsX + tierW / 2, chipY + chipH / 2 + 1);
  }
  // stardust chip — 深灰紫字
  const sdX = chipsX + tierW + (hasTier ? chipGap : 0);
  _roundRect(ctx, sdX, chipY, sdW, chipH, chipH / 2);
  ctx.fillStyle = 'rgba(255, 253, 248, 0.92)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(201, 169, 124, 0.55)';
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.fillStyle = C_MUTED;
  ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.fillText('✦ ' + stardustText, sdX + sdW / 2, chipY + chipH / 2 + 1);
  ctx.restore();
  y += chipH + Math.round(W * 0.028);

  // ── Tarot card (smaller — 名片式) with gold glow + border ──
  const cardW = Math.round(W * 0.46);
  const cardH = Math.round(cardW * CARD_ASPECT);
  const cardX = Math.round((W - cardW) / 2);
  const r = Math.round(cardW * 0.02);

  const glowPad = Math.round(W * 0.012);
  ctx.save();
  ctx.fillStyle = C_GLOW;
  _roundRect(ctx, cardX - glowPad, y - glowPad, cardW + glowPad * 2, cardH + glowPad * 2, r + glowPad);
  ctx.fill();
  ctx.restore();

  ctx.save();
  _roundRect(ctx, cardX, y, cardW, cardH, r);
  ctx.clip();
  if (cardImg) {
    ctx.drawImage(cardImg, cardX, y, cardW, cardH);
  } else {
    ctx.fillStyle = C_PLACEHOLDER;
    ctx.fillRect(cardX, y, cardW, cardH);
  }
  ctx.restore();

  ctx.save();
  _roundRect(ctx, cardX, y, cardW, cardH, r);
  ctx.strokeStyle = C_GOLD;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.75;
  ctx.stroke();
  ctx.restore();

  y += cardH + Math.round(W * 0.028);

  // ── Card name ──
  if (cardName) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.040)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(cardName, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.056);
  }

  // ── Key insight (wrapped, capped above the QR zone, max 2 lines) ──
  if (keyInsight) {
    const maxW = Math.round(W * 0.78);
    const x = Math.round((W - maxW) / 2);
    const fontSize = Math.round(W * 0.030);
    const lineH = Math.round(fontSize * 1.55);
    const qrZoneY = H - Math.round(W * 0.24);
    const maxLines = Math.max(1, Math.min(2, Math.floor((qrZoneY - y) / lineH)));

    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    const lines = _wrapText(ctx, keyInsight, maxW);
    let textY = y;
    for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
      ctx.fillText(lines[i], x, textY);
      textY += lineH;
    }
    ctx.restore();
    y = textY;
  }

  // ── QR + CTA (never overlap footer) ──
  const qrY = Math.min(y, H - Math.round(W * 0.24));
  _drawQRCode(ctx, W, qrY, qrImg, '扫码加入星光映照');

  // ── Footer: 仅供娱乐 · 星光映照 ──
  _drawFooter(ctx, W, H - Math.round(W * 0.040), '仅供娱乐 · 星光映照');
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
 * Background is an E3 cream gradient #FAF6EF → #F7F0E3 → #F2ECDF.
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

  // Soft golden glow behind the card (E3: 细金光晕 on cream)
  const glowPad = Math.round(W * 0.014);
  ctx.save();
  ctx.fillStyle = C_GLOW;
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
    ctx.fillStyle = C_PLACEHOLDER;
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

  // Card name (金深, bold — 4.6:1 on cream)
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
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
    ctx.fillStyle = C_GOLD_INK;
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

/**
 * Draw the "zodiac match" poster layout (relationship tarot card).
 *
 * Layout (3:4 portrait):
 *   - Top: brand header + title "你们的塔罗关系牌"
 *   - Zodiac pairing as the hero ("♈ + ♉")
 *   - The drawn relationship card (centered, gold glow)
 *   - Compatibility blurb (white, wrapped, capped at 4 lines)
 *   - Bottom: mini-program code with CTA "看看你和谁的星座最契合"
 *             + brand footer
 *
 * Tone: fun and light — the poster never says "destiny".
 *
 * @param {Object} data - { cardImg, qrImg, cardName, keyInsight, zodiacSigns }
 */
function _drawZodiacLayout(ctx, W, H, data) {
  const { cardImg, qrImg, cardName, keyInsight, zodiacSigns } = data;

  // ── Top: brand header (no nickname) + title ──
  let y = _drawHeader(ctx, W, '');
  y += Math.round(W * 0.012);

  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.font = `bold ${Math.round(W * 0.042)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('你们的塔罗关系牌', W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.058);

  // Zodiac pairing — the hero of the poster
  if (zodiacSigns) {
    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${Math.round(W * 0.058)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(zodiacSigns, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.056);
  }

  // Relationship card name (lavender, subtle)
  if (cardName) {
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.031)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`塔罗关系牌 · ${cardName}`, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.028);
  }

  // ── Relationship card image (centered, gold glow) ──
  const cardW = Math.round(W * 0.30);
  const cardH = Math.round(cardW * CARD_ASPECT);
  const cardX = Math.round((W - cardW) / 2);
  const r = Math.round(cardW * 0.02);

  // Soft golden glow behind the card (E3)
  const glowPad = Math.round(W * 0.012);
  ctx.save();
  ctx.fillStyle = C_GLOW;
  _roundRect(ctx, cardX - glowPad, y - glowPad, cardW + glowPad * 2, cardH + glowPad * 2, r + glowPad);
  ctx.fill();
  ctx.restore();

  // Card image (clipped to rounded rect) + gold border
  ctx.save();
  _roundRect(ctx, cardX, y, cardW, cardH, r);
  ctx.clip();
  if (cardImg) {
    ctx.drawImage(cardImg, cardX, y, cardW, cardH);
  } else {
    ctx.fillStyle = C_PLACEHOLDER;
    ctx.fillRect(cardX, y, cardW, cardH);
  }
  ctx.restore();

  ctx.save();
  _roundRect(ctx, cardX, y, cardW, cardH, r);
  ctx.strokeStyle = C_GOLD;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.75;
  ctx.stroke();
  ctx.restore();

  // ── Compatibility blurb (wrapped, capped by the QR area above) ──
  let textBottom = y + cardH + Math.round(W * 0.026);

  if (keyInsight) {
    const maxW = Math.round(W * 0.78);
    const x = Math.round((W - maxW) / 2);
    const fontSize = Math.round(W * 0.031);
    const lineH = Math.round(fontSize * 1.55);
    // Never overlap the QR zone: cap lines by available space (max 4)
    const qrAreaY = H - Math.round(W * 0.25);
    const textMaxBottom = qrAreaY - Math.round(W * 0.008);
    const maxLines = Math.min(4, Math.max(1, Math.floor((textMaxBottom - textBottom) / lineH)));

    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';

    const lines = _wrapText(ctx, keyInsight, maxW);
    for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
      ctx.fillText(lines[i], x, textBottom);
      textBottom += lineH;
    }
    ctx.restore();
    textBottom += Math.round(W * 0.010);
  }

  // ── Bottom: QR code with the "看看你和谁的星座最契合" CTA + footer ──
  const qrY = Math.min(textBottom, H - Math.round(W * 0.25));
  _drawQRCode(ctx, W, qrY, qrImg, '看看你和谁的星座最契合');
  _drawFooter(ctx, W, H - Math.round(W * 0.040));
}

/**
 * Draw the "diary share" poster layout — anonymous journal excerpt.
 *
 * Layout (3:4 portrait):
 *   - Top: mood emoji (hero) + entry date
 *   - Middle: small tarot card thumbnail + card name (when attached),
 *     then the anonymized diary excerpt (wrapped, capped above the QR zone)
 *   - Bottom: mini-program code with CTA + "星光映照 · 塔罗日记" brand footer
 *
 * The poster never contains user-identifying info — no nickname, no user_id.
 *
 * @param {Object} data - { cardImg, qrImg, moodEmoji, dateText, cardName, excerpt }
 */
function _drawDiaryLayout(ctx, W, H, data) {
  const { cardImg, qrImg, moodEmoji, dateText, cardName, excerpt } = data;
  // Top of the QR area — excerpt text is capped so it never overlaps it
  const qrZoneY = H - Math.round(W * 0.26);

  // ── Top: mood emoji (hero) + date ──
  let y = Math.round(W * 0.13);

  if (moodEmoji) {
    ctx.save();
    ctx.font = `${Math.round(W * 0.11)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(moodEmoji, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.15);
  }

  if (dateText) {
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.030)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(dateText, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.052);
  }

  // ── Middle: small tarot card thumbnail (when the entry has a card) ──
  let textY = y;
  if (cardImg) {
    const cardW = Math.round(W * 0.26);
    const cardH = Math.round(cardW * CARD_ASPECT);
    const cardX = Math.round((W - cardW) / 2);
    const r = Math.round(cardW * 0.02);

    // Soft golden glow behind the card (E3)
    const glowPad = Math.round(W * 0.012);
    ctx.save();
    ctx.fillStyle = C_GLOW;
    _roundRect(ctx, cardX - glowPad, textY - glowPad, cardW + glowPad * 2, cardH + glowPad * 2, r + glowPad);
    ctx.fill();
    ctx.restore();

    // Card image (clipped to rounded rect) + gold border
    ctx.save();
    _roundRect(ctx, cardX, textY, cardW, cardH, r);
    ctx.clip();
    ctx.drawImage(cardImg, cardX, textY, cardW, cardH);
    ctx.restore();

    ctx.save();
    _roundRect(ctx, cardX, textY, cardW, cardH, r);
    ctx.strokeStyle = C_GOLD;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = 0.75;
    ctx.stroke();
    ctx.restore();

    textY += cardH + Math.round(W * 0.034);

    // Card name under the thumbnail
    if (cardName) {
      ctx.save();
      ctx.fillStyle = C_GOLD_INK;
      ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(`🃏 ${cardName}`, W / 2, textY);
      ctx.restore();
      textY += Math.round(W * 0.052);
    }
  } else if (cardName) {
    // No card image — card name alone, 金深 and subtle
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.globalAlpha = 0.9;
    ctx.font = `${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`🃏 ${cardName}`, W / 2, textY);
    ctx.restore();
    textY += Math.round(W * 0.052);
  }

  // ── Divider line (E3 细金，cream 上加透明) ──
  textY += Math.round(W * 0.018);
  const lineX = Math.round(W * 0.20);
  const lineW = Math.round(W * 0.60);
  ctx.save();
  ctx.strokeStyle = C_LINE_GOLD;
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(lineX, textY);
  ctx.lineTo(lineX + lineW, textY);
  ctx.stroke();
  ctx.restore();
  textY += Math.round(W * 0.030);

  // ── Diary excerpt (wrapped, capped above the QR zone) ──
  if (excerpt) {
    const maxW = Math.round(W * 0.78);
    const x = Math.round((W - maxW) / 2);
    const fontSize = Math.round(W * 0.031);
    const lineH = Math.round(fontSize * 1.6);
    const available = qrZoneY - textY - Math.round(W * 0.012);
    const maxLines = Math.max(1, Math.min(6, Math.floor(available / lineH)));

    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';

    const lines = _wrapText(ctx, excerpt, maxW);
    let excerptY = textY;
    for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
      ctx.fillText(lines[i], x, excerptY);
      excerptY += lineH;
    }
    ctx.restore();
  }

  // ── Bottom: mini-program code + brand footer ──
  _drawQRCode(ctx, W, qrZoneY, qrImg, '扫码 · 写下你的星光日记');
  _drawFooter(ctx, W, H - Math.round(W * 0.040), '星光映照 · 塔罗日记');
}

/**
 * Draw the "fortune trend" poster layout (牌运曲线 · 个人数据资产).
 *
 * Layout (3:4 portrait):
 *   - Top: brand + nickname (drawn by _drawHeader), title 我的牌运 (金深)
 *     + date · 近30天解读次数
 *   - 高频之牌 top3 rows (rank + name × count)
 *   - 大/小阿卡那 ratio bar + legend
 *   - 花色 4 chips (权杖/圣杯/宝剑/星币)
 *   - 每日解读 bar chart (最近 14 天 · 细金柱)
 *   - mood 一句话总结 (牌运之语)
 *   - Bottom: brand footer "星光映照 · 我的牌运"
 *
 * No mini-program QR — this is a personal data poster (截图物).
 *
 * Note: 微信组件属性传递时，嵌套数组可能被运行时转换为「数字键对象」
 * （{0:…,1:…}）— 所有数组字段一律经 _toArray 归一化后再使用。
 *
 * @param {Object} data - { dateText, totalReadings, activeDays, mood,
 *                          cards: [{name, name_en, count}], majorCount,
 *                          minorCount, suitList: [{name, count}],
 *                          trend: [{date, count}] }
 */
function _toArray(v) {
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') {
    // 微信组件属性中的「数字键对象」数组退化形态
    return Object.keys(v).map(k => v[k]);
  }
  return [];
}

function _drawFortuneLayout(ctx, W, H, data) {
  const {
    dateText, totalReadings, mood,
    cards, majorCount, minorCount, suitList, trend,
  } = data || {};
  const major = majorCount || 0;
  const minor = minorCount || 0;
  const totalCards = major + minor;

  // ── Title 我的牌运 (金深 bold) ──
  let y = Math.round(W * 0.158);
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.font = `bold ${Math.round(W * 0.050)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('我的牌运', W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.070);

  // ── Date + total readings (深灰紫) ──
  const summary = dateText
    ? `${dateText} · 近30天解读 ${totalReadings || 0} 次`
    : `近30天解读 ${totalReadings || 0} 次`;
  ctx.save();
  ctx.fillStyle = C_MUTED;
  ctx.globalAlpha = 0.9;
  ctx.font = `${Math.round(W * 0.027)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(summary, W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.052);

  // ── 高频之牌 top3 ──
  const topCards = _toArray(cards).slice(0, 3);
  if (topCards.length) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('✦ 高频之牌', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.042);

    const rowH = Math.round(W * 0.040);
    topCards.forEach((card, i) => {
      ctx.save();
      ctx.fillStyle = C_WHITE;
      ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(`第${i + 1}名  ${card.name}  × ${card.count}`, W / 2, y);
      ctx.restore();
      y += rowH;
    });
    y += Math.round(W * 0.014);
  }

  // ── 大/小阿卡那比例条 ──
  if (totalCards > 0) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('✦ 大阿卡那 · 小阿卡那', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.040);

    const trackW = Math.round(W * 0.72);
    const trackX = Math.round((W - trackW) / 2);
    const trackH = Math.round(W * 0.024);
    const majorW = Math.max(Math.round(trackW * (major / totalCards)), 2);
    // track
    ctx.save();
    _roundRect(ctx, trackX, y, trackW, trackH, trackH / 2);
    ctx.fillStyle = C_PLACEHOLDER;
    ctx.fill();
    ctx.restore();
    // major fill (金深)
    ctx.save();
    _roundRect(ctx, trackX, y, majorW, trackH, trackH / 2);
    ctx.fillStyle = C_GOLD_INK;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.restore();
    y += trackH + Math.round(W * 0.030);

    // legend
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.023)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(`大阿卡那 ${major}`, trackX, y);
    ctx.fillText(`小阿卡那 ${minor}`, trackX + trackW - Math.round(W * 0.34), y);
    ctx.restore();
    y += Math.round(W * 0.042);
  }

  // ── 花色 4 chips ──
  const suits = _toArray(suitList).slice(0, 4);
  if (suits.length) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('✦ 花色分布', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.040);

    const chipGap = Math.round(W * 0.016);
    const chipW = Math.round((W - Math.round(W * 0.16) - chipGap * 3) / 4);
    const chipH = Math.round(W * 0.064);
    const chipsX = Math.round(W * 0.08);
    suits.forEach((s, i) => {
      const cx = chipsX + i * (chipW + chipGap);
      ctx.save();
      _roundRect(ctx, cx, y, chipW, chipH, Math.round(W * 0.012));
      ctx.fillStyle = C_GLOW;
      ctx.fill();
      ctx.strokeStyle = C_LINE_GOLD;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.fillStyle = C_GOLD_INK;
      ctx.font = `${Math.round(W * 0.024)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${s.name || ''} ${s.count || 0}`, cx + chipW / 2, y + chipH / 2 + 1);
      ctx.restore();
    });
    y += chipH + Math.round(W * 0.032);
  }

  // ── 每日解读 bar chart（最近 14 天 · 细金柱）──
  const trendData = _toArray(trend).slice(-14);
  if (trendData.length) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('✦ 每日解读 · 近30天', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.040);

    const chartW = Math.round(W * 0.74);
    const chartX = Math.round((W - chartW) / 2);
    const chartH = Math.round(W * 0.19);
    const chartBottom = y + chartH;
    const maxCount = trendData.reduce((m, t) => Math.max(m, t && t.count ? t.count : 0), 0) || 1;
    const slotW = chartW / trendData.length;
    const barW = Math.max(2, Math.round(slotW * 0.52));
    const labelFont = Math.round(W * 0.019);

    // baseline (细金)
    ctx.save();
    ctx.strokeStyle = C_LINE_GOLD;
    ctx.globalAlpha = 0.6;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(chartX, chartBottom);
    ctx.lineTo(chartX + chartW, chartBottom);
    ctx.stroke();
    ctx.restore();

    trendData.forEach((t, i) => {
      const count = t && t.count ? t.count : 0;
      const barH = count > 0 ? Math.max(3, Math.round((count / maxCount) * (chartH - 10))) : 0;
      const bx = chartX + slotW * i + (slotW - barW) / 2;
      const by = chartBottom - barH;
      ctx.save();
      ctx.fillStyle = count > 0 ? C_GOLD : C_LINE_GOLD;
      ctx.globalAlpha = count > 0 ? 0.92 : 0.55;
      ctx.fillRect(bx, by, barW, count > 0 ? barH : 2);
      ctx.restore();
      // 仅标注首/中/末日期，避免拥挤
      if (i === 0 || i === trendData.length - 1 || i === Math.floor(trendData.length / 2)) {
        const dayLabel = t && t.date ? t.date.slice(5) : '';
        ctx.save();
        ctx.fillStyle = C_MUTED;
        ctx.globalAlpha = 0.8;
        ctx.font = `${labelFont}px "PingFang SC", "Helvetica Neue", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(dayLabel, bx + barW / 2, chartBottom + 3);
        ctx.restore();
      }
    });
    y = chartBottom + Math.round(W * 0.052);
  }

  // ── mood 一句话总结 ──
  if (mood) {
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.024)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('牌运之语', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.038);

    const maxW = Math.round(W * 0.76);
    const x = Math.round((W - maxW) / 2);
    const fontSize = Math.round(W * 0.027);
    const lineH = Math.round(fontSize * 1.6);
    // 不超过页脚位置（max 2 行）
    const footerY = H - Math.round(W * 0.040);
    const maxLines = Math.max(1, Math.min(2, Math.floor((footerY - y) / lineH)));
    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${fontSize}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    const lines = _wrapText(ctx, mood, maxW);
    let textY = y;
    for (let i = 0; i < Math.min(lines.length, maxLines); i++) {
      ctx.fillText(lines[i], x, textY);
      textY += lineH;
    }
    ctx.restore();
  }
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
 * @param {string}   opts.mode         - 'reading' (default) | 'daily' | 'invite' | 'zodiac' | 'diary' | 'fortune' | 'card'
 *                                      - 'card' = 星光名片（星阶徽章+星光数+小程序码）
 * @param {string}   opts.cardImagePath - Tarot card image URL
 * @param {string}   opts.cardName     - Card display name (e.g. "愚者 · The Fool")
 * @param {string}   opts.keyInsight   - Short excerpt from the interpretation
 * @param {string}   opts.nickname     - User's display name
 * @param {string}   opts.dateText     - Formatted date for daily/diary modes (e.g. "2026.07.31")
 * @param {number}   opts.streak       - Consecutive draw days for daily mode
 * @param {string}   opts.inviteCode   - Invite mode ("送好友一张牌"): QR carries
 *                                      `scene=invite_code=CODE`, CTA + code shown
 * @param {string}   opts.zodiacSigns  - Zodiac mode: pairing text (e.g. "♈ + ♉"),
 *                                      drawn as the poster hero
 * @param {string}   opts.moodEmoji    - Diary mode: mood emoji drawn as the poster hero
 * @param {string}   opts.excerpt      - Diary mode: anonymized diary excerpt text
 * @param {Object}   opts.fortuneData  - Fortune mode: 牌运曲线数据（无小程序码）
 * @param {string}   opts.starTierName - Card mode: 星阶名称（如 星辉）
 * @param {number}   opts.stardustTotal- Card mode: 星光值（星尘总量）
 * @param {Function} opts.onSuccess    - Callback (tempFilePath)
 * @param {Function} opts.onError      - Callback (Error)
 */
function drawSharePoster(canvasId, opts) {
  const { context, mode, cardImagePath, cardName, keyInsight, nickname, dateText, streak, inviteCode, zodiacSigns, moodEmoji, excerpt, fortuneData, starTierName, stardustTotal, onSuccess, onError } = opts || {};
  const isInviteMode = !!(mode === 'invite' && inviteCode);
  // 星光名片海报：小程序码从 /share/wxacode 拉取（scene=邀请码、体验版可用、需登录）
  const isCardMode = mode === 'card';

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
    // 牌运海报是个人数据截图物，不需要小程序码 — 直接视为已加载，不等下载
    let qrImageLoaded = mode === 'fortune';
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
      } else if (mode === 'zodiac') {
        // ── Zodiac match poster (relationship tarot card) ──
        _drawZodiacLayout(ctx, W, H, {
          cardImg: cardImg,
          qrImg: qrImg,
          cardName: cardName,
          keyInsight: keyInsight,
          zodiacSigns: zodiacSigns || '',
        });
      } else if (mode === 'diary') {
        // ── Diary share poster (anonymous journal excerpt) ──
        _drawDiaryLayout(ctx, W, H, {
          cardImg: cardImg,
          qrImg: qrImg,
          moodEmoji: moodEmoji || '',
          dateText: dateText || '',
          cardName: cardName || '',
          excerpt: excerpt || '',
        });
      } else if (mode === 'fortune') {
        // ── 牌运曲线海报（个人数据资产 · 奶油底 · 金深标题 · 柱状图）──
        _drawFortuneLayout(ctx, W, H, fortuneData || {});
        _drawFooter(ctx, W, H - Math.round(W * 0.040), '星光映照 · 我的牌运');
      } else if (mode === 'card') {
        // ── 星光名片海报（星阶徽章 + 星光数 + 小程序码 · 仅供娱乐）──
        _drawCardLayout(ctx, W, H, {
          cardImg: cardImg,
          qrImg: qrImg,
          cardName: cardName,
          keyInsight: keyInsight,
          nickname: nickname,
          starTierName: starTierName || '',
          stardustTotal: stardustTotal || 0,
        });
      } else {
        // ── Reading result poster (also invite mode: same layout + invite QR) ──
        // Card image
        const cardBottom = _drawCardImage(ctx, W, headerBottom, cardImg);

        // Card name
        const nameBottom = _drawCardName(ctx, W, cardBottom, cardName);

        // Key insight
        const insightBottom = _drawKeyInsight(ctx, W, nameBottom, keyInsight);

        // QR code — invite mode reserves extra bottom room for the code line
        const qrY = Math.min(insightBottom, H - Math.round(W * (isInviteMode ? 0.28 : 0.22)));
        _drawQRCode(ctx, W, qrY, qrImg, isInviteMode ? '扫码 · 送你一张牌' : undefined, inviteCode);

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
    // We use wx.downloadFile for broad domain compatibility.
    // NOTE: tabbar pages cannot be used as the wxacode `path` (WeChat rejects
    // them with 41030) — use a real non-tabbar page and pass the invite code
    // through the `scene` param instead. On scan, the mini-program launches
    // pages/share-center/share-center with options.query.scene carrying the code.
    let qrUrl = BASE_URL + '/share/wxa-code?path=' + encodeURIComponent('pages/share-center/share-center') + '&width=280';
    if (isInviteMode) {
      qrUrl += '&scene=' + encodeURIComponent('invite_code=' + inviteCode);
    }
    // 星光名片：小程序码走登录接口（scene=邀请码 → card-landing），需带 token
    const qrHeaders = {};
    if (isCardMode) {
      qrUrl = BASE_URL + '/share/wxacode';
      const token = wx.getStorageSync('token');
      if (token) qrHeaders.Authorization = 'Bearer ' + token;
    }
    wx.downloadFile({
      url: qrUrl,
      header: qrHeaders,
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

  // 1. Background — E3 奶油渐变
  const gradient = ctx.createLinearGradient(0, 0, 0, H);
  gradient.addColorStop(0, C_BG_TOP);
  gradient.addColorStop(0.5, C_BG_MID);
  gradient.addColorStop(1, C_BG_BOT);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, W, H);

  // 2. Brand header — 金深字
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.font = `bold ${Math.round(W * 0.045)}px "PingFang SC", "Helvetica Neue", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('✦ 星光日记 ✦', W / 2, y);
  ctx.restore();
  y += Math.round(W * 0.065);

  // 3. Date — 深灰紫
  ctx.save();
  ctx.fillStyle = C_MUTED;
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
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `${Math.round(W * 0.035)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(`🃏 ${entry.card.name_zh}`, W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.048);
  }

  // 6. Divider line — E3 细金
  y += Math.round(W * 0.020);
  const lineX = PADDING + Math.round(contentW * 0.15);
  const lineW = Math.round(contentW * 0.70);
  ctx.save();
  ctx.strokeStyle = C_LINE_GOLD;
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(lineX, y);
  ctx.lineTo(lineX + lineW, y);
  ctx.stroke();
  ctx.restore();
  y += Math.round(W * 0.035);

  // 7. Reflection text
  if (entry.reflection) {
    // Label — 深灰紫
    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('今日感悟', PADDING, y);
    ctx.restore();
    y += Math.round(W * 0.040);

    // Text content — simple wrap (墨字 on cream ≈12:1)
    const fontSize = Math.round(W * 0.032);
    const lineH = fontSize * 1.6;
    ctx.save();
    ctx.fillStyle = C_WHITE;
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
    ctx.fillStyle = 'rgba(201, 169, 124, 0.14)';
    ctx.strokeStyle = 'rgba(201, 169, 124, 0.28)';
    const imgH = Math.round(W * 0.35);
    const imgW = Math.round(contentW * 0.6);
    const imgX = Math.round((W - imgW) / 2);
    _roundRect(ctx, imgX, y, imgW, imgH, Math.round(W * 0.02));
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('📷', imgX + imgW / 2, y + imgH / 2);
    ctx.restore();
    y += imgH + Math.round(W * 0.030);
  }

  // 9. Footer — 金深
  y = Math.max(y, H - Math.round(W * 0.060));
  ctx.save();
  ctx.fillStyle = C_GOLD_INK;
  ctx.globalAlpha = 0.85;
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

// =====================================================================
//  Birthchart Report Poster — drawBirthchartPoster
// =====================================================================

/**
 * Generate a share poster for the birth-chart deep report (开发 05).
 *
 * Layout (3:4 portrait, E3 cream palette):
 *   品牌头 → 昵称 → 标题「我的本命星盘」→ 日月升三行（图标+星座+一句话）
 *   → 性格金句摘录（character 段首 2~3 行）→ 小程序码 → 品牌尾
 *
 * @param {string} canvasId - Canvas node id
 * @param {Object} opts
 * @param {Object} opts.context   - Page `this`（SelectorQuery 作用域）
 * @param {Array}  opts.elements  - [{icon, displayName, line, approx}] 三要素
 * @param {string} opts.quote     - 深度报告性格底色摘录
 * @param {string} opts.nickname  - 用户昵称（可空）
 * @param {string} opts.dateText  - 生成日期（可空，如 "2026.08.09"）
 * @param {Function} opts.onSuccess - 回调(tempFilePath)
 * @param {Function} opts.onError   - 回调(Error)
 */
function drawBirthchartPoster(canvasId, opts) {
  const { context, elements, quote, nickname, dateText, onSuccess, onError } = opts || {};
  if (!context || !canvasId) {
    if (onError) onError(new Error('Missing required params: context / canvasId'));
    return;
  }

  const sysInfo = wx.getSystemInfoSync();
  const W = sysInfo.screenWidth || 375;
  const dpr = sysInfo.pixelRatio || 2;
  const H = Math.round(W / TARGET_ASPECT); // 3:4 portrait

  const query = wx.createSelectorQuery().in(context);
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

    // ── 1. Background ──
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, C_BG_TOP);
    gradient.addColorStop(0.5, C_BG_MID);
    gradient.addColorStop(1, C_BG_BOT);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
    _drawStars(ctx, W);

    // ── 2. Brand header ──
    const headerBottom = _drawHeader(ctx, W, nickname);
    let y = headerBottom + Math.round(W * 0.030);

    // ── 3. Title ──
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.058)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('我的本命星盘', W / 2, y);
    y += Math.round(W * 0.088);
    if (dateText) {
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.028)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.fillText(dateText, W / 2, y);
      y += Math.round(W * 0.050);
    }
    ctx.restore();

    // ── 4. Three element rows ──
    const rowX = Math.round(W * 0.10);
    const rowW = W - rowX * 2;
    const rowH = Math.round(W * 0.115);
    const gap = Math.round(W * 0.022);
    (elements || []).slice(0, 3).forEach(function (el) {
      _roundRect(ctx, rowX, y, rowW, rowH, Math.round(W * 0.02));
      ctx.fillStyle = 'rgba(255, 255, 255, 0.55)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(201, 169, 124, 0.40)';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Icon
      ctx.save();
      ctx.fillStyle = C_GOLD_INK;
      ctx.font = `${Math.round(W * 0.052)}px "PingFang SC", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(el.icon || '✦', rowX + Math.round(W * 0.06), y + rowH / 2);
      ctx.restore();

      // Name
      ctx.save();
      ctx.fillStyle = C_WHITE;
      ctx.font = `bold ${Math.round(W * 0.032)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(el.displayName || '', rowX + Math.round(W * 0.12), y + Math.round(W * 0.022));
      ctx.restore();

      // Line (approx tag + one-liner, ellipsis to one line)
      ctx.save();
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      let line = el.line || '';
      const approxTag = el.approx ? '近似 · ' : '';
      const maxW = rowW - Math.round(W * 0.15);
      ctx.fillText(_ellipsis(ctx, approxTag + line, maxW), rowX + Math.round(W * 0.12), y + Math.round(W * 0.064));
      ctx.restore();

      y += rowH + gap;
    });

    // ── 5. Quote from the report ──
    y += Math.round(W * 0.012);
    const quoteX = rowX;
    const quoteMaxW = rowW;
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.globalAlpha = 0.95;
    ctx.font = `${Math.round(W * 0.027)}px "PingFang SC", "Helvetica Neue", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    if (quote) {
      const lines = _wrapText(ctx, `「${quote}」`, quoteMaxW);
      lines.slice(0, 3).forEach(function (ln) {
        ctx.fillText(ln, quoteX, y);
        y += Math.round(W * 0.040);
      });
    }
    ctx.restore();

    // ── 6. QR + footer ──
    let qrY = y + Math.round(W * 0.020);
    const qrSize = Math.round(W * QR_SIZE_RATIO);
    let qrImg = null;
    let qrLoaded = false;

    const qrUrl = BASE_URL + '/share/wxa-code?path=' + encodeURIComponent('pages/birthchart/birthchart') + '&width=280';
    wx.downloadFile({
      url: qrUrl,
      success: function (dlRes) {
        if (dlRes.statusCode !== 200) { qrLoaded = true; _finish(); return; }
        const q = canvas.createImage();
        q.onload = function () { qrImg = q; qrLoaded = true; _finish(); };
        q.onerror = function () { qrLoaded = true; _finish(); };
        q.src = dlRes.tempFilePath;
      },
      fail: function () { qrLoaded = true; _finish(); },
    });
    setTimeout(function () { if (!qrLoaded) { qrLoaded = true; _finish(); } }, 5000);

    function _drawQR() {
      const qrX = Math.round((W - qrSize) / 2);
      const qrAreaY = qrY;
      ctx.save();
      _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
      ctx.clip();
      if (qrImg) ctx.drawImage(qrImg, qrX, qrAreaY, qrSize, qrSize);
      ctx.restore();
      ctx.save();
      _roundRect(ctx, qrX, qrAreaY, qrSize, qrSize, 6);
      ctx.strokeStyle = 'rgba(201, 169, 124, 0.50)';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
      ctx.save();
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.026)}px "PingFang SC", "Helvetica Neue", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('扫码 · 看看你的星盘', W / 2, qrAreaY + qrSize + 4);
      ctx.restore();
    }

    function _finish() {
      _drawQR();
      _drawFooter(ctx, W, H - Math.round(W * 0.045), '星光映照 · 本命星盘');
      wx.canvasToTempFilePath({
        canvas: canvas,
        success: function (res2) { if (onSuccess) onSuccess(res2.tempFilePath); },
        fail: function (err) { if (onError) onError(err); },
      }, context);
    }
  });
}

/** 单行省略号（canvas 无 measureText 截断辅助） */
function _ellipsis(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(t + '…').width > maxWidth) {
    t = t.slice(0, -1);
  }
  return t + '…';
}

module.exports = { drawSharePoster, generateDiaryCard, drawBirthchartPoster };
