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
 */
const { drawSharePoster } = require('../../utils/canvas-poster');

Component({
  properties: {
    visible: {
      type: Boolean,
      value: false,
      observer: '_onVisibleChange',
    },
    mode: {
      type: String,
      value: 'reading', // 'reading' | 'daily'
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
      value: '', // daily mode: formatted date, e.g. "2026.07.31"
    },
    streak: {
      type: Number,
      value: 0, // daily mode: consecutive draw days
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
      const { mode, cardImagePath, cardName, keyInsight, nickname, dateText, streak } = this.properties;

      // Use the first card image; if cardImagePath is empty, skip
      if (!cardImagePath && !cardName) {
        this.setData({ drawError: true });
        return;
      }

      this.setData({ isDrawing: true, drawError: false });

      drawSharePoster('shareCanvas', {
        context: this,
        mode: mode || 'reading',
        cardImagePath: cardImagePath || '',
        cardName: cardName || '',
        keyInsight: keyInsight || '',
        nickname: nickname || '',
        dateText: dateText || '',
        streak: streak || 0,
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
