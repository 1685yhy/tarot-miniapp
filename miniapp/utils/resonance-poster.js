// utils/resonance-poster.js —— 今日星光共鸣海报（SDD P2 · T8-4）
//
// 版式（3:4 竖版 · E3 奶油底，与 meet-poster 同系双星徽章版式）：
//   品牌头（✦ 星光映照 ✦ 金线）
//   + 标题「今日星光共鸣」
//   + 双星徽章并置（两枚星光徽章：星座 emoji + 星名；星阶名小字）
//   + 共鸣维度胶囊（同星座 / 同一张牌 / 同星光数 —— 服务端 dimension）
//   + 双星信息两行（星名 · 星光数 · 今日牌）
//   + 固定文案 caption（代码常量模板，过内容安全后由后端下发）
//   + 页脚「仅供娱乐 · 星光映照」
//
// 数据源：GET /resonance/poster?to_user_id=（全脱敏：星名/星座/星光数/今日牌/星阶名，
// 零 UGC、零可联系字段）。与 meet-poster.js / journal-poster.js 同构：
// 复用 canvas-poster.js 的 E3 调色板与绘制辅助（单一色彩/圆角/码位来源）。
//
// 小程序码（T8-5）：复用 /share/wxacode（登录态名片码，scene=邀请码 →
// card-landing 拉新闭环，不新增微信调用）。拉取失败/超时 → 无码降级
// （仅页脚、不画空白码位，T8-4 既有版式）；带码版式在小程序码上方
// 预留 QR 区（qrZoneY），文案行数随可用高度收敛，不重叠码位。
// 管线（onSuccess/onError/预览/保存/分享）两版式完全一致。

const { PALETTE, DRAW_HELPERS, LAYOUT } = require('./canvas-poster');
const { BASE_URL } = require('./api');
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
  drawFooter,
  drawQRCode,
} = DRAW_HELPERS;

const FONT = '"PingFang SC", "Helvetica Neue", sans-serif';

// 星座元素底色（E3 四系 —— 与 meet 页/相遇海报同款，双星徽章用）
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

/** 星座 key → { emoji, name }（key 非法 → 空 emoji + 空名） */
function zodiacInfo(key) {
  const z = ZODIAC_BY_KEY[key] || null;
  return {
    emoji: (z && z.emoji) || '✦',
    name: (z && z.name) || '',
    element: ZODIAC_ELEMENT[key] || '',
  };
}

/** 共鸣维度 → 中文说明（服务端 dimension：zodiac / card / number） */
function dimensionText(dim, p) {
  if (dim === 'zodiac') {
    const name = zodiacInfo(p.zodiacA).name || zodiacInfo(p.zodiacB).name;
    return name ? `同星座的星光 · ${name}` : '同星座的星光';
  }
  if (dim === 'card') {
    return p.cardAName ? `同一张牌的星光 · ${p.cardAName}` : '同一张牌的星光';
  }
  return `同星光数的星光 · ${p.starNumberA != null ? p.starNumberA : ''}`;
}

/**
 * 生成今日星光共鸣海报（3:4 竖版 · E3 奶油底 · 双星版式）。
 *
 * 小程序码（T8-5）：复用 /share/wxacode（登录态名片码 scene=邀请码 →
 * card-landing）。码拉取失败/未登录/超时 → 无码降级（仅页脚），
 * 保存/分享不阻塞；管线与带码版式一致。
 *
 * @param {string} canvasId - Canvas 节点 id
 * @param {Object} pageContext - 页面 this（SelectorQuery 作用域）
 * @param {Object} opts - {
 *   poster: {                              // GET /resonance/poster 归一化
 *     aliasA, aliasB,                      // 双方脱敏星名
 *     zodiacA, zodiacB,                    // 星座 key（可空）
 *     starNumberA, starNumberB,            // 双方星光数
 *     cardAName, cardBName,                // 双方今日牌名
 *     tierNameA, tierNameB,                // 双方星阶名
 *     dimension,                           // zodiac / card / number
 *     caption, disclaimer                  // 固定文案（过内容安全）
 *   },
 *   onSuccess(tempFilePath), onError(err)
 * }
 */
function drawResonancePoster(canvasId, pageContext, opts) {
  const { poster, onSuccess, onError } = opts || {};

  if (!pageContext || !canvasId) {
    if (onError) onError(new Error('Missing required params: context / canvasId'));
    return;
  }
  const p = poster || {};

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
    ctx.fillText('今日星光共鸣', W / 2, y);
    ctx.restore();
    y += Math.round(W * 0.072);

    // ── 3. 双星徽章并置（a ✦ b） ──
    const a = zodiacInfo(p.zodiacA);
    const b = zodiacInfo(p.zodiacB);
    const aAlias = p.aliasA || '无名星';
    const bAlias = p.aliasB || '无名星';

    const badgeW = Math.round(W * 0.33);
    const badgeH = Math.round(W * 0.21);
    const badgeY = y;
    const gap = Math.round(W * 0.07);
    const leftX = Math.round((W - badgeW * 2 - gap) / 2);
    const rightX = leftX + badgeW + gap;

    // a 徽章
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
    const aAliasLine = wrapText(ctx, aAlias, badgeW - Math.round(W * 0.06))[0] || aAlias;
    ctx.fillText(aAliasLine, leftX + badgeW / 2, badgeY + Math.round(W * 0.104));
    if (p.tierNameA) {
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.022)}px ${FONT}`;
      ctx.fillText(p.tierNameA, leftX + badgeW / 2, badgeY + Math.round(W * 0.154));
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
    const bAliasLine = wrapText(ctx, bAlias, badgeW - Math.round(W * 0.06))[0] || bAlias;
    ctx.fillText(bAliasLine, rightX + badgeW / 2, badgeY + Math.round(W * 0.104));
    if (p.tierNameB) {
      ctx.fillStyle = C_MUTED;
      ctx.font = `${Math.round(W * 0.022)}px ${FONT}`;
      ctx.fillText(p.tierNameB, rightX + badgeW / 2, badgeY + Math.round(W * 0.154));
    }
    ctx.restore();
    y += badgeH + Math.round(W * 0.036);

    // ── 4. 共鸣维度胶囊 ──
    const dimText = dimensionText(p.dimension, p);
    const dimFontSize = Math.round(W * 0.028);
    ctx.save();
    ctx.font = `${dimFontSize}px ${FONT}`;
    const dimW = ctx.measureText(dimText).width + Math.round(W * 0.06);
    const dimH = dimFontSize + Math.round(W * 0.026);
    const dimX = Math.round((W - dimW) / 2);
    roundRect(ctx, dimX, y, dimW, dimH, dimH / 2);
    ctx.fillStyle = 'rgba(255, 253, 248, 0.92)';
    ctx.fill();
    ctx.strokeStyle = C_LINE_GOLD;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = C_GOLD_INK;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(dimText, W / 2, y + Math.round(W * 0.012));
    ctx.restore();
    y += dimH + Math.round(W * 0.040);

    // ── 5. 双星信息两行（星名 · 星光数 · 今日牌） ──
    const infoLines = [
      `✦ ${p.aliasA || '无名星'} · 星光数 ${p.starNumberA != null ? p.starNumberA : '-'} · ${p.cardAName || '今日牌'}`,
      `✦ ${p.aliasB || '无名星'} · 星光数 ${p.starNumberB != null ? p.starNumberB : '-'} · ${p.cardBName || '今日牌'}`,
    ];
    ctx.save();
    ctx.fillStyle = C_WHITE;
    ctx.font = `${Math.round(W * 0.026)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    infoLines.forEach((line, i) => {
      const parts = line.split('·');
      let cx = W / 2;
      // 三段式居中（星名 · 星光数 · 牌名），整体作为一行绘制（超宽降级为省略）
      const full = ctx.measureText(line).width;
      if (full <= W * 0.88) {
        ctx.fillText(line, W / 2, y);
      } else {
        // 超宽：三段各自压缩（星名最长限 8 字）
        const namePart = parts[0].slice(0, 10);
        const short = [namePart].concat(parts.slice(1)).join('·');
        ctx.fillText(short, W / 2, y);
      }
      y += Math.round(W * 0.046);
      void cx;
    });
    ctx.restore();
    y += Math.round(W * 0.014);

    // ── 6. 分隔线 + 固定文案 caption（行数随小程序码区可用高度收敛） ──
    ctx.save();
    ctx.strokeStyle = C_LINE_GOLD;
    ctx.lineWidth = 0.8;
    ctx.beginPath();
    ctx.moveTo(Math.round(W * 0.20), y);
    ctx.lineTo(Math.round(W * 0.80), y);
    ctx.stroke();
    ctx.restore();
    y += Math.round(W * 0.040);

    // 小程序码区上沿（T8-5：复用 /share/wxacode 名片码；码位恒定预留，
    // 无码降级时该区留白仅页脚，与 T8-4 既有版式一致）
    const qrZoneY = H - Math.round(W * 0.26);

    const caption = p.caption || '两颗星在同一片夜空相遇 ✦';
    ctx.save();
    ctx.fillStyle = C_GOLD_INK;
    ctx.font = `bold ${Math.round(W * 0.032)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const capLines = wrapText(ctx, caption, W * 0.86);
    const capLineH = Math.round(W * 0.050);
    // 文案止于码区上沿（最多 2 行；可用高度不足时收敛为 1 行，不重叠码位）
    const maxCapLines = Math.max(1, Math.min(2, Math.floor((qrZoneY - y - Math.round(W * 0.030)) / capLineH)));
    capLines.slice(0, maxCapLines).forEach((ln, i) => {
      ctx.fillText(ln, W / 2, y + i * capLineH);
    });
    ctx.restore();
    y += maxCapLines * capLineH + Math.round(W * 0.030);

    // ── 7. 小程序码（/share/wxacode · 登录态）+ 页脚 ──
    // 码拉取失败/未登录/超时 → 无码降级（仅页脚，不画空白码位），不阻塞成图
    let qrImg = null;
    let qrReady = false;
    let finished = false;

    function _finish() {
      if (finished) return;
      if (!qrReady) return;
      finished = true;
      if (qrImg) {
        drawQRCode(ctx, W, qrZoneY, qrImg, '扫码 · 看看谁与你同星');
      }
      drawFooter(ctx, W, H - Math.round(W * 0.040), p.disclaimer || '仅供娱乐 · 星光映照');
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

    // 名片码：scene=用户邀请码 → card-landing 拉新（复用 /share/wxacode，不新增微信调用）
    const token = wx.getStorageSync('token');
    wx.downloadFile({
      url: BASE_URL + '/share/wxacode',
      header: token ? { Authorization: 'Bearer ' + token } : {},
      success: function (dlRes) {
        if (dlRes.statusCode !== 200) {
          // 码拉取失败：无码降级，海报仍可生成
          qrReady = true;
          _finish();
          return;
        }
        const q = canvas.createImage();
        q.onload = function () {
          qrImg = q;
          qrReady = true;
          _finish();
        };
        q.onerror = function () {
          qrReady = true;
          _finish();
        };
        q.src = dlRes.tempFilePath;
      },
      fail: function () {
        qrReady = true;
        _finish();
      },
    });

    // 安全超时：码 5 秒未就绪也照常成图（无码降级）
    setTimeout(function () {
      qrReady = true;
      _finish();
    }, 5000);
  });
}

module.exports = { drawResonancePoster };
