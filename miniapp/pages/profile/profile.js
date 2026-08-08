// pages/profile/profile.js
const perf = require('../../utils/performance');
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { computeImagePath, findCard } = require('../../utils/cards');
const sound = require('../../utils/sound');
const { getZodiacBadge } = require('../../utils/energy');

// 三位塔罗师信息（与 backend ai_personas.py 保持一致）
const PERSONA_INFO = {
  gentle_star: { icon: '✦', name: '温和的星', desc: '温暖陪伴 · 适合情感话题' },
  wise_moon:   { icon: '☽', name: '智慧的月', desc: '理性分析 · 适合事业决策' },
  frank_sun:   { icon: '☀', name: '率直的太阳', desc: '直击要害 · 敢于面对真相' },
};

// 牌阵英文键名到中文显示名的映射
const SPREAD_TYPE_NAMES = {
  three_card: '三牌占卜',
  triangle: '恋人三角',
  celtic_cross: '凯尔特十字',
  career: '事业牌阵',
  finance: '财运牌阵',
  decision: '二择一',
  life_cross: '人生十字',
  horseshoe: '马蹄牌阵',
  relationship: '关系牌阵',
  year_ahead: '年度运势',
  daily: '每日占卜',
  career_path: '事业路线',
  weekly_outlook: '周运势',
  love_reading: '爱情占卜',
  fortune_telling: '财运占卜',
};

function computeCardImage(firstCardName) {
  if (!firstCardName) return '';
  const found = findCard(firstCardName);
  return found && found.image ? found.image : '';
}

Page({
  data: {
    user: null,
    memberStatus: null,
    readingHistory: [],
    pageLoading: true,
    pageError: null,
    historyPage: 1,
    hasMore: true,
    loadingMore: false,
    historyTotal: 0,
    spreadTypeNames: SPREAD_TYPE_NAMES,

    // Saved readings
    savedReadings: [],
    savedReadingsLoading: false,

    // Favorites count
    favoriteCount: 0,

    // Sound settings
    soundEnabled: true,

    // Ambient sound
    ambientEnabled: false,

    // Draw mode preference
    defaultDrawMode: 'quick',

    // Annual report notification reminder
    yearEndReminderEnabled: false,

    // Annual report season flag
    isAnnualReportSeason: false,
    annualReportYear: new Date().getFullYear(),

    // Invite / share rewards
    inviteRewards: 0,

    // Push notification settings
    pushDailyCard: false,
    pushMemberExpire: false,
    pushAnnualReport: false,

    // Membership benefits data
    memberBenefits: [
      { icon: '✨', text: '已解锁 10 种牌阵' },
      { icon: '💬', text: '无限 AI 追问' },
      { icon: '🎭', text: '3 位专属塔罗师' },
      { icon: '📊', text: '年度运势报告' },
    ],
    lockedBenefits: [
      { icon: '✨', text: '10 种牌阵' },
      { icon: '💬', text: '无限 AI 追问' },
      { icon: '🎭', text: '3 位专属塔罗师' },
      { icon: '📊', text: '年度运势报告' },
      { icon: '🔮', text: '深度 AI 解读' },
    ],

    // Your Tarot Readers — persona usage stats
    personaStats: [],
    mostUsedPersona: null,
    mostUsedPersonaCount: 0,

    // 我的星光之旅 stats
    streak: 0,
    collectionCount: 0,
    totalReadings: 0,
    diaryCount: 0,

    // 我的牌运 — 牌运曲线入口摘要（留存功能第一批）
    fortuneTotal: 0,
    fortuneMood: '',

    // AI 周回顾 — 星光周报分享长图
    showWeeklyPoster: false,
    weeklyReportData: null,
    weeklyCardImage: '',
    weeklyLoading: false,

    // 我的星象：星座徽章 + 出生信息（前端改造第一阶段）
    zodiacBadge: '',
    birthInfo: null,       // { date, time, city, zodiac }
  },

  // —— History card image loading ——
  onHistoryImgLoad(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`readingHistory[${idx}]._imgLoaded`]: true });
    }
  },

  onHistoryImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`readingHistory[${idx}]._imgError`]: true });
    }
  },

  async onShow() {
    await this.loadData();
    // 我的星象：从 storage 同步星座徽章与出生信息
    this._loadStarProfile();
    // Sync sound state from sound module
    this.setData({
      soundEnabled: sound.sfxEnabled,
      ambientEnabled: sound.ambientEnabled,
      defaultDrawMode: wx.getStorageSync('default_draw_mode') || 'quick',
      yearEndReminderEnabled: wx.getStorageSync('year_end_reminder') === true,
      isAnnualReportSeason: false,
    });

    // Load push subscription status from storage
    this._loadPushSettings();

    // Check annual report season (Dec-Jan)
    const month = new Date().getMonth() + 1;
    const year = new Date().getFullYear();
    if (month === 12 || month === 1) {
      this.setData({
        isAnnualReportSeason: true,
        annualReportYear: month === 1 ? year - 1 : year,
      });
    }
  },

  async loadData() {
    this.setData({ pageLoading: true });
    try {
      const user = await checkLogin();
      const [status, history, shareStats] = await Promise.all([
        request('/membership/status'),
        request('/readings/history?page=1&page_size=20'),
        request('/share/stats?days=365'),
      ]);
      // Subtle entrance chime
      sound.playPageEnterSound();

      // Load invite rewards from share stats
      const inviteRewards = shareStats?.free_deep_readings || 0;

      // 我的星光之旅 — streak (same local source as the home daily card)
      let storedStreak = 0;
      try {
        storedStreak = wx.getStorageSync('streak') || 0;
      } catch (_e) {
        storedStreak = 0;
      }
      // 已收集 N/78 张牌 — collection spans the full 78-card encyclopedia
      let collectionCount = 0;
      try {
        const favIds = wx.getStorageSync('favorite_cards') || [];
        collectionCount = favIds.length;
      } catch (_e) {
        collectionCount = 0;
      }

      this.setData({
        user,
        memberStatus: status ? {
          ...status,
          expiresAtFormatted: status.expires_at ? status.expires_at.split('T')[0] : '',
        } : null,
        readingHistory: (history.items || []).map(item => ({
          ...item,
          spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
          firstCardImage: computeCardImage(item.first_card_name),
          createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
        })),
        inviteRewards,
        historyTotal: history.total || (history.items ? history.items.length : 0),
        streak: storedStreak,
        collectionCount,
        totalReadings: history.total || (history.items ? history.items.length : 0),
        pageLoading: false,
        historyPage: 1,
        hasMore: history.items ? history.items.length >= 20 : false,
      });

      // Diary count — fetched in background (list API is paginated, no total field)
      this._loadDiaryCount();

      // Compute persona usage stats from history
      this._computePersonaStats(history.items || []);
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }

    // Also load saved readings from local storage
    this._loadSavedReadings();
    this._loadFavoriteCount();

    // 我的牌运 — 入口摘要（独立请求，失败静默降级，不影响整页）
    this._loadFortuneTrend();
  },

  /** 拉取牌运曲线摘要（近 30 天解读次数 + 一句话总结） */
  async _loadFortuneTrend() {
    try {
      const data = await request('/readings/fortune-trend?days=30');
      this.setData({
        fortuneTotal: data.total_readings || 0,
        fortuneMood: data.mood || '星光同行',
      });
    } catch (_err) {
      // Silent degrade — 入口卡显示默认值
    }
  },

  /** 进入「我的牌运」页（牌运曲线 · 个人数据资产） */
  onGoFortuneTrend() {
    wx.navigateTo({ url: '/pages/fortune-trend/fortune-trend' });
  },

  _loadFavoriteCount() {
    try {
      const favoriteIds = wx.getStorageSync('favorite_cards') || [];
      this.setData({ favoriteCount: favoriteIds.length });
    } catch (_e) {
      this.setData({ favoriteCount: 0 });
    }
  },

  /** 我的星光之旅 — diary entry count (paginated API, no total; cap at 10 pages) */
  async _loadDiaryCount() {
    let total = 0;
    try {
      for (let page = 1; page <= 10; page++) {
        const data = await request(`/diary/entries?page=${page}`);
        const entries = data.entries || [];
        total += entries.length;
        if (entries.length < 20) break; // last page reached
      }
    } catch (_err) {
      // Silent degrade — keep count at 0
    }
    this.setData({ diaryCount: total });
  },

  async _loadSavedReadings() {
    let savedIds;
    try {
      savedIds = wx.getStorageSync('saved_readings') || [];
    } catch (_e) {
      savedIds = [];
    }
    if (!savedIds.length) {
      this.setData({ savedReadings: [], savedReadingsLoading: false });
      return;
    }
    this.setData({ savedReadingsLoading: true });
    try {
      // Fetch each saved reading's detail from API (limit to 20 for perf)
      const batch = savedIds.slice(0, 20);
      const results = await Promise.allSettled(
        batch.map(id => request(`/readings/${id}`))
      );
      const readings = results
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value)
        .filter(Boolean)
        .map(item => ({
          ...item,
          spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type || '占卜',
          createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
        }));
      this.setData({ savedReadings: readings, savedReadingsLoading: false });
    } catch (err) {
      this.setData({ savedReadingsLoading: false });
    }
  },

  async onScrollToBottom() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    const nextPage = this.data.historyPage + 1;
    try {
      const history = await request(`/readings/history?page=${nextPage}&page_size=20`);
      this.setData({
        readingHistory: this.data.readingHistory.concat(
          (history.items || []).map(item => ({
            ...item,
            spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
            firstCardImage: computeCardImage(item.first_card_name),
            createdAtFormatted: item.created_at ? item.created_at.split('T')[0] : '',
          }))
        ),
        historyPage: nextPage,
        hasMore: history.items ? history.items.length >= 20 : false,
        loadingMore: false,
      });
    } catch (err) {
      this.setData({ loadingMore: false });
      wx.showToast({ title: '加载更多失败', icon: 'none' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadData();
  },

  /** AI 周回顾 — 拉取本周数据并打开「我的星光一周」分享长图 */
  async onShareWeeklyReport() {
    if (this.data.weeklyLoading) return;
    this.setData({ weeklyLoading: true });
    try {
      const report = await request('/report/weekly');
      if (!report || !report.has_data) {
        wx.showToast({
          title: '本周还没有星光记录，先来占卜或写日记吧',
          icon: 'none',
          duration: 2500,
        });
        return;
      }
      // 常遇之牌图片 — 由前端卡牌注册表计算 CDN 路径
      let cardImage = '';
      if (report.most_frequent_card && report.most_frequent_card.name) {
        cardImage = computeCardImage(report.most_frequent_card.name);
      }
      this.setData({
        weeklyReportData: report,
        weeklyCardImage: cardImage,
        showWeeklyPoster: true,
      });
    } catch (err) {
      const msg = getFriendlyError(err);
      wx.showToast({ title: msg || '周报生成失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ weeklyLoading: false });
    }
  },

  onCloseWeeklyPoster() {
    this.setData({ showWeeklyPoster: false });
  },

  /** 分享周报长图给朋友 — 用户主动分享，无诱导文案 */
  onShareWeeklyPoster(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    // wx.showShareImageMenu — 小程序原生分享图片菜单（基础库 2.14.0+）
    if (wx.showShareImageMenu) {
      wx.showShareImageMenu({
        path: imagePath,
        fail: () => {
          wx.showToast({
            title: '请先保存海报，再从相册分享',
            icon: 'none',
            duration: 2000,
          });
        },
      });
    } else {
      wx.showToast({
        title: '请先保存海报，再从相册分享',
        icon: 'none',
        duration: 2000,
      });
    }
  },

  /** 我的星象：同步星座徽章 + 出生信息（storage 为准） */
  _loadStarProfile() {
    let birthInfo = null;
    try { birthInfo = wx.getStorageSync('birth_info') || null; } catch (e) { /* silent */ }
    this.setData({
      zodiacBadge: getZodiacBadge(),
      birthInfo,
    });
  },

  /** 我的星座（可改）→ 复用星座网格页（change 模式） */
  onGoZodiac() {
    wx.navigateTo({ url: '/pages/zodiac-welcome/zodiac-welcome?from=change' });
  },

  /** 完善出生信息（日期自动推导星座） */
  onGoBirthInfo() {
    wx.navigateTo({ url: '/pages/birth-info/birth-info' });
  },

  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onGoToReading() {
    wx.navigateTo({ url: '/pages/reading/reading' });
  },

  onViewReading(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/reading-result/reading-result?id=${id}` });
  },

  onGoFavorites() {
    // Use globalData to signal favorites filter (百科已改为普通页面，navigateTo 进入)
    const app = getApp();
    app.globalData.showCardFavorites = true;
    wx.navigateTo({ url: '/pages/encyclopedia/encyclopedia' });
  },

  onGoDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  /** P3-1: 每日签到入口 */
  onGoCheckin() {
    wx.navigateTo({ url: '/pages/checkin/checkin' });
  },

  onGoAnnualReport() {
    const app = getApp();
    const user = app.globalData.user;
    if (!user || !user.is_member) {
      wx.showToast({ title: '会员专属功能', icon: 'none' });
      wx.navigateTo({ url: '/pages/membership/membership' });
      return;
    }
    wx.navigateTo({ url: '/pages/annual-report/annual-report' });
  },

  onToggleYearEndReminder() {
    const newVal = !this.data.yearEndReminderEnabled;
    wx.setStorageSync('year_end_reminder', newVal);
    this.setData({ yearEndReminderEnabled: newVal });
    wx.showToast({
      title: newVal ? '已开启年度报告提醒' : '已关闭年度报告提醒',
      icon: 'none',
      duration: 1500,
    });
  },

  onGoShareCenter() {
    wx.navigateTo({ url: '/pages/share-center/share-center' });
  },

  onGoAbout() {
    wx.navigateTo({ url: '/pages/about/about' });
  },

  /**
   * 退出登录：请求后端使 token 失效（后端已实现 token_version 机制时生效；
   * 若后端暂无 /auth/logout 接口则忽略失败），无论如何都清除本地登录态并回首页。
   */
  async onLogout() {
    try {
      await request('/auth/logout', { method: 'POST' });
    } catch (err) {
      // 后端尚未提供登出接口（404 等）时，降级为本地登出，不影响用户退出
      console.warn('[profile] 后端登出接口调用失败，执行本地登出:', err.message);
    }
    wx.removeStorageSync('token');
    wx.removeStorageSync('user');
    wx.showToast({ title: '已退出登录', icon: 'success' });
    setTimeout(() => {
      wx.reLaunch({ url: '/pages/index/index' });
    }, 600);
  },

  /**
   * 注销账号：双重确认（说明弹窗 + 输入"注销"二字）后调用 DELETE /auth/me，
   * 成功后清空全部本地数据并回到首页。
   * 注销文案与隐私政策承诺一致：注销后数据将被删除或匿名化处理。
   */
  async onDeleteAccount() {
    // 第一重确认：告知后果
    const first = await new Promise((resolve) => {
      wx.showModal({
        title: '注销账号',
        content: '注销后，您的解读记录、日记、会员权益等数据将被删除或匿名化处理，且不可恢复。确定继续吗？',
        confirmText: '继续',
        confirmColor: '#e64340',
        cancelText: '取消',
        success: resolve,
      });
    });
    if (!first.confirm) return;

    // 第二重确认：输入「注销」二字，防止误触
    const second = await new Promise((resolve) => {
      wx.showModal({
        title: '再次确认注销',
        content: '请输入「注销」二字以确认注销账号',
        editable: true,
        placeholderText: '请输入：注销',
        confirmText: '确认注销',
        confirmColor: '#e64340',
        success: resolve,
      });
    });
    if (!second.confirm) return;
    if (String(second.content || '').trim() !== '注销') {
      wx.showToast({ title: '输入不正确，已取消注销', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '注销中...', mask: true });
    try {
      await request('/auth/me', { method: 'DELETE' });
      wx.clearStorageSync(); // 清空全部本地数据
      wx.hideLoading();
      wx.showToast({ title: '账号已注销', icon: 'success' });
      setTimeout(() => {
        wx.reLaunch({ url: '/pages/index/index' });
      }, 1200);
    } catch (err) {
      wx.hideLoading();
      wx.showToast({
        title: getFriendlyError(err) || '注销失败，请稍后重试',
        icon: 'none',
        duration: 2500,
      });
    }
  },

  onToggleSound() {
    const newVal = sound.toggleSfx();
    this.setData({ soundEnabled: newVal });
    wx.showToast({
      title: newVal ? '音效已开启' : '音效已关闭',
      icon: 'none',
      duration: 1500,
    });
  },

  onToggleAmbient() {
    const newVal = sound.toggleAmbient();
    this.setData({ ambientEnabled: newVal });
    wx.showToast({
      title: newVal ? '星空环境音已开启 🌙' : '星空环境音已关闭',
      icon: 'none',
      duration: 1500,
    });
  },

  onToggleDrawMode() {
    const currentMode = this.data.defaultDrawMode;
    const newMode = currentMode === 'immersive' ? 'quick' : 'immersive';
    wx.setStorageSync('default_draw_mode', newMode);
    this.setData({ defaultDrawMode: newMode });
    wx.showToast({
      title: newMode === 'immersive' ? '已切换为沉浸解读' : '已切换为快速抽牌',
      icon: 'none',
      duration: 1500,
    });
  },

  async onClearHistory() {
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: '清除记录',
        content: '确定清除所有占卜历史记录吗？此操作不可恢复。',
        success: resolve,
      });
    });
    if (!res.confirm) return;

    try {
      await request('/readings/history', { method: 'DELETE' });
      this.setData({ readingHistory: [] });
      wx.showToast({ title: '已清除', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '清除失败', icon: 'none' });
    }
  },

  onClearSavedReadings() {
    wx.showModal({
      title: '清除收藏',
      content: '确定清除所有收藏的解读吗？',
      success: (res) => {
        if (!res.confirm) return;
        wx.setStorageSync('saved_readings', []);
        this.setData({ savedReadings: [] });
        wx.showToast({ title: '已清除', icon: 'success' });
      },
    });
  },

  /** Compute persona usage stats from reading history items */
  _computePersonaStats(historyItems) {
    const personaCount = {};
    (historyItems || []).forEach(item => {
      if (item.persona && PERSONA_INFO[item.persona]) {
        personaCount[item.persona] = (personaCount[item.persona] || 0) + 1;
      }
    });

    const stats = Object.entries(personaCount)
      .filter(([key]) => PERSONA_INFO[key])
      .map(([key, count]) => ({ key, ...PERSONA_INFO[key], count }))
      .sort((a, b) => b.count - a.count);

    const mostUsed = stats.length > 0 ? stats[0] : null;

    this.setData({
      personaStats: stats,
      mostUsedPersona: mostUsed ? { name: mostUsed.name, icon: mostUsed.icon } : null,
      mostUsedPersonaCount: mostUsed ? mostUsed.count : 0,
    });
  },

  // ---- Push notification settings ----

  /** Load push subscription status from local storage */
  _loadPushSettings() {
    const pushDailyCard = wx.getStorageSync('push_daily_subscribed') === true;
    const pushMemberExpire = wx.getStorageSync('push_member_expire') === true;
    const pushAnnualReport = wx.getStorageSync('push_annual_report') === true;
    this.setData({
      pushDailyCard,
      pushMemberExpire,
      pushAnnualReport,
    });
  },

  /** Subscribe to daily card push */
  onSubscribeDailyCard() {
    wx.requestSubscribeMessage({
      tmplIds: ['TEMPLATE_DAILY_CARD'],
      success: (res) => {
        const accepted = res['TEMPLATE_DAILY_CARD'] === 'accept';
        wx.setStorageSync('push_daily_subscribed', accepted);
        this.setData({ pushDailyCard: accepted });
        wx.showToast({
          title: accepted ? '已开启每日推送 ✦' : '已关闭每日推送',
          icon: 'none',
          duration: 1500,
        });
        // Report to backend
        this._reportSubscription('TEMPLATE_DAILY_CARD', accepted);
      },
      fail: () => {
        // Silent degrade
      },
    });
  },

  /** Open WeChat settings page so user can manage notification permissions */
  onOpenPushSettings() {
    wx.openSetting({
      success: (res) => {
        // Check subscription settings after returning
        this._loadPushSettings();
        wx.showToast({ title: '设置已更新', icon: 'none', duration: 1500 });
      },
    });
  },

  /** Report subscription status to backend */
  async _reportSubscription(templateId, accepted) {
    try {
      const user = wx.getStorageSync('user');
      const openid = user?.openid || '';
      if (!openid) return;
      await request('/notify/subscribe', {
        method: 'POST',
        data: {
          openid,
          template_id: templateId,
          accept: accepted,
        },
      });
    } catch (_err) {
      // Silent degrade
    }
  },

  onReady() {
    // Performance monitoring: page ready timestamp
    perf.markPageReady('profile');
  },
});
