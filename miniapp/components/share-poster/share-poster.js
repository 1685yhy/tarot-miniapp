/**
 * Share Poster Component
 * Canvas-based poster generator combining card image, quote, and QR code.
 *
 * Usage (reading-result poster):
 *   <share-poster
 *     visible="{{showSharePoster}}"
 *     cardImagePath="{{shareCardImage}}"
 *     cardName="{{shareCardName}}"
 *     keyInsight="{{shareKeyInsight}}"
 *     nickname="{{userNickname}}"
 *     bind:close="onCloseSharePoster"
 *   />
 *
 * Usage (daily card check-in poster — mode="daily"):
 *   <share-poster
 *     mode="daily"
 *     visible="{{showDailySharePoster}}"
 *     cardImagePath="{{dailyShareCardImage}}"
 *     cardName="{{dailyShareCardName}}"
 *     dateText="{{dailyShareCardDate}}"
 *     streak="{{streak}}"
 *     bind:close="onCloseDailySharePoster"
 *   />
 *
 * Usage (friend invite poster — mode="invite", "送好友一张牌"):
 *   <share-poster
 *     mode="invite"
 *     visible="{{showInvitePoster}}"
 *     inviteCode="{{inviteCode}}"
 *     cardImagePath="{{shareCardImage}}"
 *     cardName="{{shareCardName}}"
 *     keyInsight="{{shareKeyInsight}}"
 *     nickname="{{userNickname}}"
 *     bind:close="onCloseInvitePoster"
 *   />
 *
 * Usage (zodiac match poster — mode="zodiac", "星座契合 · 塔罗关系牌"):
 *   <share-poster
 *     mode="zodiac"
 *     visible="{{showMatchPoster}}"
 *     zodiacSigns="{{matchSignsText}}"
 *     cardImagePath="{{matchCardImage}}"
 *     cardName="{{matchCardName}}"
 *     keyInsight="{{matchCompatText}}"
 *     bind:close="onCloseMatchPoster"
 *     bind:share="onShareMatchPoster"
 *   />
 *
 * Usage (diary share poster — mode="diary", "日记精选分享", fully anonymous:
 * mood emoji + date + anonymized excerpt + card thumbnail; no nickname):
 *   <share-poster
 *     mode="diary"
 *     visible="{{showDiarySharePoster}}"
 *     moodEmoji="{{diaryShareData.moodEmoji}}"
 *     dateText="{{diaryShareData.date}}"
 *     cardImagePath="{{diaryShareData.cardImagePath}}"
 *     cardName="{{diaryShareData.cardName}}"
 *     excerpt="{{diaryShareData.excerpt}}"
 *     bind:close="onCloseDiarySharePoster"
 *     bind:share="onShareDiaryPosterToFriend"
 *   />
 *
 * Usage (fortune trend poster — mode="fortune", "我的牌运", personal data
 * 截图物，无小程序码):
 *   <share-poster
 *     mode="fortune"
 *     visible="{{showFortunePoster}}"
 *     fortuneData="{{posterData}}"
 *     nickname="{{userNickname}}"
 *     bind:close="onCloseFortunePoster"
 *     bind:share="onShareFortunePosterToFriend"
 *   />
 *
 * Usage (star card poster — mode="card", "星光名片": 星阶徽章 + 星光数 +
 * 小程序码 from /share/wxacode, footer 仅供娱乐 · 星光映照):
 *   <share-poster
 *     mode="card"
 *     visible="{{showSharePoster}}"
 *     cardImagePath="{{shareCardImage}}"
 *     cardName="{{shareCardName}}"
 *     keyInsight="{{shareKeyInsight}}"
 *     nickname="{{userNickname}}"
 *     starTierName="{{starTierName}}"
 *     stardustTotal="{{stardustTotal}}"
 *     bind:close="onCloseSharePoster"
 *     bind:share="onSharePosterToFriend"
 *   />
 *
 * Usage (月度星光手账海报 — mode="journal", 匿名脱敏数据 + 星阶徽章 +
 * 小程序码 from /share/wxacode, footer 仅供娱乐 · 星光映照):
 *   <share-poster
 *     mode="journal"
 *     visible="{{showPoster}}"
 *     journalData="{{posterData}}"
 *     bind:close="onClosePoster"
 *     bind:share="onSharePosterToFriend"
 *   />
 *
 * Usage (月光卡晚安卡海报 — mode="moon", 深空底晚安版星光名片 +
 * 小程序码 from /share/wxacode, footer 仅供娱乐 · 星光映照):
 *   <share-poster
 *     mode="moon"
 *     visible="{{showMoonPoster}}"
 *     moonCardData="{{posterData}}"
 *     bind:close="onCloseMoonPoster"
 *     bind:share="onShareMoonPosterToFriend"
 *   />
 *
 * fortuneData shape:
 *   {
 *     dateText, totalReadings, mood,
 *     cards: [{name, name_en, count}],
 *     majorCount, minorCount,
 *     suitList: [{name, count}],
 *     trend: [{date, count}]
 *   }
 *
 * journalData shape（来自 /journal/review/share-preview，脱敏）:
 *   {
 *     monthLabel: '八月',
 *     stats: {days_recorded, bright_count, dim_count, bright_ratio},
 *     starColorCounts: [{color, count}],
 *     summary: 'AI/降级 复盘摘要',
 *     starTierName: '星光'
 *   }
 */
const { drawSharePoster } = require('../../utils/canvas-poster');
const { drawJournalPoster } = require('../../utils/journal-poster');
const { drawMoonCardPoster } = require('../../utils/moon-card-poster');

Component({
  properties: {
    visible: {
      type: Boolean,
      value: false,
      observer: '_onVisibleChange',
    },
    mode: {
      type: String,
      value: 'reading', // 'reading' | 'daily' | 'invite' | 'zodiac' | 'diary' | 'fortune' | 'card' | 'journal' | 'moon'
    },
    // journal mode: 月度星光手账海报数据（脱敏）
    journalData: {
      type: null,
      value: {}, // { monthLabel, stats, starColorCounts, summary, starTierName }
    },
    // moon mode: 月光卡晚安卡海报数据（当日月光卡 + 日期行）
    moonCardData: {
      type: null,
      value: {}, // { dateText, card: {date, phase:{emoji,label}, phrase, star_color, star_number, source} }
    },
    starTierName: {
      type: String,
      value: '', // card mode: 星阶名称（微光/星光/星辉/星冠）
    },
    stardustTotal: {
      type: Number,
      value: 0, // card mode: 星光值（星尘总量）
    },
    // type: null — 复杂嵌套对象原样传递，避免运行时将嵌套数组强转为「数字键对象」
    fortuneData: {
      type: null,
      value: {}, // fortune mode: 牌运曲线数据 { dateText, totalReadings, mood, cards, majorCount, minorCount, suitList, trend }
    },
    inviteCode: {
      type: String,
      value: '', // invite mode: user's invite code (STAR-XXXX), baked into QR scene
    },
    zodiacSigns: {
      type: String,
      value: '', // zodiac mode: "♈ + ♉" pairing shown as the poster hero
    },
    cardImagePath: {
      type: String,
      value: '',
    },
    cardName: {
      type: String,
      value: '',
    },
    keyInsight: {
      type: String,
      value: '',
    },
    nickname: {
      type: String,
      value: '',
    },
    dateText: {
      type: String,
      value: '', // daily/diary modes: formatted date, e.g. "2026.07.31"
    },
    streak: {
      type: Number,
      value: 0, // daily mode: consecutive draw days
    },
    moodEmoji: {
      type: String,
      value: '', // diary mode: mood emoji drawn as the poster hero
    },
    excerpt: {
      type: String,
      value: '', // diary mode: anonymized diary excerpt text
    },
  },

  data: {
    previewPath: '',
    drawError: false,
    isDrawing: false,
    canvasW: 0,
    canvasH: 0,
    // 回归修复：同一页面可能出现多个 share-poster 实例（解读结果页「分享海报」
    // + 「送好友一张牌」），若共用固定 canvas id "shareCanvas" 会导致渲染线程
    // 崩溃(白屏/灰屏+JS 冻结)。每个实例生成唯一 canvas id。
    canvasId: '',
  },

  lifetimes: {
    attached() {
      if (!this.data.canvasId) {
        this.setData({
          canvasId: 'shareCanvas_' + Date.now().toString(36) + '_' + Math.floor(Math.random() * 1e6).toString(36),
        });
      }
    },
    // 懒挂载场景（父页面 wx:if 仅在 visible 为 true 时才创建本组件）：
    // 组件挂载时 visible 已是 true，property observer 不会触发（observer 只监听变化），
    // 需要在组件就绪后主动绘制。
    ready() {
      if (this.properties.visible && !this._drewOnMount) {
        this._drewOnMount = true;
        this._initCanvasSize();
        this._drawPoster();
      }
    },
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
        // Reset state when hiding
        this.setData({
          previewPath: '',
          drawError: false,
          isDrawing: false,
        });
      }
    },

    /* ---------------------------------------------------------------
       Determine canvas logical size based on screen width
       --------------------------------------------------------------- */
    _initCanvasSize() {
      const sysInfo = wx.getSystemInfoSync();
      const screenWidth = sysInfo.screenWidth || 375;
      // 3:4 portrait ratio (optimal for Moments)
      const posterW = screenWidth;
      const posterH = Math.round(screenWidth * (4 / 3));
      this.setData({
        canvasW: posterW,
        canvasH: posterH,
      });
    },

    /* ---------------------------------------------------------------
       Draw the poster on canvas using the utility
       --------------------------------------------------------------- */
    _drawPoster() {
      const { mode, cardImagePath, cardName, keyInsight, nickname, dateText, streak, inviteCode, zodiacSigns, moodEmoji, excerpt, fortuneData, journalData, moonCardData, starTierName, stardustTotal } = this.properties;

      // 懒挂载 + visible 初始为 true 时，属性 observer 可能在 attached() 生成
      // canvasId 之前触发（部分基础库版本对初始属性值也触发 observer）——
      // 绘制前兜底生成，保证 canvasId 恒存在。
      if (!this.data.canvasId) {
        this.setData({
          canvasId: 'shareCanvas_' + Date.now().toString(36) + '_' + Math.floor(Math.random() * 1e6).toString(36),
        });
      }

      // Card image is optional in diary/fortune/journal/moon modes — data-only
      // posters (mood emoji + excerpt / fortune trend / 月度星光手账 / 月光卡晚安卡) are valid.
      if (!cardImagePath && !cardName && mode !== 'diary' && mode !== 'fortune' && mode !== 'journal' && mode !== 'moon') {
        this.setData({ drawError: true });
        return;
      }

      this.setData({ isDrawing: true, drawError: false });

      // 月光卡晚安卡海报：深空底晚安版星光名片（moon-card-poster.js，独立绘制管线）
      if (mode === 'moon') {
        const md = moonCardData || {};
        drawMoonCardPoster(this.data.canvasId, this, {
          dateText: md.dateText || '',
          card: md.card || {},
          onSuccess: (tempFilePath) => {
            this.setData({
              previewPath: tempFilePath,
              isDrawing: false,
              drawError: false,
            });
          },
          onError: (err) => {
            console.error('[share-poster] Moon draw error:', err);
            this.setData({
              drawError: true,
              isDrawing: false,
            });
          },
        });
        return;
      }

      // 月度星光手账海报：独立绘制管线（journal-poster.js，复用 E3 调色板）
      if (mode === 'journal') {
        const jd = journalData || {};
        drawJournalPoster(this.data.canvasId, this, {
          monthLabel: jd.monthLabel || '',
          stats: jd.stats || {},
          starColorCounts: jd.starColorCounts || [],
          summary: jd.summary || '',
          starTierName: jd.starTierName || '',
          onSuccess: (tempFilePath) => {
            this.setData({
              previewPath: tempFilePath,
              isDrawing: false,
              drawError: false,
            });
          },
          onError: (err) => {
            console.error('[share-poster] Journal draw error:', err);
            this.setData({
              drawError: true,
              isDrawing: false,
            });
          },
        });
        return;
      }

      drawSharePoster(this.data.canvasId, {
        context: this,
        mode: mode || 'reading',
        cardImagePath: cardImagePath || '',
        cardName: cardName || '',
        keyInsight: keyInsight || '',
        nickname: nickname || '',
        dateText: dateText || '',
        streak: streak || 0,
        inviteCode: inviteCode || '',
        zodiacSigns: zodiacSigns || '',
        moodEmoji: moodEmoji || '',
        excerpt: excerpt || '',
        fortuneData: fortuneData || {},
        starTierName: starTierName || '',
        stardustTotal: stardustTotal || 0,
        onSuccess: (tempFilePath) => {
          this.setData({
            previewPath: tempFilePath,
            isDrawing: false,
            drawError: false,
          });
        },
        onError: (err) => {
          console.error('[share-poster] Draw error:', err);
          this.setData({
            drawError: true,
            isDrawing: false,
          });
        },
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
            // User denied permission — guide them to settings
            wx.showModal({
              title: '需要相册权限',
              content: '请在设置中开启相册权限，以便保存海报到相册',
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
       Share poster to friends (trigger page-level share)
       --------------------------------------------------------------- */
    onShare() {
      const { previewPath } = this.data;
      if (!previewPath) return;

      // Trigger the page-level onShareAppMessage with the poster image
      this.triggerEvent('share', { imagePath: previewPath });
    },

    /* ---------------------------------------------------------------
       Close / dismiss
       --------------------------------------------------------------- */
    onClose() {
      this.triggerEvent('close');
    },

    /* ---------------------------------------------------------------
       Retry drawing after error
       --------------------------------------------------------------- */
    onRetry() {
      this._drawPoster();
    },
  },
});
