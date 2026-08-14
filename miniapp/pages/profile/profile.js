// pages/profile/profile.js
const perf = require('../../utils/performance');
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const analytics = require('../../utils/analytics');
const { computeImagePath, findCard } = require('../../utils/cards');
const sound = require('../../utils/sound');
const { getZodiacBadge } = require('../../utils/energy');
const { SLOT_INFO } = require('../../utils/config');

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

// 星阶阈值映射（与 backend app/services/stardust.py STAR_TIERS 一致：0微光/7星光/30星辉/100星冠）
const STAR_TIERS = [
  { threshold: 0, name: '微光' },
  { threshold: 7, name: '星光' },
  { threshold: 30, name: '星辉' },
  { threshold: 100, name: '星冠' },
];

/** 当前星阶名（按累计星尘取最近阈值） */
function currentTierName(stardust) {
  let name = '微光';
  for (const t of STAR_TIERS) {
    if (stardust >= t.threshold) name = t.name;
  }
  return name;
}

/** 下一星阶信息（{name, need}），已到星冠返回 null */
function nextTierInfo(stardust) {
  for (const t of STAR_TIERS) {
    if (stardust < t.threshold) return { name: t.name, need: t.threshold - stardust };
  }
  return null;
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

    // Push notification settings（T4-4：星光时刻槽位偏好）
    slotPreference: 'morning',   // 'morning' 晨讯 7:37 / 'night' 星语 21:00（回显高亮）
    slotSwitching: false,        // 切换中防重复提交

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

    // 开发 04 · 星光记录卡（主角）：迷你牌运曲线 + 等级 + 愿望/月相
    sparkBars: [],          // 近 30 天解读次数迷你柱（高度百分比）
    sparkActive: 0,         // 有解读记录的天数
    recordLevel: '',        // 等级名（星辰学徒…）
    wishCount: 0,           // 愿望总数
    wishTileDesc: '',       // 新月许愿 tile 描述（新月日期）
    reviewTileDesc: '',     // 满月复盘 tile 描述（满月日期）

    // AI 周回顾 — 星光周报分享长图
    showWeeklyPoster: false,
    weeklyReportData: null,
    weeklyCardImage: '',
    weeklyLoading: false,

    // 我的星象：星座徽章 + 出生信息（前端改造第一阶段）
    zodiacBadge: '',
    birthInfo: null,       // { date, time, city, zodiac }

    // P0-3 星尘签到收集体系：星阶徽章（星光记录卡）+ 星卡收藏区
    starTierName: '',      // 星阶名：微光/星光/星辉/星冠（来自 /tasks/status）
    stardustTotal: 0,      // 累计星尘数
    tierNextName: '',      // 下一星阶名（距下一阶提示）
    tierNeed: 0,           // 距下一阶还差多少星尘
    starCards: [],         // 稀有星卡收藏（card_name/date/tier + image）
    wallpapers: [],        // 星光壁纸达成日期
    // T5-1 星阶区三数据：手账连续记录天数 / 本月节点完成数
    journalStreak: 0,
    nodeCompleted: 0,
    p1StatsVisible: false,

    // 星友圈（T8-5）：共鸣墙入口角标 + 隐身开关（我的页）
    resonanceReceivedToday: 0, // 今日收到共鸣数（角标「今天有 N 颗星与你共鸣」）
    resonanceVisible: true,    // 在共鸣墙中出现（默认开，wall 回读校准）

    // 星灵学堂称号（T6-6）：GET /academy/overview titles（星辉学者/星光塔罗师…）
    academyTitles: [],

    // 我的页整理 2026-08：设置分组折叠（默认收起，点击标题行展开 9 项设置）
    settingsExpanded: false,
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

    // Load push slot preference（星光时刻：GET /notify/preference 回显）
    this._loadSlotPreference();

    // 星友圈（T8-5）：共鸣角标 + 隐身开关回读（登录态才拉，失败静默）
    this._loadResonance();

    // 星灵学堂称号（T6-6）：称号徽章行（登录态才拉，失败静默降级）
    this._loadAcademyTitles();

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
      // T5-1：星阶区三数据 —— 手账连续记录天数（journal calendar）+ 本月节点完成数
      const _now = new Date();
      const _monthStr = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}`;
      const [status, history, shareStats, taskStatus, journalCal, activitySum] = await Promise.all([
        request('/membership/status'),
        request('/readings/history?page=1&page_size=20'),
        request('/share/stats?days=365'),
        request('/tasks/status').catch(() => null),
        request(`/journal/calendar?year=${_now.getFullYear()}&month=${_now.getMonth() + 1}`)
          .catch(() => null),
        request(`/astral/activity/summary?month=${_monthStr}`).catch(() => null),
      ]);
      // Subtle entrance chime
      sound.playPageEnterSound();

      // Load invite rewards from share stats
      const inviteRewards = shareStats?.free_deep_readings || 0;

      // 已收集 N/78 张牌 — collection spans the full 78-card encyclopedia
      let collectionCount = 0;
      try {
        const favIds = wx.getStorageSync('favorite_cards') || [];
        collectionCount = favIds.length;
      } catch (_e) {
        collectionCount = 0;
      }

      // 开发 04 · 星光记录卡：连续天数以 /tasks/status 为准，本地缓存兜底
      let recordStreak = (taskStatus && taskStatus.streak) || 0;
      if (!recordStreak) {
        try { recordStreak = wx.getStorageSync('streak') || 0; } catch (_e) { recordStreak = 0; }
      }
      const recordLevel = (taskStatus && taskStatus.level && taskStatus.level.current_level) || '';

      // P0-3 缺口2/1：星阶徽章 + 星卡收藏（后端新字段，旧后端无字段时优雅降级为空）
      const stardustTotal = (taskStatus && taskStatus.stardust_total) || 0;
      const next = nextTierInfo(stardustTotal);
      // T5-1：星阶区三数据 —— 手账连续记录天数 + 本月节点完成数（后端缺失优雅降级 0）
      const journalStreak = (journalCal && journalCal.stats && journalCal.stats.current_streak) || 0;
      const nodeCompleted = (activitySum && activitySum.completed) || 0;
      const starCards = ((taskStatus && taskStatus.star_cards) || []).map(c => ({
        ...c,
        image: computeCardImage(c.card_name),
      }));

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
        streak: recordStreak,
        recordLevel,
        // 星阶名以后端为准（star_tier_name），旧后端无该字段时用前端映射兜底
        starTierName: (taskStatus && taskStatus.star_tier_name) || currentTierName(stardustTotal),
        stardustTotal,
        tierNextName: next ? next.name : '',
        tierNeed: next ? next.need : 0,
        // T5-1：星阶区三数据（手账连续 / 本月节点 / 推送偏好——偏好由 _loadSlotPreference 回显）
        journalStreak,
        nodeCompleted,
        p1StatsVisible: journalStreak > 0 || nodeCompleted > 0,
        starCards,
        wallpapers: (taskStatus && taskStatus.wallpapers) || [],
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

    // 开发 04 · 星光记录卡：愿望数 + 月相（独立请求，失败静默降级）
    this._loadWishesAndMoon();
  },

  /** 拉取牌运曲线摘要（近 30 天解读次数 + 一句话总结 + 迷你曲线） */
  async _loadFortuneTrend() {
    try {
      const data = await request('/readings/fortune-trend?days=30');
      // 迷你牌运曲线：近 30 天每日解读次数 → 归一化柱高（星光记录卡主角）
      const rawTrend = data.trend || [];
      const maxCount = rawTrend.reduce((m, t) => Math.max(m, t.count || 0), 0) || 1;
      const sparkBars = rawTrend.map(t => ({
        h: Math.max(6, Math.round(((t.count || 0) / maxCount) * 100)),
        active: (t.count || 0) > 0,
      }));
      const sparkActive = sparkBars.filter(b => b.active).length;
      this.setData({
        fortuneTotal: data.total_readings || 0,
        fortuneMood: data.mood || '星光同行',
        sparkBars,
        sparkActive,
      });
    } catch (_err) {
      // Silent degrade — 入口卡显示默认值
    }
  },

  /** 开发 04 · 愿望数 + 月相（新月许愿/满月复盘 tile 描述） */
  async _loadWishesAndMoon() {
    const [wishRes, moonRes] = await Promise.allSettled([
      request('/wishes'),
      request('/moon/phase'),
    ]);
    const wishCount = (wishRes.status === 'fulfilled' && wishRes.value) ? (wishRes.value.total || 0) : 0;
    let wishTileDesc = '';
    let reviewTileDesc = '';
    if (moonRes.status === 'fulfilled' && moonRes.value) {
      const m = moonRes.value;
      const nm = (m.next_new_moon || '').slice(5).replace('-', '.');
      const fm = (m.next_full_moon || '').slice(5).replace('-', '.');
      wishTileDesc = `新月 ${nm} · 现在 ${m.emoji}`;
      reviewTileDesc = `满月 ${fm} 来复盘`;
    } else {
      wishTileDesc = '交给月光保管 ✦';
      reviewTileDesc = '满月时月亮会回应';
    }
    this.setData({ wishCount, wishTileDesc, reviewTileDesc });
  },

  /** 进入「我的牌运」页（牌运曲线 · 个人数据资产） */
  onGoFortuneTrend() {
    wx.navigateTo({ url: '/pages/fortune-trend/fortune-trend' });
  },

  /** P2 星象月报入口（周报 Tab 默认） */
  onGoStarReport() {
    wx.navigateTo({ url: '/pages/star-report/star-report?tab=week' });
  },

  /** 开发 04 · 新月许愿 */
  onGoWish() {
    wx.navigateTo({ url: '/pages/wish/wish' });
  },

  /** 开发 04 · 满月复盘 */
  onGoReview() {
    wx.navigateTo({ url: '/pages/review/review' });
  },

  /** 设置 tile → 平滑滚到页面「设置」分区 */
  onGoSettingsSection() {
    wx.pageScrollTo({ selector: '#settings-section', duration: 320 });
  },

  /** 展开/收起设置分组（折叠标题条，写法与日记页 onToggleReview 一致） */
  toggleSettings() {
    this.setData({ settingsExpanded: !this.data.settingsExpanded });
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
    // 星光手账 T1-4：日记与手账合并，入口指向手账
    wx.navigateTo({ url: '/pages/journal/journal' });
  },

  /** 星辰相遇（双人合盘）入口（SDD P1 · T2-4） */
  onGoMeet() {
    analytics.trackEvent('meet_entry', { source: 'profile' });
    wx.navigateTo({ url: '/pages/meet/meet' });
  },

  /** 星友圈（今日共鸣墙）入口（SDD P2 · T8-5） */
  onGoResonance() {
    analytics.trackEvent('resonance_entry', { source: 'profile' });
    wx.navigateTo({ url: '/pages/resonance/resonance' });
  },

  /**
   * 星友圈共鸣角标 + 隐身开关回读（T8-5，我的页）：
   * - GET /resonance/stats → received_today 角标「今天有 N 颗星与你共鸣」
   * - GET /resonance/wall → my_card.visible 回读隐身态（与共鸣页同契约，0215345）
   * 失败静默降级（角标 0、开关默认开），不阻塞我的页加载。
   */
  async _loadResonance() {
    if (!wx.getStorageSync('token')) return; // 未登录不拉（接口需鉴权）
    const [statsRes, wallRes] = await Promise.allSettled([
      request('/resonance/stats'),
      request('/resonance/wall'),
    ]);
    if (statsRes.status === 'fulfilled' && statsRes.value) {
      this.setData({ resonanceReceivedToday: statsRes.value.received_today || 0 });
    }
    const myCard = wallRes.status === 'fulfilled' && wallRes.value && wallRes.value.my_card;
    if (myCard && typeof myCard.visible === 'boolean') {
      this.setData({ resonanceVisible: myCard.visible });
    }
  },

  /**
   * 星灵学堂称号（T6-6）：GET /academy/overview → titles（称号名数组），
   * 星阶区徽章行展示，与星阶徽章并列。失败静默降级（不展示称号行），
   * 不阻塞我的页加载（独立请求，与 _loadResonance 同模式）。
   */
  async _loadAcademyTitles() {
    if (!wx.getStorageSync('token')) return; // 未登录不拉（接口需鉴权）
    try {
      const data = await request('/academy/overview');
      this.setData({ academyTitles: (data && data.titles) || [] });
    } catch (_err) {
      // 静默降级：后端无该功能/网络异常时称号行不展示
    }
  },

  /** 隐身开关（我的页设置项 · T8-5）：即时生效（POST /resonance/visibility），失败回滚 */
  async onToggleResonanceVisible(e) {
    const next = !!(e && e.detail && e.detail.value);
    const prev = this.data.resonanceVisible;
    if (next === prev) return;
    this.setData({ resonanceVisible: next });
    try {
      await request('/resonance/visibility', { method: 'POST', data: { visible: next } });
      analytics.trackEvent('resonance_visibility', { visible: next ? 1 : 0, source: 'profile' });
      wx.showToast({ title: next ? '你的星重新点亮 ✦' : '已隐身 ✦', icon: 'none' });
    } catch (err) {
      // 失败回滚开关状态（即时生效语义以服务端为准，与共鸣页一致）
      this.setData({ resonanceVisible: prev });
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
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

  // ---- Push notification settings（T4-4：星光时刻槽位偏好） ----

  /**
   * 加载推送槽位偏好（星光时刻）：GET /notify/preference 回显高亮。
   * 优雅降级：未登录/接口失败时优先本地缓存（上次选择），无缓存默认
   * morning（与后端默认一致）；失败静默不打扰用户。
   */
  async _loadSlotPreference() {
    let cached = 'morning';
    try { cached = wx.getStorageSync('slot_preference') || 'morning'; } catch (_e) { /* silent */ }
    if (cached !== 'morning' && cached !== 'night') cached = 'morning';
    try {
      const data = await request('/notify/preference');
      const slot = data && data.slot_preference;
      const valid = (slot === 'morning' || slot === 'night') ? slot : cached;
      try { wx.setStorageSync('slot_preference', valid); } catch (_e) { /* silent */ }
      this.setData({ slotPreference: valid });
    } catch (_err) {
      // 未登录/接口失败：静默用缓存兜底，不打扰用户
      this.setData({ slotPreference: cached });
    }
  },

  /**
   * 切换星光时刻（晨讯 7:37 / 星语 21:00）：POST /notify/preference，即时生效。
   * 守卫：切换中防重复提交；重复点击当前已选槽位 no-op（不发请求）。
   * 失败：回滚高亮 + 轻提示（本地态保持上一次选择，次日生效语义不因失败漂移）。
   */
  async onSelectSlot(e) {
    const slot = e.currentTarget.dataset.slot;
    if (slot !== 'morning' && slot !== 'night') return;
    if (this.data.slotSwitching || this.data.slotPreference === slot) return;
    const prev = this.data.slotPreference;
    this.setData({ slotSwitching: true, slotPreference: slot });
    try {
      await request('/notify/preference', { method: 'POST', data: { slot } });
      try { wx.setStorageSync('slot_preference', slot); } catch (_err) { /* silent */ }
      const info = SLOT_INFO[slot] || SLOT_INFO.morning;
      wx.showToast({ title: info.switchToast, icon: 'none', duration: 2000 });
    } catch (_err) {
      // 失败回滚 + 轻提示（getFriendlyError 映射为中文）
      this.setData({ slotPreference: prev });
      wx.showToast({ title: '切换失败，请稍后重试', icon: 'none' });
    } finally {
      this.setData({ slotSwitching: false });
    }
  },

  /** Open WeChat settings page so user can manage notification permissions */
  onOpenPushSettings() {
    wx.openSetting({
      success: () => {
        wx.showToast({ title: '设置已更新', icon: 'none', duration: 1500 });
      },
    });
  },

  onReady() {
    // Performance monitoring: page ready timestamp
    perf.markPageReady('profile');
  },
});
