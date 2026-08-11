// pages/journal/journal.js —— 星光手账（T1-4）
//
// 手账 = 情感日记的"星光视图升级"（设计 1.5 合并决策）：
//   - 顶部"今晚，记一颗星"：5 档星光亮度一屏点选，点按即存（3 秒完成）
//   - 月历 = 我的星光夜空：共用 calendar 组件，星点颜色=当日星光色、光晕=亮度档
//   - 点任一天 → 星点详情展开：改情绪档（"让这一天更亮一点"）+ 可选文字 +
//     图片上传/删除（复用旧日记 /diary/entries PUT/DELETE、/diary/upload-image、
//     /diary/reflection-prompt）
//
// 数据降级：月历接口失败 → 错误态 + 重试；详情所需日记列表（/diary/entries）
// 拉取失败或超页数上限 → 详情仍展示月历已有数据（星点/亮度），编辑功能隐藏。
//
// T1-4 审查修复（I-1/I-2/M-2）：
//   - AI 周回顾（/diary/review?period=weekly）+ 情绪趋势 + 生成/刷新 由旧 diary 迁入，
//     折叠标题条 UI 与日记页保持一致；本地回溯降级数据改由 entriesMap 计算
//   - 详情层新增匿名分享海报（复用旧 diary /diary/entries/{id}/share-preview + share-poster）
//   - onLoad 消费 reading-result 写入的 globalData.diaryCardHint：打开今日详情并
//     预填卡牌/反思引导，消费后立即清除防脏残留
//   - 详情层新增"删除图片"入口（PUT image_url 置空，配合后端部分更新语义）

const { request, getFriendlyError, BASE_URL } = require('../../utils/api');
const analytics = require('../../utils/analytics');
const { findCard, computeImagePath } = require('../../utils/cards');

// 6 档情绪 → 5 档星光亮度（与后端 services.journal.MOOD_BRIGHTNESS 同口径）
const BRIGHTNESS_NAMES = { 5: '满溢星光', 4: '明亮星光', 3: '常亮星光', 2: '微暗星光', 1: '隐没星光' };
const MOOD_META = {
  excited: { name: '兴奋', emoji: '🤩', brightness: 5 },
  happy: { name: '开心', emoji: '😊', brightness: 4 },
  calm: { name: '平静', emoji: '😌', brightness: 3 },
  thoughtful: { name: '思考', emoji: '🤔', brightness: 2 },
  anxious: { name: '焦虑', emoji: '😰', brightness: 1 },
  sad: { name: '低落', emoji: '😢', brightness: 1 },
};
const MOOD_ORDER = ['excited', 'happy', 'calm', 'thoughtful', 'anxious', 'sad'];
// 周回顾本地降级用的情绪分（与旧 diary.js 同口径）
const MOOD_SCORE_MAP = { happy: 4.5, calm: 3.5, excited: 5, anxious: 2, sad: 1, thoughtful: 3 };
// 分享预览缺 mood_emoji 时的兜底表情（与旧 diary.js 同口径）
const MOOD_EMOJI_MAP = { happy: '😊', calm: '😌', excited: '🤩', anxious: '😰', sad: '😢', thoughtful: '🤔' };

// 顶部快记五档（隐没档覆盖 anxious+sad，取 anxious 落库，详情可再调）
const QUICK_LEVELS = [
  { level: 5, mood: 'excited', name: '满溢星光', glyph: '✦✦✦✦✦', hint: '兴奋' },
  { level: 4, mood: 'happy', name: '明亮星光', glyph: '✦✦✦✦', hint: '开心' },
  { level: 3, mood: 'calm', name: '常亮星光', glyph: '✦✦✦', hint: '平静' },
  { level: 2, mood: 'thoughtful', name: '微暗星光', glyph: '✦✦', hint: '思考' },
  { level: 1, mood: 'anxious', name: '隐没星光', glyph: '✦', hint: '焦虑 · 低落' },
];

// 日记条目地图拉取上限（GET /diary/entries 每页 20 条，8 页覆盖绝大多数用户）
const MAX_ENTRY_PAGES = 8;

function pad(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

function fmtDate(y, m, d) {
  return `${y}-${pad(m)}-${pad(d)}`;
}

Page({
  data: {
    todayStr: '',
    year: 0,
    month: 0,
    calDays: [],
    stats: null, // {days_recorded, bright_count, dim_count, current_streak}
    calendarLoading: true,
    calendarError: null,

    // 顶部快记
    quickLevels: QUICK_LEVELS,
    quickSaving: false,
    quickDone: false, // 今晚的星已点亮
    todayMood: '',

    // 星点详情展开
    detailVisible: false,
    detailDate: '',
    detailDateLabel: '',
    detailDayInfo: null, // 月历日数据 {date, mood, brightness, star_color, has_reflection, card_id}
    detailEntry: null, // 日记条目 {id, mood, reflection, image_url, card}
    detailMood: '',
    detailMoodMeta: null, // {emoji, name}（由 detailMood 计算，避免 wxml 按 key 取对象）
    detailReflection: '',
    detailImage: '',
    detailSelectedImage: '',
    detailCard: null,
    detailBrightness: 0, // 当前展示亮度（预览星点用）
    detailBrightnessName: '',
    detailStarColor: '',
    detailHasStar: false,
    detailIsToday: false,
    detailIsFuture: false,
    detailSaving: false,
    detailDeleting: false,
    detailReflectionPrompt: '',
    detailPromptLoading: false,
    // 情绪档 chips（6 档 → 星光亮度视觉）
    moodChips: MOOD_ORDER.map((mood) => ({
      mood,
      name: MOOD_META[mood].name,
      emoji: MOOD_META[mood].emoji,
      brightness: MOOD_META[mood].brightness,
      starGlyph: '✦'.repeat(Math.max(1, MOOD_META[mood].brightness)),
    })),

    // 日记条目地图（详情展开复用旧日记能力）
    entriesMap: {},
    entriesPage: 0,
    entriesHasMore: true,
    entriesLoading: false,
    entriesCount: 0, // 手账内记录总数（周回顾卡片显隐/文案用）

    // AI 周回顾（I-1：由旧 diary 迁入，UI 与交互保持一致）
    reviewExpanded: false,
    weeklyReview: null,
    reviewLoading: false,
    reviewError: null,
    topCard: '',
    moodTrend: '',

    // 匿名分享海报（I-1：复用旧 diary share-poster 流程）
    showDiarySharePoster: false,
    diaryShareData: null,
  },

  onLoad() {
    const now = new Date();
    this.setData({
      todayStr: fmtDate(now.getFullYear(), now.getMonth() + 1, now.getDate()),
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    });
    // I-2：消费 reading-result 写入的 diaryCardHint（消费后即清除）→ 打开今日详情并预填卡牌/反思引导
    this._hintCard = this._takeDiaryCardHint();
    if (this._hintCard) {
      this._openTodayDetailWithHint();
    }
    this._loadCalendar(false);
    this._loadMoreEntries(2); // 预热详情数据
  },

  onShow() {
    // 静默刷新：在别处记录/编辑后回到本页保持最新（首帧由 onLoad 加载）
    if (this._loadedOnce) {
      this._loadCalendar(true);
    }
    this._loadedOnce = true;
  },

  onShareAppMessage() {
    return {
      title: '星光映照 · 我的星光夜空',
      path: '/pages/index/index',
    };
  },

  // ============================================================
  // 月历数据
  // ============================================================

  async _loadCalendar(silent) {
    if (!silent) this.setData({ calendarLoading: true });
    try {
      const data = await request(`/journal/calendar?year=${this.data.year}&month=${this.data.month}`);
      const days = data.days || [];
      const todayEntry = days.find((d) => d.date === this.data.todayStr) || null;
      this.setData({
        calDays: days,
        stats: data.stats || null,
        calendarLoading: false,
        calendarError: null,
        quickDone: !!todayEntry,
        todayMood: todayEntry ? todayEntry.mood : '',
      });
      // I-2：hint 预填打开的今日详情，等月历数据到达后刷新星点/状态
      this._refreshOpenDetail();
    } catch (err) {
      if (!silent) {
        this.setData({ calendarLoading: false, calendarError: getFriendlyError(err) });
      }
    }
  },

  onRetry() {
    this.setData({ calendarError: null, calendarLoading: true });
    this._loadCalendar(false);
  },

  onCalendarMonthChange(e) {
    const { year, month } = e.detail;
    this.setData({ year, month });
    this._loadCalendar(true);
  },

  // ============================================================
  // 顶部快记：5 档星光亮度一屏点选，点按即存
  // ============================================================

  async onQuickRecord(e) {
    const mood = e.currentTarget.dataset.mood;
    if (!mood || this.data.quickSaving) return;
    this.setData({ quickSaving: true });
    try {
      const res = await request('/journal/entries', {
        method: 'POST',
        data: { mood },
      });
      wx.vibrateShort({ type: 'light' }).catch(() => {});
      wx.showToast({
        title: res && res.reward ? '七夜连星 · 星尘 +1 ✦' : '今晚的星，已挂上夜空 ✦',
        icon: 'none',
        duration: 2000,
      });
      // 本地写入 entriesMap（拿到真实 entry id，详情可直接编辑）
      if (res && res.id) {
        const map = Object.assign({}, this.data.entriesMap, { [res.date]: res });
        this.setData({
          entriesMap: map,
          entriesCount: Object.keys(map).length,
          quickDone: true,
          todayMood: mood,
        });
      }
      analytics.trackEvent('journal_record', { mood, source: 'quick' });
      this._loadCalendar(true);
      // 快记发生在详情展开（未记录日引导）时，成功后收起
      if (this.data.detailVisible) this._closeDetail();
    } catch (err) {
      wx.showToast({ title: '记录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ quickSaving: false });
    }
  },

  // ============================================================
  // 日记条目地图（GET /diary/entries 分页，详情展开复用旧日记能力）
  // ============================================================

  async _loadMoreEntries(maxPages = 2) {
    if (this.data.entriesLoading || !this.data.entriesHasMore) return;
    this.setData({ entriesLoading: true });
    let page = this.data.entriesPage + 1;
    const max = Math.min(page + maxPages - 1, MAX_ENTRY_PAGES);
    try {
      for (; page <= max; page++) {
        const data = await request(`/diary/entries?page=${page}`);
        const items = data.entries || [];
        const map = Object.assign({}, this.data.entriesMap);
        items.forEach((it) => {
          if (it && it.date) map[it.date] = it;
        });
        const hasMore = items.length === 20;
        this.setData({
          entriesMap: map,
          entriesCount: Object.keys(map).length,
          entriesPage: page,
          entriesHasMore: hasMore,
        });
        // I-2：hint 预填打开的今日详情，等真实条目到达后以真实卡牌刷新
        this._refreshOpenDetail();
        if (!hasMore) break;
      }
    } catch (err) {
      // 静默降级：详情展开时按需重试；失败则展示月历已有数据
    } finally {
      this.setData({ entriesLoading: false });
    }
  },

  /** 已记录但地图未覆盖（记录很早）→ 按需补拉，最多补到 8 页 */
  async _ensureEntryFor(date) {
    if (this.data.entriesMap[date] || !this.data.entriesHasMore) return;
    await this._loadMoreEntries(MAX_ENTRY_PAGES - this.data.entriesPage);
  },

  // ============================================================
  // 星点详情展开
  // ============================================================

  async onDayTap(e) {
    const { date, hasStar } = e.detail || {};
    if (!date) return;
    const dayInfo = this.data.calDays.find((d) => d.date === date) || null;
    let entry = this.data.entriesMap[date] || null;
    if (hasStar && !entry) {
      await this._ensureEntryFor(date);
      entry = this.data.entriesMap[date] || null;
    }
    this._openDetail(date, dayInfo, entry);
  },

  _openDetail(date, dayInfo, entry, hintCard) {
    const detailMood = entry ? entry.mood : dayInfo ? dayInfo.mood : '';
    // I-2：今日真实记录有卡牌以真实卡牌为准；否则用 hint 预填的卡牌（来自本次解读）
    const card = (entry && entry.card) || hintCard || null;
    this.setData({
      detailVisible: true,
      detailDate: date,
      detailDateLabel: this._fmtDateLabel(date),
      detailDayInfo: dayInfo,
      detailEntry: entry,
      detailMood: detailMood || '',
      detailMoodMeta: MOOD_META[detailMood] || null,
      detailReflection: (entry && entry.reflection) || '',
      detailImage: (entry && entry.image_url) || '',
      detailSelectedImage: '',
      detailCard: card,
      detailReflectionPrompt: '',
      detailPromptLoading: false,
    });
    this._recomputeDetailView();
    if (card && card.id) {
      this._loadReflectionPrompt(card);
    }
  },

  // ============================================================
  // I-2：diaryCardHint 预填（reading-result 解读完成 → 记录 → 手账）
  // ============================================================

  /** 消费 reading-result 写入的 globalData.diaryCardHint（消费后即清除，防脏残留） */
  _takeDiaryCardHint() {
    const app = getApp();
    const hint = app && app.globalData && app.globalData.diaryCardHint;
    if (!hint || !hint.card_id) return null;
    delete app.globalData.diaryCardHint;
    return hint;
  },

  /** 打开今日详情并带 hint 卡牌（预填卡牌 + 反思引导） */
  _openTodayDetailWithHint() {
    const today = this.data.todayStr;
    const dayInfo = this.data.calDays.find((d) => d.date === today) || null;
    const entry = this.data.entriesMap[today] || null;
    const hintCard = this._hintCard
      ? { id: this._hintCard.card_id, name_zh: this._hintCard.card_name || '' }
      : null;
    this._openDetail(today, dayInfo, entry, hintCard);
  },

  /** 月历/日记数据异步到达后刷新已打开的今日详情（hint 预填场景） */
  _refreshOpenDetail() {
    const date = this.data.detailDate;
    if (!date || !this.data.detailVisible) return;
    const dayInfo = this.data.calDays.find((d) => d.date === date) || null;
    const entry = this.data.entriesMap[date] || null;
    const patch = {};
    if (dayInfo) patch.detailDayInfo = dayInfo;
    if (entry) patch.detailEntry = entry;
    if (Object.keys(patch).length > 0) this.setData(patch);
    this._recomputeDetailView();
    // 今日真实记录到达后以其卡牌覆盖 hint 预填卡牌，并重载反思引导
    if (entry && entry.card && entry.card.id) {
      const cur = this.data.detailCard;
      if (!cur || String(cur.id) !== String(entry.card.id)) {
        this.setData({ detailCard: entry.card });
        this._loadReflectionPrompt(entry.card);
      }
    }
  },

  /** 由 detailMood/detailDayInfo 重算展示字段（wxml 直接取值） */
  _recomputeDetailView() {
    const day = this.data.detailDayInfo;
    const meta = MOOD_META[this.data.detailMood];
    const brightness = meta ? meta.brightness : day ? day.brightness : 0;
    this.setData({
      detailBrightness: brightness,
      detailBrightnessName: BRIGHTNESS_NAMES[brightness] || '',
      detailStarColor: day ? day.star_color : '',
      detailHasStar: !!(day && day.brightness > 0),
      detailIsToday: this.data.detailDate === this.data.todayStr,
      detailIsFuture: this.data.detailDate > this.data.todayStr,
    });
  },

  /** '2026-08-15' → '2026年8月15日 · 周六' */
  _fmtDateLabel(dateStr) {
    const parts = dateStr.split('-');
    const y = Number(parts[0]);
    const m = Number(parts[1]);
    const d = Number(parts[2]);
    const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date(y, m - 1, d).getDay()];
    return `${y}年${m}月${d}日 · ${week}`;
  },

  _closeDetail() {
    this.setData({ detailVisible: false });
  },

  preventClose() {
    // 阻止事件冒泡——防止点击弹层内部元素时关闭
  },

  onDetailMoodSelect(e) {
    const mood = e.currentTarget.dataset.mood;
    this.setData({ detailMood: mood, detailMoodMeta: MOOD_META[mood] || null });
    this._recomputeDetailView();
  },

  onDetailReflectionInput(e) {
    this.setData({ detailReflection: e.detail.value });
  },

  onDetailChooseImage() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        this.setData({ detailSelectedImage: res.tempFilePaths[0] });
      },
    });
  },

  onDetailRemoveImage() {
    this.setData({ detailSelectedImage: '' });
  },

  async _loadReflectionPrompt(card) {
    if (!card || !card.id) return;
    this.setData({ detailPromptLoading: true });
    try {
      const res = await request('/diary/reflection-prompt', {
        method: 'POST',
        data: { card_id: card.id, card_name: card.name_zh || '' },
      });
      this.setData({
        detailReflectionPrompt: res.question || '',
        detailPromptLoading: false,
      });
    } catch (err) {
      // 降级：本地默认引导
      this.setData({
        detailReflectionPrompt: `今天的「${card.name_zh || ''}」给你带来了什么感受？`,
        detailPromptLoading: false,
      });
    }
  },

  /** 保存："让这一天更亮一点"（改情绪档 + 可选文字/图片） */
  async onDetailSave() {
    const { detailEntry, detailMood, detailDate, detailSaving } = this.data;
    if (!detailMood) {
      wx.showToast({ title: '先选一档星光亮度', icon: 'none' });
      return;
    }
    if (!detailEntry || !detailEntry.id) {
      wx.showToast({ title: '这篇记录暂不可编辑', icon: 'none' });
      return;
    }
    if (detailSaving) return;
    this.setData({ detailSaving: true });

    let imageUrl = this.data.detailImage;
    if (this.data.detailSelectedImage) {
      try {
        imageUrl = await this._uploadImage(this.data.detailSelectedImage);
      } catch (err) {
        this.setData({ detailSaving: false });
        wx.showToast({ title: '图片上传失败', icon: 'none' });
        return;
      }
    }

    try {
      const updated = await request(`/diary/entries/${detailEntry.id}`, {
        method: 'PUT',
        data: {
          mood: detailMood,
          reflection: this.data.detailReflection,
          image_url: imageUrl || undefined,
        },
      });
      const map = Object.assign({}, this.data.entriesMap, { [detailDate]: updated });
      this.setData({
        entriesMap: map,
        entriesCount: Object.keys(map).length,
        detailSaving: false,
        detailVisible: false,
      });
      wx.showToast({ title: '这一天，更亮了一点 ✦', icon: 'none' });
      analytics.trackEvent('journal_update', { mood: detailMood, source: 'detail' });
      this._loadCalendar(true);
    } catch (err) {
      this.setData({ detailSaving: false });
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
    }
  },

  onDetailDelete() {
    const entry = this.data.detailEntry;
    if (!entry || !entry.id || this.data.detailDeleting) return;
    wx.showModal({
      title: '删除这一天',
      content: '确定要删除这颗星吗？删除后无法恢复。',
      confirmText: '删除',
      confirmColor: '#E87A8A',
      success: async (res) => {
        if (!res.confirm) return;
        this.setData({ detailDeleting: true });
        try {
          await request(`/diary/entries/${entry.id}`, { method: 'DELETE' });
          const map = Object.assign({}, this.data.entriesMap);
          delete map[this.data.detailDate];
          this.setData({
            entriesMap: map,
            entriesCount: Object.keys(map).length,
            detailDeleting: false,
            detailVisible: false,
          });
          wx.showToast({ title: '已删除', icon: 'success' });
          this._loadCalendar(true);
        } catch (err) {
          this.setData({ detailDeleting: false });
          wx.showToast({ title: '删除失败', icon: 'none' });
        }
      },
    });
  },

  // ============================================================
  // I-1：AI 周回顾（由旧 diary 迁入：生成/刷新/趋势曲线/本地降级）
  // ============================================================

  /** 本地回溯降级数据（由 entriesMap 计算，与旧 diary._computeRetrospect 同口径） */
  _computeRetrospect() {
    const entries = Object.keys(this.data.entriesMap).map((k) => this.data.entriesMap[k]);
    if (entries.length < 3) return;
    const cardCount = {};
    entries.forEach((e) => {
      const name = e.card && e.card.name_zh;
      if (name) cardCount[name] = (cardCount[name] || 0) + 1;
    });
    const topEntry = Object.entries(cardCount).sort((a, b) => b[1] - a[1])[0];
    const topCard = topEntry ? topEntry[0] : '未知';
    const recent = entries.slice(0, 3);
    const avgMood = recent.reduce((s, e) => {
      return s + (e.mood_score || MOOD_SCORE_MAP[e.mood] || 3);
    }, 0) / recent.length;
    const moodTrend = avgMood > 3.5 ? '在变好 ✦' : avgMood < 2.5 ? '有些低落' : '比较平稳';
    this.setData({ topCard, moodTrend });
  },

  /** 拉取 AI 周回顾（复用旧日记 /diary/review?period=weekly 逻辑） */
  async _loadWeeklyReview() {
    if (this.data.reviewLoading) return;
    this.setData({ reviewLoading: true, reviewError: null });
    try {
      const review = await request('/diary/review?period=weekly');
      // 情绪趋势曲线（moodTrendCurve 为本地 camelCase，由 API snake_case mood_trends 计算）
      if (review.mood_trends && review.mood_trends.length > 0) {
        review.moodTrendCurve = this._computeMoodTrendCurve(review.mood_trends);
      }
      this.setData({ weeklyReview: review, reviewLoading: false });
    } catch (err) {
      this.setData({ reviewLoading: false, reviewError: getFriendlyError(err) });
    }
  },

  /** 用户点按生成/刷新周回顾 */
  onRefreshReview() {
    this._loadWeeklyReview();
    wx.vibrateShort({ type: 'light' }).catch(() => {});
  },

  /** 展开/收起本周回顾（折叠标题条） */
  onToggleReview() {
    this.setData({ reviewExpanded: !this.data.reviewExpanded });
  },

  /** 由 mood_trends 计算 emoji 情绪趋势曲线（与旧 diary 同口径） */
  _computeMoodTrendCurve(trends) {
    const BLOCK_MAP = ['▁', '▁', '▂', '▃', '▅', '▇'];
    const blocks = trends.map((t) => {
      const score = Math.round(t.mood_score || 3);
      return BLOCK_MAP[Math.min(Math.max(score, 1), 5)];
    });
    return '😔 ' + blocks.join(' ') + ' 😊';
  },

  // ============================================================
  // I-1：详情层匿名分享海报（复用旧 diary share-poster 流程）
  // ============================================================

  /** 生成并预览匿名分享海报（/diary/entries/{id}/share-preview 仅返回分享安全字段） */
  async onDetailShare() {
    const entry = this.data.detailEntry;
    if (!entry || !entry.id) return;
    wx.showLoading({ title: '生成分享图...', mask: true });
    try {
      const preview = await request(`/diary/entries/${entry.id}/share-preview`);
      // 后端 card 为精简 {id, name_zh, meaning_upright} — 先解析全量卡牌再算图路径
      const fullCard = preview.card ? findCard(preview.card.name_zh) : null;
      const cardImagePath = fullCard ? computeImagePath(fullCard) : '';
      this.setData({
        diaryShareData: {
          moodEmoji: preview.mood_emoji || MOOD_EMOJI_MAP[entry.mood] || '🤔',
          date: preview.date || entry.date,
          excerpt: preview.excerpt || '',
          cardImagePath,
          cardName: preview.card ? preview.card.name_zh : (entry.card ? entry.card.name_zh : ''),
        },
        showDiarySharePoster: true,
      });
      wx.hideLoading();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '生成失败，请重试', icon: 'none' });
    }
  },

  onCloseDiarySharePoster() {
    this.setData({ showDiarySharePoster: false });
  },

  onShareDiaryPosterToFriend(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'diary_poster');
    try {
      wx.shareAppMessage({
        imageUrl: imagePath,
        title: '星光映照 · 塔罗日记',
      });
    } catch (err) {
      // 降级：先保存海报，再从相册分享
      wx.showToast({
        title: '请先保存海报，再从相册分享',
        icon: 'none',
        duration: 2000,
      });
    }
  },

  // ============================================================
  // M-2：删除已保存图片（PUT image_url 置空，配合后端部分更新语义）
  // ============================================================

  onDetailRemoveSavedImage() {
    const entry = this.data.detailEntry;
    if (!entry || !entry.id) return;
    wx.showModal({
      title: '删除图片',
      content: '确定要删除这张图片吗？',
      confirmText: '删除',
      confirmColor: '#E87A8A',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          // 后端部分更新：image_url 非 None 即写入，故置空字符串清图（null 会被视为未提供）
          const updated = await request(`/diary/entries/${entry.id}`, {
            method: 'PUT',
            data: { image_url: '' },
          });
          const map = Object.assign({}, this.data.entriesMap, { [this.data.detailDate]: updated });
          this.setData({
            entriesMap: map,
            entriesCount: Object.keys(map).length,
            detailImage: '',
            detailEntry: updated,
          });
          wx.showToast({ title: '图片已删除', icon: 'none' });
          analytics.trackEvent('journal_update', { mood: this.data.detailMood, source: 'detail-image-remove' });
        } catch (err) {
          wx.showToast({ title: '删除失败，请重试', icon: 'none' });
        }
      },
    });
  },

  /** 上传图片（复用旧日记 /diary/upload-image 逻辑） */
  _uploadImage(filePath) {
    return new Promise((resolve, reject) => {
      const token = wx.getStorageSync('token');
      wx.uploadFile({
        url: `${BASE_URL}/diary/upload-image`,
        filePath,
        name: 'file',
        header: {
          'Authorization': token ? `Bearer ${token}` : '',
        },
        success: (res) => {
          try {
            const data = JSON.parse(res.data);
            if (res.statusCode >= 200 && res.statusCode < 300 && data.url) {
              resolve(data.url);
            } else {
              reject(new Error(data.detail || '上传失败'));
            }
          } catch (e) {
            reject(new Error('上传响应解析失败'));
          }
        },
        fail: (err) => reject(err),
      });
    });
  },
});
