// pages/diary/diary.js
const { request, getFriendlyError } = require('../../utils/api');
const { computeImagePath } = require('../../utils/cards');

// Mood score map for trend analysis
const MOOD_SCORE_MAP = { happy: 4.5, calm: 3.5, excited: 5, anxious: 2, sad: 1, thoughtful: 3 };
const BASE_URL = require('../../utils/api').BASE_URL;

Page({
  data: {
    entries: [],
    showCreate: false,
    mood: '',
    reflection: '',
    reflectionPlaceholder: '',
    creating: false,
    page: 1,
    hasMore: true,
    pageLoading: true,
    pageError: null,
    loadingMore: false,
    todayCard: null,
    topCard: '',
    moodTrend: '',

    // Weekly AI review
    weeklyReview: null,
    reviewLoading: false,
    reviewError: null,

    // Card image error
    diaryCardImgError: false,
    entryCardImgErrors: {},

    // Reflection prompt
    reflectionPrompt: '',
    reflectionPromptLoading: false,
    todayCardId: null,
    todayCardName: '',

    // Image upload
    selectedImage: '',
    uploadingImage: false,

    // Edit state
    editingEntryId: null,
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },

  async onShow() {
    this.setData({ page: 1, entries: [], pageLoading: true, weeklyReview: null });
    await this.loadEntries();
    await this._loadTodayCard();
    this._loadReflectionPrompt();
  },

  async loadEntries() {
    try {
      const data = await request(`/diary/entries?page=${this.data.page}`);
      const rawEntries = data.entries || [];
      // Compute card thumbnail paths for each entry
      const entries = [...this.data.entries, ...rawEntries.map(e => {
        if (e.card) {
          e.cardImagePath = computeImagePath(e.card);
        }
        return e;
      })];
      this.setData({
        entries,
        hasMore: rawEntries.length === 20,
        pageLoading: false,
      });
      this._computeRetrospect();
      // Update placeholder after entries loaded
      this._updatePlaceholder();
      // Auto-load weekly review if enough entries
      if (entries.length >= 3 && !this.data.weeklyReview && !this.data.reviewLoading) {
        this._loadWeeklyReview();
      }
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  async loadMore() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.setData({ loadingMore: true, page: this.data.page + 1 });
    await this.loadEntries();
    this.setData({ loadingMore: false });
  },

  showCreateModal() {
    this.setData({
      showCreate: true,
      editingEntryId: null,
      selectedImage: '',
      mood: '',
      reflection: '',
      diaryCardImgError: false,
    });
  },

  hideCreateModal() {
    this.setData({
      showCreate: false,
      editingEntryId: null,
      mood: '',
      reflection: '',
      selectedImage: '',
    });
  },

  preventClose() {
    // 阻止事件冒泡——防止点击 modal 内部元素时关闭弹窗
  },

  /** Handle card thumbnail load error in diary create modal */
  onDiaryCardImgError() {
    this.setData({ diaryCardImgError: true });
  },

  onMoodSelect(e) {
    this.setData({ mood: e.currentTarget.dataset.mood });
  },

  onReflectionInput(e) {
    this.setData({ reflection: e.detail.value });
  },

  async onCreateEntry() {
    if (this.data.creating) return;
    if (!this.data.mood) {
      wx.showToast({ title: '请选择心情', icon: 'none' });
      return;
    }
    this.setData({ creating: true });

    // Upload image first if selected
    let imageUrl = '';
    if (this.data.selectedImage) {
      try {
        imageUrl = await this._uploadImage(this.data.selectedImage);
      } catch (err) {
        wx.showToast({ title: '图片上传失败', icon: 'none' });
        this.setData({ creating: false });
        return;
      }
    }

    const editingEntryId = this.data.editingEntryId;
    try {
      if (editingEntryId) {
        // Edit existing entry
        const entry = await request(`/diary/entries/${editingEntryId}`, {
          method: 'PUT',
          data: {
            mood: this.data.mood,
            reflection: this.data.reflection,
            image_url: imageUrl || undefined,
          },
        });
        if (!entry) {
          throw new Error('更新日记失败');
        }
        // Update entry in list
        const updatedEntries = this.data.entries.map(e =>
          e.id === editingEntryId ? entry : e
        );
        this.setData({
          entries: updatedEntries,
          showCreate: false,
          editingEntryId: null,
          mood: '',
          reflection: '',
          selectedImage: '',
          creating: false,
        });
        wx.showToast({ title: '更新成功 ✨', icon: 'success' });
      } else {
        // Create new entry
        const entry = await request('/diary/entries', {
          method: 'POST',
          data: {
            mood: this.data.mood,
            reflection: this.data.reflection,
            card_id: this.data.todayCardId || undefined,
            image_url: imageUrl || undefined,
          },
        });
        if (!entry) {
          throw new Error('创建日记失败');
        }
        this.setData({
          entries: [entry, ...this.data.entries],
          showCreate: false,
          mood: '',
          reflection: '',
          selectedImage: '',
          creating: false,
        });
        wx.showToast({ title: '记录成功 ✨', icon: 'success' });
      }
      // Refresh weekly review after new entry
      if (this.data.entries.length >= 3) {
        this._loadWeeklyReview();
      }
    } catch (err) {
      wx.showToast({ title: editingEntryId ? '更新失败' : '记录失败', icon: 'none' });
      this.setData({ creating: false });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true, page: 1, entries: [], weeklyReview: null });
    this.loadEntries();
  },

  /** Load today's card to show in the editor header */
  async _loadTodayCard() {
    try {
      const card = await request('/cards/daily');
      card.imagePath = computeImagePath(card);
      this.setData({ todayCard: card });
      // Also store in globalData for reflection prompt consumption
      const app = getApp();
      if (app) {
        app.globalData = app.globalData || {};
        app.globalData.dailyCard = card;
      }
      this._updatePlaceholder();
    } catch(e) {
      // 静默降级——今日卡牌加载失败不影响记录列表
    }
  },

  /** Update textarea placeholder based on today's card context */
  _updatePlaceholder() {
    const card = this.data.todayCard;
    if (card && card.name_zh) {
      this.setData({
        reflectionPlaceholder: `这张${card.name_zh}让你想到了什么？你此刻的心情是怎样的？`
      });
    } else {
      this.setData({
        reflectionPlaceholder: '此刻你的心情是怎样的？'
      });
    }
  },

  /** Load AI-generated reflection prompt based on today's card */
  _loadReflectionPrompt() {
    const app = getApp();
    const dailyCard = app.globalData?.dailyCard;
    if (!dailyCard || !dailyCard.id) return;

    this.setData({
      todayCardId: dailyCard.id,
      todayCardName: dailyCard.name_zh || '',
      reflectionPromptLoading: true,
    });

    request('/diary/reflection-prompt', 'POST', {
      card_id: dailyCard.id,
      card_name: dailyCard.name_zh || '',
    }).then(res => {
      this.setData({
        reflectionPrompt: res.question || '',
        reflectionPromptLoading: false,
      });
    }).catch(() => {
      // 降级: 使用本地默认问题
      this.setData({
        reflectionPrompt: `今天的「${this.data.todayCardName}」给你带来了什么感受？`,
        reflectionPromptLoading: false,
      });
    });
  },

  /** Compute local fallback retrospect data (kept for backward compat) */
  _computeRetrospect() {
    const entries = this.data.entries;
    if (entries.length < 3) return;

    // 统计最常出现的牌
    const cardCount = {};
    entries.forEach(e => {
      const name = e.card?.name_zh;
      if (name) cardCount[name] = (cardCount[name] || 0) + 1;
    });
    const topEntry = Object.entries(cardCount).sort((a, b) => b[1] - a[1])[0];
    const topCard = topEntry?.[0] || '未知';

    // 心情趋势：最近3条记录的平均心情（1-5分）
    const recent = entries.slice(0, 3);
    const avgMood = recent.reduce((s, e) => {
      return s + (e.mood_score || MOOD_SCORE_MAP[e.mood] || 3);
    }, 0) / recent.length;
    const moodTrend = avgMood > 3.5 ? '在变好 ✦' : avgMood < 2.5 ? '有些低落' : '比较平稳';

    this.setData({ topCard, moodTrend });
  },

  // ============================================================
  // AI Weekly Review
  // ============================================================

  /** Fetch AI weekly review from backend */
  async _loadWeeklyReview() {
    if (this.data.reviewLoading) return;
    this.setData({ reviewLoading: true, reviewError: null });
    try {
      const review = await request('/diary/review?period=weekly');
      // Compute emoji trend curve for mood visualization
      if (review.mood_trends && review.mood_trends.length > 0) {
        review.moodTrendCurve = this._computeMoodTrendCurve(review.mood_trends);
      }
      this.setData({ weeklyReview: review, reviewLoading: false });
    } catch (err) {
      this.setData({ reviewLoading: false, reviewError: getFriendlyError(err) });
    }
  },

  /** User tap to refresh weekly review */
  onRefreshReview() {
    this._loadWeeklyReview();
    wx.vibrateShort({ type: 'light' }).catch(() => {});
  },

  /** Get CSS width percentage for mood chart bar */
  _getMoodBarWidth(score) {
    return Math.max(10, (score / 5) * 100);
  },

  /** Compute emoji mood trend curve from weekly review data */
  _computeMoodTrendCurve(trends) {
    const BLOCK_MAP = ['▁', '▁', '▂', '▃', '▅', '▇'];
    const blocks = trends.map(t => {
      const score = Math.round(t.mood_score || 3);
      return BLOCK_MAP[Math.min(Math.max(score, 1), 5)];
    });
    return '😔 ' + blocks.join(' ') + ' 😊';
  },

  /** Handle entry card image load error — hide the broken thumbnail */
  onEntryCardImageError(e) {
    const entryId = e.currentTarget.dataset.entryId;
    if (!entryId) return;
    const key = `entryCardImgErrors.${entryId}`;
    this.setData({ [key]: true });
  },

  /** Floating AI review button tap — scroll to review card */
  onTapFloatingReview() {
    wx.pageScrollTo({
      selector: '.review-card',
      duration: 300,
    });
  },

  // ============================================================
  // Image Selection & Upload
  // ============================================================

  /** Choose an image from album or camera */
  onChooseImage() {
    wx.chooseImage({
      count: 1,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        this.setData({ selectedImage: res.tempFilePaths[0] });
      },
    });
  },

  /** Remove the selected image */
  onRemoveImage() {
    this.setData({ selectedImage: '' });
  },

  /** Upload an image file to the server and return the URL */
  _uploadImage(filePath) {
    return new Promise((resolve, reject) => {
      const token = wx.getStorageSync('token');
      wx.uploadFile({
        url: `${BASE_URL}/diary/upload-image`,
        filePath: filePath,
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
        fail: (err) => {
          reject(err);
        },
      });
    });
  },

  // ============================================================
  // Long-press: Edit & Delete
  // ============================================================

  /** Long-press on an entry shows action sheet */
  onLongPressEntry(e) {
    const id = e.currentTarget.dataset.id;
    wx.showActionSheet({
      itemList: ['编辑', '删除'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this._editEntry(id);
        } else if (res.tapIndex === 1) {
          this._deleteEntry(id);
        }
      },
    });
  },

  /** Populate the composer with an existing entry for editing */
  _editEntry(id) {
    const entry = this.data.entries.find(e => e.id === id);
    if (!entry) return;
    this.setData({
      showCreate: true,
      editingEntryId: id,
      mood: entry.mood || '',
      reflection: entry.reflection || '',
      selectedImage: entry.image_url || '',
    });
  },

  /** Confirm and delete a diary entry */
  _deleteEntry(id) {
    wx.showModal({
      title: '删除日记',
      content: '确定要删除这条日记吗？删除后无法恢复。',
      success: (res) => {
        if (res.confirm) {
          request(`/diary/entries/${id}`, { method: 'DELETE' }).then(() => {
            const remaining = this.data.entries.filter(e => e.id !== id);
            this.setData({ entries: remaining });
            wx.showToast({ title: '已删除', icon: 'success' });
          }).catch(() => {
            wx.showToast({ title: '删除失败', icon: 'none' });
          });
        }
      },
    });
  },

  // ============================================================
  // Share Diary Entry as Image Card
  // ============================================================

  /** Generate and preview a share image for a diary entry */
  onShareEntry(e) {
    const id = e.currentTarget.dataset.id;
    const entry = this.data.entries.find(e => e.id === id);
    if (!entry) return;

    wx.showLoading({ title: '生成分享图...' });

    const { generateDiaryCard } = require('../../utils/canvas-poster');
    generateDiaryCard(entry, this).then((imagePath) => {
      wx.hideLoading();
      wx.previewImage({ urls: [imagePath] });
    }).catch((err) => {
      wx.hideLoading();
      wx.showToast({ title: '生成失败', icon: 'none' });
    });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
