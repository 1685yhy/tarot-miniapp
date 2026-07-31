/**
 * Annual Report Page — Spotify Wrapped-style experience
 *
 * 8-screen swipeable story format with entrance animations, particle effects,
 * and a share poster generator at the end.
 *
 * Screens:
 *   0: Intro — "你的星光年度报告", cosmic animation
 *   1: Total readings reveal  — "这一年，你一共占卜了 N 次"
 *   2: Top theme  — "你最常思考的是 · XX"
 *   3: Annual card — "你的年度之牌" with card image
 *   4: Personality — "你的塔罗人格 · XX"
 *   5: Monthly chart — CSS bar chart
 *   6: New year blessing — AI blessing in beautiful typography
 *   7: Share — poster + share buttons
 */

const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { computeImagePath, findCard, pngFallbackPath } = require('../../utils/cards');
const { drawSharePoster } = require('../../utils/canvas-poster');
const { playCardRevealSound, playMilestoneSound } = require('../../utils/sound');

const TOTAL_SCREENS = 8;
const AUTO_ADVANCE_DELAY = 6000; // ms per screen in auto mode

Page({
  data: {
    // State
    pageLoading: true,
    pageError: null,
    generating: false,
    report: null,

    // Screen management
    currentScreen: 0,
    totalScreens: TOTAL_SCREENS,
    screenProgress: [],

    // Animation flags (per screen entrance)
    screenVisible: false,
    showBigNumber: false,
    showCardReveal: false,
    showSparkle: false,
    chartAnimated: false,

    // Card images
    annualCardImagePath: '',
    annualCardName: '',
    annualCardSuit: '',
    annualCardImgError: false,

    // Share poster
    showSharePoster: false,
    sharePosterPath: '',
    sharePosterDrawing: false,

    // Year
    year: new Date().getFullYear(),
    // Chart data enhancement
    maxMonthlyCount: 10,
    themeIcons: {
      love: '/images/icons/theme_love_64.png',
      career: '/images/icons/theme_career_64.png',
      finance: '/images/icons/theme_finance_64.png',
      general: '/images/icons/theme_general_64.png',
    },
    soundEnabled: true,
    isMember: false,
  },

  // ── Screen labels (for progress dots) ──
  screenLabels: [
    '星 光 年 度 报 告',
    '占 卜 次 数',
    '最 常 思 考',
    '年 度 之 牌',
    '塔 罗 人 格',
    '月 度 运 势',
    '新 年 寄 语',
    '分 享',
  ],

  async onLoad() {
    // Check login
    try {
      const user = await checkLogin();
      this.setData({
        isMember: !!user.is_member,
        year: new Date().getFullYear(),
      });
    } catch (_) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      this.setData({ pageLoading: false });
      return;
    }

    // Try cached report
    try {
      const cached = wx.getStorageSync('annual_report_wrapped');
      if (cached && cached.year === this.data.year) {
        this.setData({
          report: cached,
          pageLoading: false,
          screenProgress: Array(TOTAL_SCREENS).fill(false),
        });
        this._initCardImages();
        return;
      }
    } catch (_) {}

    this.setData({ pageLoading: false });
  },

  onReady() {
    // Pre-start ambient / transition sounds reserved
  },

  onUnload() {
    this._clearTimers();
  },

  onHide() {
    this._clearTimers();
  },

  // ════════════════════════════════════════════════════════════════
  //  DATA LOADING
  // ════════════════════════════════════════════════════════════════

  async onGenerate() {
    if (this.data.generating) return;
    this.setData({ generating: true, pageLoading: false });

    try {
      const report = await request('/report/annual?regenerate=true');
      this.setData({
        report,
        generating: false,
        currentScreen: 0,
        screenProgress: Array(TOTAL_SCREENS).fill(false),
        screenVisible: false,
        showBigNumber: false,
        showCardReveal: false,
        showSparkle: false,
        chartAnimated: false,
      });
      wx.setStorageSync('annual_report_wrapped', report);
      this._initCardImages();
      this._startAutoAdvance();

      // Play entrance chime
      playMilestoneSound(true);
    } catch (err) {
      this.setData({ generating: false });
      if (err.statusCode === 402) {
        wx.showModal({
          title: '会员专属',
          content: '年度运势报告仅限会员使用',
          confirmText: '开通会员',
          success: (res) => {
            if (res.confirm) {
              wx.navigateTo({ url: '/pages/membership/membership' });
            }
          },
        });
      } else {
        wx.showToast({ title: '生成失败', icon: 'none' });
        this.setData({ pageError: getFriendlyError(err) });
      }
    }
  },

  _initCardImages() {
    const report = this.data.report;
    if (!report) return;

    // Compute max monthly count for chart scaling
    if (report.monthly_chart && report.monthly_chart.length > 0) {
      const counts = report.monthly_chart.map(m => m.count || 0);
      const maxCount = Math.max(...counts, 1);
      this.setData({ maxMonthlyCount: maxCount });
    }

    if (!report.annual_theme_card) return;
    const card = report.annual_theme_card;
    const cardName = card.name || '';
    const found = findCard(cardName);
    let imagePath = '';
    if (found && found.image) {
      imagePath = found.image;
    } else {
      imagePath = computeImagePath({
        name_en: card.name_en || '',
        arcana: card.arcana || 'major',
        suit: card.suit || null,
        card_number: 0,
      });
    }

    this.setData({
      annualCardImagePath: imagePath,
      annualCardName: cardName,
      annualCardSuit: card.suit || card.arcana || 'major',
      annualCardImgError: false,
    });
  },

  onAnnualCardImgError() {
    // Retry once with PNG fallback before hiding the annual card image
    const current = this.data.annualCardImagePath;
    if (current && current.endsWith('.webp') && !this.data.webpFallbackTried) {
      this.setData({ webpFallbackTried: true, annualCardImagePath: pngFallbackPath(current) });
      return;
    }
    this.setData({ annualCardImgError: true });
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  // ════════════════════════════════════════════════════════════════
  //  SCREEN NAVIGATION
  // ════════════════════════════════════════════════════════════════

  _startAutoAdvance() {
    this._clearTimers();
    this._advanceTimer = setInterval(() => {
      if (this.data.currentScreen < TOTAL_SCREENS - 1) {
        this.goNextScreen();
      }
    }, AUTO_ADVANCE_DELAY);
  },

  goNextScreen() {
    if (this.data.currentScreen >= TOTAL_SCREENS - 1) return;
    this._progressTo(this.data.currentScreen + 1);
  },

  goPrevScreen() {
    if (this.data.currentScreen <= 0) return;
    this._progressTo(this.data.currentScreen - 1);
  },

  onScreenTap(e) {
    // Tap right half = next, left half = prev
    const touch = e.changedTouches ? e.changedTouches[0] : null;
    if (touch) {
      const screenW = wx.getSystemInfoSync().screenWidth || 375;
      if (touch.clientX > screenW * 0.5) {
        this.goNextScreen();
      } else {
        this.goPrevScreen();
      }
    } else {
      this.goNextScreen();
    }
  },

  onSwipe(e) {
    // Fallback swipe handler
    if (!e || !e.detail) return;
    if (e.detail.direction === 'left') {
      this.goNextScreen();
    } else if (e.detail.direction === 'right') {
      this.goPrevScreen();
    }
  },

  _progressTo(screenIndex) {
    if (screenIndex < 0 || screenIndex >= TOTAL_SCREENS) return;
    this._clearTimers();
    this.setData({ currentScreen: screenIndex });

    // Trigger entrance animation
    this._triggerScreenAnimation(screenIndex);

    // Restart auto-advance if not on the last screen
    if (screenIndex < TOTAL_SCREENS - 1) {
      this._startAutoAdvance();
    }
  },

  _triggerScreenAnimation(screenIndex) {
    switch (screenIndex) {
      case 0:
        this.setData({ screenVisible: true });
        break;
      case 1:
        // Animate number count up after a small delay
        this.setData({ showBigNumber: false });
        setTimeout(() => {
          this.setData({ showBigNumber: true });
          playCardRevealSound();
        }, 500);
        break;
      case 2:
        this.setData({ showSparkle: false });
        setTimeout(() => {
          this.setData({ showSparkle: true });
        }, 300);
        break;
      case 3:
        this.setData({ showCardReveal: false });
        setTimeout(() => {
          this.setData({ showCardReveal: true });
          playMilestoneSound(true);
        }, 400);
        break;
      case 4:
        this.setData({ screenVisible: true });
        break;
      case 5:
        this.setData({ chartAnimated: false });
        setTimeout(() => {
          this.setData({ chartAnimated: true });
        }, 300);
        break;
      case 6:
        this.setData({ screenVisible: true });
        break;
      case 7:
        this.setData({ screenVisible: true });
        break;
    }
  },

  // ════════════════════════════════════════════════════════════════
  //  SHARE / POSTER
  // ════════════════════════════════════════════════════════════════

  onShowSharePoster() {
    this.setData({ showSharePoster: true });
    this._generateSharePoster();
  },

  onCloseSharePoster() {
    this.setData({ showSharePoster: false, sharePosterPath: '' });
  },

  _generateSharePoster() {
    const report = this.data.report;
    if (!report) return;

    this.setData({ sharePosterDrawing: true });

    const nickname = wx.getStorageSync('user')?.nickname || '星光旅人';
    const cardName = this.data.annualCardName || '命运之轮';
    const topTheme = report.top_themes && report.top_themes.length > 0
      ? report.top_themes[0].label
      : '未知';
    const blessing = report.new_year_blessing || '愿星光指引你的前路';

    const keyInsight = `我的${report.year}年度之牌 · ${cardName} - ${report.total_readings}次占卜, 最关注${topTheme}`;

    drawSharePoster('annualShareCanvas', {
      context: this,
      cardImagePath: this.data.annualCardImagePath || '',
      cardName: `我的${report.year}年度之牌 · ${cardName}`,
      keyInsight: `"${blessing}"`,
      nickname: nickname,
      onSuccess: (tempFilePath) => {
        this.setData({
          sharePosterPath: tempFilePath,
          sharePosterDrawing: false,
        });
      },
      onError: (err) => {
        console.error('[annual-report] Poster error:', err);
        this.setData({ sharePosterDrawing: false });
        wx.showToast({ title: '海报生成失败', icon: 'none' });
      },
    });
  },

  onSavePoster() {
    const path = this.data.sharePosterPath;
    if (!path) return;

    wx.saveImageToPhotosAlbum({
      filePath: path,
      success: () => {
        wx.showToast({ title: '已保存到相册', icon: 'success' });
      },
      fail: (err) => {
        if (err.errMsg && err.errMsg.indexOf('auth deny') !== -1) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在设置中开启相册权限，以便保存海报到相册',
            confirmText: '去设置',
            success: (res) => {
              if (res.confirm) wx.openSetting();
            },
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      },
    });
  },

  onShareTimeline() {
    // WeChat Moments share — handled by onShareAppMessage
    wx.showToast({ title: '点击右上角分享到朋友圈', icon: 'none' });
  },

  onShareAppMessage() {
    const report = this.data.report;
    const cardName = report?.annual_theme_card?.name || '年度之牌';
    const count = report?.total_readings || 0;
    return {
      title: `我的星光年度报告 — ${count}次占卜，年度之牌「${cardName}」✨`,
      desc: 'AI星光年度运势报告',
      path: '/pages/annual-report/annual-report',
    };
  },

  onBuySingle() {
    wx.navigateTo({ url: '/pages/membership/membership?product=annual_report' });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  // ════════════════════════════════════════════════════════════════
  //  UTILITY
  // ════════════════════════════════════════════════════════════════

  _clearTimers() {
    if (this._advanceTimer) {
      clearInterval(this._advanceTimer);
      this._advanceTimer = null;
    }
  },
});
