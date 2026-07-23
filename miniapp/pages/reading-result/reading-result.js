// pages/reading-result/reading-result.js
const { request, getFriendlyError } = require('../../utils/api');
const { cardEnter } = require('../../utils/animate');
const { computeImagePath } = require('../../utils/cards');
const { playCardRevealSound } = require('../../utils/sound');

// ---- Persona data (must match reading.js PERSONAS) ----
const PERSONA_DATA = {
  gentle_star: { name: '温和的星', icon: '✦', signature: '— 来自 温和的星 ✦ 愿你被星光温柔以待' },
  wise_moon:   { name: '智慧的月', icon: '☽', signature: '— 来自 智慧的月 ☽ 愿你的心如月光般澄明' },
  frank_sun:   { name: '率直的太阳', icon: '☀', signature: '— 来自 率直的太阳 ☀ 直面真相，才有改变的力量' },
};

// ---- Spread type key → Chinese name (must match reading.js SPREADS) ----
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

Page({
  data: {
    reading: null,
    personaDisplay: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,
    showFullInterpretation: false,

    // 3-stage loading sequence
    loadingStage: 1,        // 1 = 洗牌中, 2 = 翻牌中, 3 = 星光解读中
    loadingDotCount: 0,     // 0..3 — how many dots are lit in stage 3
    loadingTimeText: '',    // dynamic status text in stage 3
    showWaitOptions: false, // show the "continue waiting?" UI after timeout

    // Quick / immersive mode
    isQuick: false,
    isImmersive: false,

    // Save / share
    isSaved: false,         // whether this reading is in saved_readings storage

    // Undo reading
    showUndo: false,

    // ---- wx.createAnimation native animation system ----
    useNativeAnim: true,
    // Staggered card entrance animations (one per drawn card)
    cardAnimData: [],

    // Share poster
    showSharePoster: false,
    shareCardImage: '',
    shareCardName: '',
    shareKeyInsight: '',
    userNickname: '',

    // Interactive card enlargement
    enlargedCardIndex: -1,   // -1 = none; 0/1/2 = which card is enlarged
    isFlipped: false,        // front (false) or back (true)
    flipState: '',           // '' | 'flip-out' | 'flip-in'
    isAnimatingExit: false,  // true during exit animation before reset

    // TL;DR summary
    tldr: [],

    // Onboarding Step 3
    showOnboarding: false,
    onboardingStep: 0,
  },

  onLoad(options) {
    const id = options && options.id;
    const isPending = options && options.pending === '1';
    const spread = options && options.spread;
    const isQuick = options && options.quick === '1';

    if (!id && !isPending) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      wx.navigateBack();
      return;
    }

    if (isPending) {
      // New reading — create via API with full loading animation
      this._pendingSpread = spread || 'three_card';
      this._cachedReading = null;
      this._cachedError = null;

      if (isQuick) {
        // Quick mode: skip all loading stages, show result as soon as it arrives
        this._isQuickMode = true;
        this.setData({ isQuick: true, isImmersive: false, pageLoading: false });
        this._createReading();
      } else {
        // Immersive mode: full 3-stage animation
        this.setData({ isQuick: false, isImmersive: true });
        this._startStages();
        this._createReading();
      }
      return;
    }

    this._id = id;
    this._cachedReading = null;
    this.setData({ isQuick: false, isImmersive: true });

    // Check if already saved in local storage
    const saved = wx.getStorageSync('saved_readings') || [];
    this.setData({ isSaved: saved.includes(id) });
    this._cachedError = null;

    // Start the 3-stage ritual animation
    this._startStages();

    // Fire the API call in parallel — result is cached until stage 3 begins
    this._load();
  },

  /* ---------------------------------------------------------------
     New reading creation (pending mode) — makes AI API call
     --------------------------------------------------------------- */
  async _createReading() {
    const pending = wx.getStorageSync('pending_reading');
    const data = {
      spread_type: this._pendingSpread,
      question: (pending && pending.question) || null,
      theme: (pending && pending.theme) || 'general',
      persona: (pending && pending.persona) || null,
    };
    try {
      const result = await request(`/readings/spread/${this._pendingSpread}`, {
        method: 'POST',
        data: data,
      });
      if (this._destroyed) return;
      wx.removeStorageSync('pending_reading');
      this._cachedReading = result;
      this._tryShowResult();
    } catch (err) {
      if (this._destroyed) return;
      this._cachedError = getFriendlyError(err);
      // Show error after stages complete, or immediately if timeout
      this._tryShowResult();
    }
  },

  /* ---------------------------------------------------------------
     Stage Progression
     --------------------------------------------------------------- */

  _startStages() {
    this.setData({ loadingStage: 1, loadingDotCount: 0, loadingTimeText: '', showWaitOptions: false });

    // Stage 1: 洗牌中 — 2s (Emphasis: ritual pacing, not motion timing)
    this._stageTimer1 = setTimeout(() => {
      if (this._destroyed) return;

      // Stage 2: 翻牌中 — 2s (Emphasis: ritual pacing)
      this.setData({ loadingStage: 2 });
      this._stageTimer2 = setTimeout(() => {
        if (this._destroyed) return;

        // Stage 3: 星光解读中 — real waiting with progress feedback
        this.setData({
          loadingStage: 3,
          loadingDotCount: 0,
          loadingTimeText: '约 15-20 秒',
          showWaitOptions: false,
        });
        this._startStage3();
        // If the API already returned during stages 1-2, show result now
        this._tryShowResult();
      }, 2000);
    }, 2000);
  },

  /* ---------------------------------------------------------------
     Stage 3 — Progress Dots + Timeout Messages
     --------------------------------------------------------------- */

  _startStage3() {
    // Light up one dot every ~5s (3 dots total ≈ 15s) — UX pacing for anticipation
    this._dotTimer = setInterval(() => {
      if (this._destroyed) return;
      const next = Math.min(this.data.loadingDotCount + 1, 3);
      this.setData({ loadingDotCount: next });
    }, 5000);

    // After 3 seconds: show "AI正在仔细分析你的牌面..." for perceived speed
    this._timeout3 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: 'AI正在仔细分析你的牌面...' });
    }, 3000);

    // After 25 seconds: polite nudge
    this._timeout25 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '仍在努力中，请稍等...' });
    }, 25000);

    // After 50 seconds: firmer nudge
    this._timeout50 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '可能需要更长时间，请耐心等待...' });
    }, 50000);

    // After 55 seconds: offer a choice
    this._timeout55 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '', showWaitOptions: true });
    }, 55000);
  },

  /* ---------------------------------------------------------------
     API Fetch — runs in parallel with stages
     --------------------------------------------------------------- */

  async _load() {
    try {
      const reading = await request('/readings/' + this._id);
      if (this._destroyed) return;

      // Clean AI Markdown formatting
      if (reading && reading.interpretation) {
        reading.interpretation = reading.interpretation
          .replace(/^#{1,4}\s+(\*\*)?[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]*(\*\*)?\s*/gmu, '')
          .replace(/\*\*(.+?)\*\*/g, '$1')
          .replace(/^---+\s*$/gm, '')
          .replace(/^\*\s+/gm, '· ')
          .replace(/^-\s+/gm, '')
          .replace(/\n{3,}/g, '\n\n')
          .trim();
      }

      // Compute image paths for each drawn card
      if (reading && reading.drawn_cards) {
        reading.drawn_cards = reading.drawn_cards.map(card => ({
          ...card,
          imagePath: computeImagePath(card),
        }));
      }

      this._cachedReading = reading;
      this._tryShowResult();
    } catch (err) {
      if (this._destroyed) return;
      this._cachedError = getFriendlyError(err);
      this._tryShowResult();
    }
  },

  /* ---------------------------------------------------------------
     TL;DR Extraction — pull 3 concise summary lines from interpretation
     --------------------------------------------------------------- */

  _extractTLDR(text) {
    if (!text || typeof text !== 'string') return [];

    // Strategy 1: Look for structured markers — "**过去**", "**现在**", "**未来**"
    const sectionRegex = /\*{2}(过去|现在|未来|past|present|future)\*{2}[:：]?\s*([^\n]+)/gi;
    const sectionMatches = [];
    let match;
    while ((match = sectionRegex.exec(text)) !== null && sectionMatches.length < 3) {
      const sentence = match[2].trim();
      if (sentence) sectionMatches.push(sentence);
    }
    if (sectionMatches.length === 3) {
      return sectionMatches.map(s => s.length > 30 ? s.slice(0, 27) + '...' : s);
    }

    // Strategy 2: Look for numbered sections — "1. 过去" or "①" patterns
    const numberedRegex = /(?:^|\n)\s*(?:\d+[\.\、]|[①②③④])\s*[：:]?\s*([^\n]{4,80})/gm;
    const numberedMatches = [];
    while ((match = numberedRegex.exec(text)) !== null && numberedMatches.length < 3) {
      const sentence = match[1].trim();
      if (sentence) numberedMatches.push(sentence);
    }
    if (numberedMatches.length === 3) {
      return numberedMatches.map(s => s.length > 30 ? s.slice(0, 27) + '...' : s);
    }

    // Strategy 3: Split by double newlines → take first sentence of first 3 paragraphs
    const paragraphs = text.split(/\n{2,}/).filter(p => p.trim().length > 10);
    const paraLines = [];
    for (const para of paragraphs) {
      if (paraLines.length >= 3) break;
      // First sentence of paragraph (split by 。！？ and take first segment)
      const firstSentence = para.split(/[。！？]/)[0].trim();
      // Remove leading markers like "- ", "· ", or "**"
      const cleaned = firstSentence.replace(/^[-·\*\s　]+/, '').trim();
      if (cleaned && cleaned.length > 4) paraLines.push(cleaned);
    }
    if (paraLines.length >= 1) {
      return paraLines.slice(0, 3).map(s => s.length > 30 ? s.slice(0, 27) + '...' : s);
    }

    // Strategy 4: Ultimate fallback — first 3 sentences split by 。！？
    const sentences = text.split(/[。！？]/).filter(s => s.trim().length > 4);
    return sentences.slice(0, 3).map(s => {
      const cleaned = s.replace(/^[-·\*\s　]+/, '').trim();
      return cleaned.length > 30 ? cleaned.slice(0, 27) + '...' : cleaned;
    });
  },

  /* ---------------------------------------------------------------
     Transition to Result
     Only fires when both stage 3 has begun AND the API has returned,
     so stages 1-2 always play through in full.
     --------------------------------------------------------------- */

  _tryShowResult() {
    // Quick mode bypass — no loading stages to wait for
    if (!this._isQuickMode && this.data.loadingStage !== 3) return;

    this._clearStage3Timers();

    if (this._cachedReading) {
      let reading = this._cachedReading;
      const spreadTypeName = SPREAD_TYPE_NAMES[reading.spread_type]
        || reading.spread_type
        || '三牌占卜';

      // Quick mode: prepend ⚡ 快速解读 marker to interpretation text
      if (this._isQuickMode && reading.interpretation) {
        reading = { ...reading, interpretation: '⚡ 快速解读\n\n' + reading.interpretation };
      }

      // Append persona signature to interpretation
      let personaDisplay = null;
      if (reading.persona) {
        const pData = PERSONA_DATA[reading.persona];
        if (pData) {
          personaDisplay = { name: pData.name, icon: pData.icon, signature: pData.signature };
          // Append signature to the end of interpretation text
          if (reading.interpretation) {
            reading = {
              ...reading,
              interpretation: reading.interpretation + '\n\n' + pData.signature,
            };
          }
        }
      }

      const tldr = this._extractTLDR(reading.interpretation);
      this.setData({ reading, personaDisplay, tldr, spreadTypeName, pageLoading: false, showUndo: true, showFullInterpretation: false });
      // Trigger staggered card entrance animation after render
      this._animateCardReveal();
      // Play reveal sound when reading result appears
      try { playCardRevealSound(); } catch(e) {}

      // ── Onboarding Step 3: hint next to action items ──
      const onboardingCompleted = wx.getStorageSync('onboarding_completed');
      const onboardingStep = wx.getStorageSync('onboarding_step') || 1;
      if (!onboardingCompleted && onboardingStep === 3) {
        this.setData({ showOnboarding: true, onboardingStep: 3 });
        this._onboardingTimer = setTimeout(() => {
          this.setData({ showOnboarding: false });
          wx.setStorageSync('onboarding_completed', true);
          wx.removeStorageSync('onboarding_step');
        }, 5000);
      }
    } else if (this._cachedError) {
      this.setData({ pageLoading: false, pageError: this._cachedError });
    }
  },

  /* ---------------------------------------------------------------
     Timer Cleanup
     --------------------------------------------------------------- */

  _clearStageTimers() {
    if (this._stageTimer1) { clearTimeout(this._stageTimer1); this._stageTimer1 = null; }
    if (this._stageTimer2) { clearTimeout(this._stageTimer2); this._stageTimer2 = null; }
    this._clearStage3Timers();
  },

  _clearStage3Timers() {
    if (this._dotTimer) { clearInterval(this._dotTimer); this._dotTimer = null; }
    if (this._timeout3) { clearTimeout(this._timeout3); this._timeout3 = null; }
    if (this._timeout25) { clearTimeout(this._timeout25); this._timeout25 = null; }
    if (this._timeout50) { clearTimeout(this._timeout50); this._timeout50 = null; }
    if (this._timeout55) { clearTimeout(this._timeout55); this._timeout55 = null; }
  },

  /** Animate drawn cards appearing one by one using wx.createAnimation stagger */
  _animateCardReveal() {
    if (!this.data.useNativeAnim) return;
    const cards = this.data.reading && this.data.reading.drawn_cards;
    if (!cards || cards.length === 0) return;

    const anims = [];
    for (let i = 0; i < cards.length; i++) {
      // Each card enters with cardEnter + increasing delay for cascade effect
      anims.push(cardEnter(450, i * 120));
    }
    this.setData({ cardAnimData: anims });
  },

  /* ---------------------------------------------------------------
     Handlers
     --------------------------------------------------------------- */

  // —— Card image loading ——
  onCardImgLoad(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`reading.drawn_cards[${idx}]._imgLoaded`]: true });
    }
  },

  onCardImgError(e) {
    const idx = e.currentTarget.dataset.index;
    if (idx !== undefined && idx !== '') {
      this.setData({ [`reading.drawn_cards[${idx}]._imgError`]: true });
    }
  },

  onEnlargedImgLoad() {
    this.setData({ enlargedImgLoaded: true });
  },

  onUnload() {
    this._destroyed = true;
    this._clearStageTimers();
    if (this._onboardingTimer) {
      clearTimeout(this._onboardingTimer);
      this._onboardingTimer = null;
    }
  },

  onShow() {
    // Check if a background reading was completed while we were away
    const completed = wx.getStorageSync('reading_completed');
    if (completed) {
      wx.removeStorageSync('reading_completed');
      wx.removeStorageSync('background_reading');
      wx.showToast({
        title: '解读已生成！',
        icon: 'success',
        duration: 2000,
      });
    }
  },

  onContinueWaiting() {
    this.setData({ showWaitOptions: false, loadingTimeText: '好的，继续为你解读...' });

    // Restart the 55-second timer so the prompt can reappear later
    if (this._timeout55) { clearTimeout(this._timeout55); }
    this._timeout55 = setTimeout(() => {
      if (this._destroyed) return;
      this.setData({ loadingTimeText: '', showWaitOptions: true });
    }, 55000);
  },

  onCheckLater() {
    this._clearStageTimers();
    // Save as pending background reading so user can pick up later
    const pending = wx.getStorageSync('pending_reading');
    if (pending) {
      wx.setStorageSync('background_reading', {
        spread: pending.spread_type,
        question: pending.question,
        theme: pending.theme,
        persona: pending.persona || null,
        timestamp: Date.now(),
      });
    }
    wx.showToast({ title: '解读生成后可在记录中查看', icon: 'none', duration: 2000 });
    setTimeout(() => { wx.navigateBack(); }, 2200);
  },

  onCardSwiperChange(e) {
    this.setData({ activeCardIndex: e.detail.current });
  },

  /* ---------------------------------------------------------------
     Interactive Card — Tap to Enlarge
     --------------------------------------------------------------- */

  onCardTap(e) {
    const index = e.currentTarget.dataset.index;
    if (index === undefined) return;
    this.setData({
      enlargedCardIndex: index,
      isFlipped: false,
      flipState: '',
      isAnimatingExit: false,
    });
  },

  onEnlargedCardTap() {
    if (this.data.isAnimatingExit) return;
    if (this.data.flipState === 'flip-out' || this.data.flipState === 'flip-in') return;

    // Phase 1: collapse scaleX(1→0)
    this.setData({ flipState: 'flip-out' });

    setTimeout(() => {
      if (this._destroyed) return;
      // Phase 2: swap content, expand scaleX(0→1)
      this.setData({ isFlipped: !this.data.isFlipped, flipState: 'flip-in' });

      setTimeout(() => {
        if (this._destroyed) return;
        this.setData({ flipState: '' });
      }, 200);
    }, 200);
  },

  onOverlayTap() {
    if (this.data.isAnimatingExit) return;
    // Start exit animation
    this.setData({ isAnimatingExit: true });
    setTimeout(() => {
      if (this._destroyed) return;
      this.setData({
        enlargedCardIndex: -1,
        isFlipped: false,
        flipState: '',
        isAnimatingExit: false,
      });
    }, 300);
  },

  /* ---- Swipe down to dismiss ---- */
  onOverlayTouchStart(e) {
    this._touchStartY = e.touches[0].clientY;
  },

  onOverlayTouchMove(e) {
    // prevent pull-to-refresh / page scroll
  },

  onOverlayTouchEnd(e) {
    if (!this._touchStartY) return;
    const deltaY = e.changedTouches[0].clientY - this._touchStartY;
    if (deltaY > 80) {
      this._touchStartY = 0;
      if (!this.data.isAnimatingExit) this.onOverlayTap();
    }
    this._touchStartY = 0;
  },

  onToggleFull() {
    this.setData({ showFullInterpretation: !this.data.showFullInterpretation });
  },

  onRetry() {
    this._clearStageTimers();
    this._destroyed = false;
    this._cachedReading = null;
    this._cachedError = null;
    this._startStages();
    this._load();
  },

  onAskMore() {
    const reading = this.data.reading;
    if (!reading) return;
    wx.navigateTo({ url: '/pages/chat/chat?readingId=' + reading.id });
  },

  onNewReading() {
    wx.navigateBack();
  },

  /** Undo the current reading — allows user to re-draw cards */
  onUndoReading() {
    const reading = this.data.reading;
    wx.showModal({
      title: '重新抽牌',
      content: '确定要放弃本次解读，重新抽牌吗？',
      success: (res) => {
        if (res.confirm) {
          wx.removeStorageSync('pending_reading');
          wx.redirectTo({
            url: '/pages/reading/reading?type=' + (reading?.spread_type || 'three_card'),
          });
        }
      },
    });
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  /* ---------------------------------------------------------------
     Action Cards — all items checked
     --------------------------------------------------------------- */

  onAllActionsChecked(e) {
    try { wx.vibrateShort({ type: 'medium' }); } catch(e) {}
    const { readingId } = e.detail;
    wx.showToast({
      title: '全部完成 ✦',
      icon: 'none',
      duration: 2000,
    });
  },

  /* ---------------------------------------------------------------
     Share — WeChat built-in share (personalized)
     --------------------------------------------------------------- */

  onShareAppMessage() {
    const reading = this.data.reading;
    if (!reading) return { title: '星光塔罗解读' };

    // Extract a 15-char key insight from the interpretation
    let keyInsight = '';
    if (reading.interpretation) {
      const clean = reading.interpretation
        .replace(/#{1,4}\s+/g, '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\n+/g, '')
        .trim();
      keyInsight = clean.length > 15 ? clean.slice(0, 15) + '…' : clean;
    }

    // Use first card name if available
    let cardName = '星光塔罗';
    if (reading.drawn_cards && reading.drawn_cards.length > 0) {
      cardName = reading.drawn_cards[0].card_name_zh
        || reading.drawn_cards[0].card_name
        || '星光塔罗';
    }

    const spreadName = SPREAD_TYPE_NAMES[reading.spread_type] || reading.spread_type || '三牌占卜';

    // Personalized share text
    const title = keyInsight
      ? `我抽到了「${cardName}」—— ${keyInsight} ✦ 你也来试试星光塔罗`
      : `我的星光解读 ✦ ${spreadName}`;

    // Track share event and show reward toast on success
    const user = wx.getStorageSync('user') || {};
    const sharerId = user.id || '';

    if (sharerId) {
      // Fire-and-forget share tracking
      request('/share/track', {
        method: 'POST',
        data: {
          sharer_id: sharerId,
          channel: 'wechat_friend',
          share_type: 'reading',
          ref_id: reading.id,
        },
      }).then((res) => {
        if (res && res.rewarded) {
          wx.showToast({
            title: '分享成功！奖励已发放 ✦',
            icon: 'success',
            duration: 2000,
          });
        }
        // Set flag so the index page can show tier progress feedback
        wx.setStorageSync('_share_success_flag', true);
      }).catch(() => {
        // Silent fail — still set flag so homepage banner can show
        wx.setStorageSync('_share_success_flag', true);
      });
    }

    return {
      title: title,
      path: `/pages/reading-result/reading-result?id=${reading.id}`,
    };
  },

  /* ---------------------------------------------------------------
     Share Poster — Open / Close
     --------------------------------------------------------------- */

  onOpenSharePoster() {
    const reading = this.data.reading;
    if (!reading || !reading.drawn_cards || reading.drawn_cards.length === 0) {
      wx.showToast({ title: '暂无牌面可生成海报', icon: 'none' });
      return;
    }

    // Use the first drawn card for the poster
    const firstCard = reading.drawn_cards[0];
    const cardImage = firstCard.imagePath || '';
    const cardName = (firstCard.card_name_zh || firstCard.card_name || '') +
      ' · ' + (firstCard.card_name_en || firstCard.name_en || '');

    // Extract a short key insight (15 chars) for the poster
    let keyInsight = '';
    if (reading.interpretation) {
      const clean = reading.interpretation
        .replace(/#{1,4}\s+/g, '')
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\n+/g, '')
        .trim();
      keyInsight = clean.length > 15 ? clean.slice(0, 15) + '…' : clean;
    }

    // Get user nickname
    const user = wx.getStorageSync('user') || {};
    const nickname = user.nickname || user.nickName || '';

    this.setData({
      showSharePoster: true,
      shareCardImage: cardImage,
      shareCardName: cardName,
      shareKeyInsight: keyInsight,
      userNickname: nickname,
    });
  },

  onCloseSharePoster() {
    this.setData({ showSharePoster: false });
  },

  onSharePosterToFriend(e) {
    // Forward the poster image path to the native share API
    // WeChat doesn't support custom image via onShareAppMessage directly,
    // so we use wx.shareAppMessage (available in newer base libs)
    // or fall back to letting the user save + share manually
    const imagePath = e.detail && e.detail.imagePath;
    if (imagePath) {
      // Attempt to use WeChat's share with image
      // Note: wx.shareAppMessage is only available in some WeChat versions
      try {
        wx.shareAppMessage({
          imageUrl: imagePath,
          title: '星光映照 · 塔罗解读',
        });
      } catch (err) {
        // Fallback: inform user to save first
        wx.showToast({
          title: '请先保存海报，再从相册分享',
          icon: 'none',
          duration: 2000,
        });
      }
    }
  },

  /* ---------------------------------------------------------------
     Save / Unsave — local storage
     --------------------------------------------------------------- */

  onSaveReading() {
    const reading = this.data.reading;
    if (!reading) return;

    const saved = wx.getStorageSync('saved_readings') || [];
    if (saved.includes(reading.id)) {
      this.setData({ isSaved: true });
      wx.showToast({ title: '已收藏', icon: 'success' });
      return;
    }
    saved.push(reading.id);
    wx.setStorageSync('saved_readings', saved);
    this.setData({ isSaved: true });
    wx.showToast({ title: '已收藏', icon: 'success' });
  },

  onUnsaveReading() {
    const reading = this.data.reading;
    if (!reading) return;

    let saved = wx.getStorageSync('saved_readings') || [];
    saved = saved.filter(id => id !== reading.id);
    wx.setStorageSync('saved_readings', saved);
    this.setData({ isSaved: false });
    wx.showToast({ title: '已取消收藏', icon: 'none' });
  },
});
