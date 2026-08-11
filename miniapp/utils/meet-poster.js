// utils/meet-poster.js —— 星辰相遇合盘海报（SDD P1 · T2-5）
//
// 版式（3:4 竖版 · E3 奶油底，设计 2.3）：
//   品牌头（✦ 星光映照 ✦ 金线）
//   + 标题「星辰相遇」
//   + 双人徽章并置（两枚星光徽章：星座 emoji + 中文名；a 侧带发起人昵称小字）
//   + 共鸣度大数字 + 档位名（level_name）
//   + 三牌横排（position + 牌名 chips，文字版：零图片依赖、确定性强）
//   + 小程序码（复用 /share/wxa-code：scene=m:{meet_id} → meet-landing，海报即拉新）
//   + CTA「扫码 · 看看你们的星辰共鸣度」
//   + 页脚「仅供娱乐 · 星光映照」
//
// 数据源：GET /meet/{meet_id}/poster（脱敏：昵称/星座/score/level/牌面摘要/分享文案，
// 无日记类原文、无出生信息）。与 journal-poster.js / moon-card-poster.js 同构：
// 复用 canvas-poster.js 的 E3 调色板与绘制辅助（单一色彩/圆角/码位来源）。

const { BASE_URL } = require('./api');
const { PALETTE, DRAW_HELPERS, LAYOUT } = require('./canvas-poster');
const { ZODIAC_BY_KEY } = require('./energy');

const {
  C_GOLD,
  C_GOLD_INK,
  C_WHITE,
  C_MUTED,
  C_BG_TOP,
  C_BG_MID,
  C_BG_BOT,
  C_LINE_GOLD,
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

// 星座元素底色（E3 四系 —— 与 meet 页/落地页同款，海报徽章用）
const ELEMENT_OF = {
  fire: ['aries', 'leo', 'sagittarius'],
  earth: ['taurus', 'virgo', 'capricorn'],
  air: ['gemini', 'libra', 'aquarius'],
  water: ['cancer', 'scorpio', 'pisces'],
};
const ZODIAC_ELEMENT = {};
Object.keys(ELEMENT_OF).forEach((el) => {
  ELEMENT_OF[el].forEach((key) => { ZODIAC_ELEMENT[key] = el; });
});
const ELEMENT_FILL = {
  fire: 'rgba(232, 196, 190, 0.40)',
  earth: 'rgba(201, 169, 124, 0.26)',
  air: 'rgba(216, 210, 228, 0.45)',
  water: 'rgba(175, 194, 209, 0.40)',
};

/** 星座 key → { emoji, name }（key 非法 → 空 emoji + 原样文本） */
function zodiacInfo(key) {
  const z = ZODIAC_BY_KEY[key] || null;
  return {
    emoji: (z && z.emoji) || '✦',
    name: (z && z.name) || '',
    element: ZODIAC_ELEMENT[key] || '',
  };
}

/**
 * 生成星辰相遇合盘海报（3:4 竖版 · E3 奶油底）。
 *
 * @param {string} canvasId - Canvas 节点 id
 * @param {Object} pageContext - 页面 this（SelectorQuery 作用域）
 * @param {Object} opts - {
 *   poster: {                              // GET /meet/{meet_id}/poster 归一化
 *     meet_id, relation,
 *     a: {zodiac, name_zh, nickname},
 *     b: {zodiac, name_zh},
 *     score, level_name,
 *     cards: [{position, name_zh}],
 *     share_text
 *   },
 *   onSuccess(tempFilePath), onError(err)
 * }
 */
function drawMeetPoster(canvasId, pageContext, opts) {
  const { poster, onSuccess, onError } = opts || {};

  if (!pageContext || !canvasId) {
    if (onError) onError(new Error('Missing required params: context / canvasId'));
    return;
  }
  const p = poster || {};
  const meetId = p.meet_id || '';
  const score = typeof p.score === 'number' ? p.score : null;

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

    // ── 1. 背景奶油渐变 + 装饰星点 ──
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, C_BG_TOP);
    gradient.addColorStop(0.5, C_BG_MID);
    gradient.addColorStop(1, C_BG_BOT);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
    drawStars(ctx, W);

    // ── 2. 品牌头 + 标题 ──
    let y = drawHeader(ctx, W, '');
    y += Math.round(W * 0.030);

    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.046)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('星辰相遇', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.066);

    // ── 3. 双人徽章并置（a ✦ b） ──
    const a = zodiacInfo(p.a && p.a.zodiac);
    const b = zodiacInfo(p.b && p.b.zodiac);
    const aName = (p.a && p.a.name_zh) || a.name || '我';
    const bName = (p.b && p.b.name_zh) || b.name || 'TA';
    const aNick = (p.a && p.a.nickname) || '';

    const badgeW = Math.round(W * 0.33);
    const badgeH = Math.round(W * 0.21);
    const badgeY = y;
    const gap = Math.round(W * 0.07);
    const leftX = Math.round((W - badgeW * 2 - gap) / 2);
    const rightX = leftX + badgeW + gap;

    // a 徽章（发起人；带昵称小字）
    ctx.save();
    roundRect(ctx, leftX, badgeY, badgeW, badgeH, Math.round(W * 0.025));
    ctx.fillStyle = ELEMENT_FILL[a.element] || 'rgba(255, 253, 248, 0.92)';
    ctx.fill();
    ctx.strokeStyle = C_LINE_GOLD;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C_WHITE;
    ctx.font = `${Math.round(W * 0.055)}px sans-serif`;
    ctx.fillText(a.emoji, leftX + badgeW / 2, badgeY + Math.round(W * 0.028));
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.031)}px ${FONT}`;
    ctx.fillText(aName, leftX + badgeW / 2, badgeY + Math.round(W * 0.104));
    if (aNick) {
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.022)}px ${FONT}`;
      const nick = wrapText(ctx, aNick, badgeW - Math.round(W * 0.06))[0] || aNick;
      ctx.fillText(nick, leftX + badgeW / 2, badgeY + Math.round(W * 0.154));
    }
    ctx.restore();

    // 中间连接星
    ctx.save();
    ctx.fillStyle = C_GOLD;
    ctx.font = `${Math.round(W * 0.040)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('✦', leftX + badgeW + gap / 2, badgeY + badgeH / 2);
    ctx.restore();

    // b 徽章
    ctx.save();
    roundRect(ctx, rightX, badgeY, badgeW, badgeH, Math.round(W * 0.025));
    ctx.fillStyle = ELEMENT_FILL[b.element] || 'rgba(255, 253, 248, 0.92)';
    ctx.fill();
    ctx.strokeStyle = C_LINE_GOLD;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C_WHITE;
    ctx.font = `${Math.round(W * 0.055)}px sans-serif`;
    ctx.fillText(b.emoji, rightX + badgeW / 2, badgeY + Math.round(W * 0.028));
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.031)}px ${FONT}`;
    ctx.fillText(bName, rightX + badgeW / 2, badgeY + Math.round(W * 0.104));
    ctx.restore();
    y += badgeH + Math.round(W * 0.040);

    // ── 4. 共鸣度大数字 + 档位名 ──
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.105)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(score == null ? '--' : String(score), W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.118);

    ctx.save();
    ctx.fillStyle = C_MUTED;
    ctx.font = `${Math.round(W * 0.028)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText('星辰共鸣度', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.046);

    if (p.level_name) {
      ctx.save();
      ctx.fillStyle = C_GOLD_INK;
      ctx.font = `${Math.round(W * 0.030)}px ${FONT}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(`✦ ${p.level_name} ✦`, W / 2, y);
      ctx.restore();
      y += Math.round(W * 0.050);
    }

    // ── 5. 三牌横排（position + 牌名 chips，文字版零图片依赖） ──
    const cards = toArray(p.cards).filter((c) => c && c.name_zh).slice(0, 3);
    if (cards.length > 0) {
      ctx.save();
      ctx.strokeStyle = C_LINE_GOLD;
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(Math.round(W * 0.20), y);
      ctx.lineTo(Math.round(W * 0.80), y);
      ctx.stroke();
      ctx.restore();
      y += Math.round(W * 0.026);

      const chipW = Math.round(W * 0.26);
      const chipH = Math.round(W * 0.088);
      const chipGap = Math.round(W * 0.026);
      const chipsW = chipW * cards.length + chipGap * (cards.length - 1);
      const chipX0 = Math.round((W - chipsW) / 2);
      cards.forEach((c, i) => {
        const cx = chipX0 + i * (chipW + chipGap);
        ctx.save();
        roundRect(ctx, cx, y, chipW, chipH, Math.round(W * 0.02));
        ctx.fillStyle = 'rgba(255, 253, 248, 0.92)';
        ctx.fill();
        ctx.strokeStyle = C_LINE_GOLD;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = C_MUTED;
        ctx.font = `${Math.round(W * 0.021)}px ${FONT}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(c.position || '牌位', cx + chipW / 2, y + Math.round(W * 0.016));
        ctx.fillStyle = C_GOLD_INK;
        ctx.font = `bold ${Math.round(W * 0.024)}px ${FONT}`;
        const name = wrapText(ctx, c.name_zh, chipW - Math.round(W * 0.04))[0] || '';
        ctx.fillText(name, cx + chipW / 2, y + Math.round(W * 0.050));
        ctx.restore();
      });
      y += chipH + Math.round(W * 0.030);
    }

    // ── 6. 小程序码（scene=m:{meet_id} → meet-landing）+ 页脚 ──
    const qrZoneY = H - Math.round(W * 0.26);
    let qrImg = null;
    let qrImageLoaded = false;
    let drawAttempted = false;

    function _tryFinish() {
      if (drawAttempted) return;
      if (!qrImageLoaded) return;
      drawAttempted = true;
      drawQRCode(ctx, W, qrZoneY, qrImg, '扫码 · 看看你们的星辰共鸣度');
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

    // 相遇码：scene=m:{meet_id} → meet-landing（/share/wxa-code 公开、无需登录，
    // 与 canvas-poster invite 模式同款调用；双端（发起人/好友）都能取码）
    const qrUrl = BASE_URL + '/share/wxa-code?path=' +
      encodeURIComponent('pages/meet-landing/meet-landing') + '&width=280&scene=' +
      encodeURIComponent('m:' + meetId);
    wx.downloadFile({
      url: qrUrl,
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

module.exports = { drawMeetPoster };
