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

const { request, getFriendlyError, BASE_URL } = require('../../utils/api');
const analytics = require('../../utils/analytics');

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
  },

  onLoad() {
    const now = new Date();
    this.setData({
      todayStr: fmtDate(now.getFullYear(), now.getMonth() + 1, now.getDate()),
      year: now.getFullYear(),
      month: now.getMonth() + 1,
    });
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
        this.setData({ entriesMap: map, quickDone: true, todayMood: mood });
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
        this.setData({ entriesMap: map, entriesPage: page, entriesHasMore: hasMore });
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

  _openDetail(date, dayInfo, entry) {
    const detailMood = entry ? entry.mood : dayInfo ? dayInfo.mood : '';
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
      detailCard: (entry && entry.card) || null,
      detailReflectionPrompt: '',
      detailPromptLoading: false,
    });
    this._recomputeDetailView();
    if (entry && entry.card) {
      this._loadReflectionPrompt(entry.card);
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
      this.setData({ entriesMap: map, detailSaving: false, detailVisible: false });
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
          this.setData({ entriesMap: map, detailDeleting: false, detailVisible: false });
          wx.showToast({ title: '已删除', icon: 'success' });
          this._loadCalendar(true);
        } catch (err) {
          this.setData({ detailDeleting: false });
          wx.showToast({ title: '删除失败', icon: 'none' });
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
