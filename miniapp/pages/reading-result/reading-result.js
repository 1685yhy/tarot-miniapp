// pages/reading-result/reading-result.js
const { request, getFriendlyError } = require('../../utils/api');
const { cardEnter } = require('../../utils/animate');
const { computeImagePath, pngFallbackPath } = require('../../utils/cards');
const { playCardRevealSound } = require('../../utils/sound');
const analytics = require('../../utils/analytics');

// ---- Persona data (must match reading.js PERSONAS) ----
const PERSONA_DATA = {
  gentle_star: { name: '温和的星', icon: '✦', signature: '— 来自 温和的星 ✦ 愿你被星光温柔以待' },
  wise_moon:   { name: '智慧的月', icon: '☽', signature: '— 来自 智慧的月 ☽ 愿你的心如月光般澄明' },
  frank_sun:   { name: '率直的太阳', icon: '☀', signature: '— 来自 率直的太阳 ☀ 直面真相，才有改变的力量' },
};

// ---- Persona info with descriptions for badge (must match ai_personas.py) ----
const PERSONA_INFO = {
  gentle_star: { icon: '✦', name: '温和的星', desc: '温暖陪伴 · 适合情感话题' },
  wise_moon:   { icon: '☽', name: '智慧的月', desc: '理性分析 · 适合事业决策' },
  frank_sun:   { icon: '☀', name: '率直的太阳', desc: '直击要害 · 敢于面对真相' },
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

// ---- Loading timing (ms) ----
// Quick mode (default): lightweight skeleton shown for a minimum of 800ms,
// then results appear the moment the API returns.
const QUICK_MIN_MS = 800;
// Immersive mode (opt-in): single "正在解读..." pulsing state that lasts
// at most 2s — after that the result appears as soon as the API returns.
const IMMERSIVE_MAX_MS = 2000;

Page({
  data: {
    reading: null,
    personaDisplay: null,
    pageLoading: true,
    pageError: null,
    activeCardIndex: 0,

    // Loading states (single-stage: quick skeleton / immersive pulse)
    loadingStage: 1,

    // Quick / immersive mode
    isQuick: false,
    isImmersive: false,

    // Save / share
    isSaved: false,         // whether this reading is in saved_readings storage

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
    enlargedImgError: false, // true if the enlarged card image failed to load
    enlargedImgLoaded: false, // true once enlarged card image has loaded

    // TL;DR summary
    tldr: [],

    // Membership / user state
    isMember: false,

    // Share CTA state
    showShareCTA: false,

    // Onboarding Step 3
    showOnboarding: false,
    onboardingStep: 0,

    // Teaching data display — default expanded now
    showTeaching: true,
    hasTeachingData: false,
    teachingCards: [],

    // Task 4: Reflection question
    reflectionQuestion: '',
  },

  onLoad(options) {
    const id = options && options.id;
    const isPending = options && options.pending === '1';
    const spread = options && options.spread;
    const isQuick = options && options.quick === '1';

    // Load member status: check app.globalData first, fall back to storage
    const app = getApp();
    const isMember = app.globalData?.isMember || wx.getStorageSync('user')?.is_member || false;
    this.setData({ isMember });

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
        // Quick mode (default): lightweight skeleton — 800ms minimum,
        // then results appear as soon as the API returns
        this._isQuickMode = true;
        this._quickStartTime = Date.now();
        this._quickMinTimer = null;
        this.setData({ isQuick: true, isImmersive: false, pageLoading: true });
        this._createReading();
      } else {
        // Immersive mode (opt-in): single pulsing state, max 2s
        this.setData({ isQuick: false, isImmersive: true, pageLoading: true });
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

    // Start the single pulsing state
    this._startStages();

    // Fire the API call in parallel — result shows as soon as it returns
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
      zodiac: (pending && pending.zodiac) || '',
      depth: (pending && pending.depth) || 'standard',
    };
    try {
      const result = await request(`/readings/spread/${this._pendingSpread}`, {
        method: 'POST',
        data: data,
      });
      wx.removeStorageSync('pending_reading');
      // Always cache result — even if page was hidden (onShow will pick it up)
      this._cachedReading = result;
      if (!this._destroyed) { this._tryShowResult(); }
    } catch (err) {
      // Always cache error — even if page was hidden (onShow will pick it up)
      this._cachedError = getFriendlyError(err);
      if (!this._destroyed) { this._tryShowResult(); }
    }
  },

  /* ---------------------------------------------------------------
     Loading Progression
     --------------------------------------------------------------- */

  _startStages() {
    // Immersive mode: a single "正在解读..." pulsing state. It lasts at
    // most IMMERSIVE_MAX_MS — after that the result appears the moment
    // the API response arrives (no artificial delay added).
    this._immersiveStarted = true;
    this.setData({ loadingStage: 1 });
    this._stageTimer1 = setTimeout(() => {
      if (this._destroyed) return;
      this._tryShowResult();
    }, IMMERSIVE_MAX_MS);
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
          imagePath: computeImagePath(card, card.imageBase),
        }));
      }

      this._cachedReading = reading;
      if (!this._destroyed) { this._tryShowResult(); }
    } catch (err) {
      // Always cache error — even if page was hidden (onShow will pick it up)
      this._cachedError = getFriendlyError(err);
      if (!this._destroyed) { this._tryShowResult(); }
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
     - Quick mode: skeleton holds for at least QUICK_MIN_MS, then the
       result shows the moment the API has returned.
     - Immersive mode: fires once the pulse has started (at most
       IMMERSIVE_MAX_MS after start) AND the API has returned.
     --------------------------------------------------------------- */

  _tryShowResult() {
    // Quick mode: keep the skeleton on screen for at least 800ms so
    // content never flashes in.
    if (this._isQuickMode) {
      const elapsed = Date.now() - this._quickStartTime;
      if (elapsed < QUICK_MIN_MS) {
        if (!this._quickMinTimer) {
          this._quickMinTimer = setTimeout(() => {
            this._quickMinTimer = null;
            if (this._destroyed) return;
            this._tryShowResult();
          }, QUICK_MIN_MS - elapsed);
        }
        return;
      }
    } else if (!this._immersiveStarted) {
      return; // pulse has not started yet
    }

    this._clearStageTimers();

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
        const pInfo = PERSONA_INFO[reading.persona];
        if (pData) {
          personaDisplay = {
            name: pData.name,
            icon: pData.icon,
            signature: pData.signature,
            desc: pInfo ? pInfo.desc : '',
          };
          // Append signature to the end of interpretation text
          if (reading.interpretation) {
            reading = {
              ...reading,
              interpretation: reading.interpretation + '\n\n' + pData.signature,
            };
          }
        }
      }

      // Analytics: funnel — reading completed
      analytics.funnel('reading_completed', { spread_type: reading.spread_type });

      const tldr = this._extractTLDR(reading.interpretation);

      // Extract teaching data from drawn cards
      const teachingCards = [];
      if (reading.drawn_cards) {
        for (const card of reading.drawn_cards) {
          if (card.teaching && (card.teaching.symbols?.length > 0 || card.teaching.life_connection)) {
            teachingCards.push({
              card_id: card.card_id,
              card_name: card.card_name,
              symbols: card.teaching.symbols || [],
              life_connection: card.teaching.life_connection || '',
            });
          }
        }
      }
      const hasTeachingData = teachingCards.length > 0;

      const reflectionQuestion = reading.reflection_question || '今天的解读对你意味着什么？';
      this.setData({ reading, personaDisplay, tldr, teachingCards, hasTeachingData, spreadTypeName, pageLoading: false, reflectionQuestion });
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

      // ── Share CTA: show for non-members if not dismissed before ──
      const shareCtaDismissed = wx.getStorageSync('_share_cta_dismissed');
      if (!this.data.isMember && !shareCtaDismissed) {
        this.setData({ showShareCTA: true });
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
    if (this._quickMinTimer) { clearTimeout(this._quickMinTimer); this._quickMinTimer = null; }
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
    this.setData({ enlargedImgLoaded: true, enlargedImgError: false });
  },

  onEnlargedImgError() {
    // Retry once with PNG fallback before hiding the enlarged card image
    const idx = this.data.enlargedCardIndex;
    const cards = this.data.reading && this.data.reading.drawn_cards;
    const card = cards && idx >= 0 ? cards[idx] : null;
    if (card && card.imagePath && card.imagePath.endsWith('.webp') && !card._webpFallbackTried) {
      this.setData({
        [`reading.drawn_cards[${idx}]._webpFallbackTried`]: true,
        [`reading.drawn_cards[${idx}].imagePath`]: pngFallbackPath(card.imagePath),
      });
      return;
    }
    this.setData({ enlargedImgError: true, enlargedImgLoaded: false });
  },

  onUnload() {
    this._destroyed = true;
    this._clearStageTimers();
    if (this._onboardingTimer) { clearTimeout(this._onboardingTimer); this._onboardingTimer = null; }
    if (this._navBackTimer) { clearTimeout(this._navBackTimer); this._navBackTimer = null; }
  },

  onHide() {
    this._destroyed = true;
    this._clearStageTimers();
    if (this._onboardingTimer) { clearTimeout(this._onboardingTimer); this._onboardingTimer = null; }
    if (this._navBackTimer) { clearTimeout(this._navBackTimer); this._navBackTimer = null; }
  },

  onShow() {
    // If page was hidden mid-load, reset destroyed flag and check for cached result
    this._destroyed = false;
    if (this._cachedReading || this._cachedError) {
      this._tryShowResult();
    }
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
      enlargedImgError: false,
      enlargedImgLoaded: false,
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

  onToggleTeaching() {
    this.setData({ showTeaching: !this.data.showTeaching });
  },

  onRetry() {
    this._clearStageTimers();
    this._destroyed = false;
    this._cachedReading = null;
    this._cachedError = null;
    this.setData({ pageLoading: true, pageError: null });
    if (this._isQuickMode) {
      this._quickStartTime = Date.now();
      this._quickMinTimer = null;
    } else {
      this._startStages();
    }
    this._load();
  },

  onAskMore() {
    const reading = this.data.reading;
    if (!reading) return;
    const app = getApp();
    app.globalData.currentReading = reading;
    wx.navigateTo({ url: '/pages/chat/chat?readingId=' + reading.id });
  },

  onNewReading() {
    wx.navigateBack();
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  /** Navigate to diary page with the first card as reflection prompt */
  onGoDiaryFromReading() {
    const app = getApp();
    const cards = this.data.reading && this.data.reading.drawn_cards || [];
    if (cards.length > 0) {
      app.globalData.diaryCardHint = {
        card_id: cards[0].card_id,
        card_name: cards[0].card_name || cards[0].name_zh || '',
      };
    }
    wx.navigateTo({ url: '/pages/diary/diary' });
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
     Share CTA — Prompt user to share for rewards
     --------------------------------------------------------------- */

  /** User tapped the share CTA button */
  onShareCTA() {
    // The open-type="share" button triggers onShareAppMessage natively
    // This handler is for optional analytics; the actual share tracking
    // happens in onShareAppMessage
  },

  /** Dismiss the share CTA card permanently */
  onDismissShareCTA() {
    this.setData({ showShareCTA: false });
    wx.setStorageSync('_share_cta_dismissed', true);
  },

  /* ---------------------------------------------------------------
     Share — WeChat built-in share (personalized)
     --------------------------------------------------------------- */

  onShareAppMessage() {
    const reading = this.data.reading;
    if (!reading) return { title: '星光塔罗解读' };

    // Analytics: track share event
    analytics.trackEvent('share', { type: 'reading', spread_type: reading.spread_type });

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
        } else {
          wx.showToast({
            title: '分享成功 ✦',
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
