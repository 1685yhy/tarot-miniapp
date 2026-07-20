// pages/daily-card/daily-card.js
// 每日一牌 — 卡牌翻转动画 + 牌意教学 + 收集进度 + 日记入口
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

const IMAGE_BASE = 'https://xingxiang.chat/images/cards_full';
const MAJOR_ARCANA_TOTAL = 22;

function getTodayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

Page({
  data: {
    // Card data
    dailyCard: null,
    cardImagePath: '',
    cardImgLoaded: false,
    cardImgError: false,

    // Teaching data
    teaching: null,

    // Card flip state
    isFlipped: false,
    isAnimating: false,
    showTeaching: false,
    showGlow: false,
    backHidden: false,
    frontVisible: false,

    // Loading / Error states
    pageLoading: true,
    pageError: null,
    teachingLoading: false,
    teachingError: null,

    // Collection progress (major arcana only)
    collectedCount: 0,
    collectedMajorIds: [],
    MAJOR_ARCANA_TOTAL: MAJOR_ARCANA_TOTAL,

    // Diary
    diaryText: '',
    diarySaving: false,
    diarySaved: false,
  },

  async onLoad() {
    const today = getTodayStr();
    const flippedDate = wx.getStorageSync('daily_card_flipped_date');
    const alreadyFlipped = flippedDate === today;

    // Load collection progress from storage
    this._loadCollectionProgress();

    try {
      const card = await request('/cards/daily');
      card.imagePath = computeImagePath(card, IMAGE_BASE);

      this.setData({
        dailyCard: card,
        pageLoading: false,
        // If already flipped today, show face-up immediately
        isFlipped: alreadyFlipped,
        showTeaching: alreadyFlipped,
        showGlow: alreadyFlipped,
        backHidden: alreadyFlipped,
        frontVisible: alreadyFlipped,
      });

      // Fetch teaching data in parallel after card loads
      this._loadTeaching(card.id);
    } catch (err) {
      this.setData({
        pageLoading: false,
        pageError: getFriendlyError(err),
      });
    }
  },

  // ---- Teaching data ----

  async _loadTeaching(cardId) {
    this.setData({ teachingLoading: true, teachingError: null });
    try {
      const teaching = await request(`/cards/${cardId}/teaching`);
      this.setData({ teaching, teachingLoading: false });
    } catch (err) {
      this.setData({
        teachingLoading: false,
        teachingError: getFriendlyError(err),
      });
    }
  },

  // ---- Collection progress ----

  _loadCollectionProgress() {
    const collectedMajorIds = wx.getStorageSync('collected_major_ids') || [];
    this.setData({
      collectedCount: collectedMajorIds.length,
      collectedMajorIds,
    });
  },

  _saveCollectionProgress() {
    const card = this.data.dailyCard;
    if (!card || card.arcana !== 'major') return;

    const collectedMajorIds = wx.getStorageSync('collected_major_ids') || [];
    if (!collectedMajorIds.includes(card.id)) {
      collectedMajorIds.push(card.id);
      wx.setStorageSync('collected_major_ids', collectedMajorIds);
      this.setData({
        collectedCount: collectedMajorIds.length,
        collectedMajorIds,
      });
    }
  },

  // ---- Card flip ----

  onCardTap() {
    if (this.data.isFlipped || this.data.isAnimating) return;

    this.setData({ isAnimating: true });

    // Haptic feedback
    wx.vibrateShort({ type: 'light' }).catch(() => {});

    // Midpoint (~700ms): swap card faces
    this._flipTimer = setTimeout(() => {
      this.setData({
        backHidden: true,
        frontVisible: true,
      });
    }, 700);

    // End of flip animation (1.5s): glow + teaching reveal
    this._flipTimer = setTimeout(() => {
      this.setData({
        isFlipped: true,
        isAnimating: false,
      });

      // Golden glow (0.3s), then show teaching content
      this.setData({ showGlow: true });

      this._glowTimer = setTimeout(() => {
        this.setData({ showTeaching: true });
        this._saveCollectionProgress();

        // Store flipped date so it persists across page revisits
        const today = getTodayStr();
        wx.setStorageSync('daily_card_flipped_date', today);
      }, 300);
    }, 1500);
  },

  // ---- Diary ----

  onDiaryInput(e) {
    this.setData({ diaryText: e.detail.value });
  },

  async onDiarySave() {
    if (this.data.diarySaving || !this.data.diaryText.trim()) return;
    if (!this.data.dailyCard) return;

    this.setData({ diarySaving: true });
    try {
      await request('/diary/entries', {
        method: 'POST',
        data: {
          reflection: this.data.diaryText.trim(),
          card_id: this.data.dailyCard.id,
        },
      });
      this.setData({ diarySaved: true, diarySaving: false });
      wx.showToast({ title: '记录成功', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
      this.setData({ diarySaving: false });
    }
  },

  // ---- Image events ----

  onCardImgLoad() {
    this.setData({ cardImgLoaded: true });
  },

  onCardImgError() {
    this.setData({ cardImgError: true });
  },

  // ---- Retry ----

  onRetry() {
    this.setData({
      pageError: null,
      pageLoading: true,
      teachingError: null,
    });
    this.onLoad();
  },

  onRetryTeaching() {
    if (this.data.dailyCard) {
      this._loadTeaching(this.data.dailyCard.id);
    }
  },

  // ---- Cleanup ----

  onUnload() {
    if (this._flipTimer) clearTimeout(this._flipTimer);
    if (this._glowTimer) clearTimeout(this._glowTimer);
  },
});
