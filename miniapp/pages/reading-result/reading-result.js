// pages/reading-result/reading-result.js
const { request, getFriendlyError } = require('../../utils/api');
const { cardEnter } = require('../../utils/animate');
const { computeImagePath, pngFallbackPath } = require('../../utils/cards');
const { playCardRevealSound } = require('../../utils/sound');
const { fetchTodayEnergy } = require('../../utils/energy');
const analytics = require('../../utils/analytics');
const { checkLogin } = require('../../utils/auth');
const { startPay, isComingSoonError, showComingSoonModal } = require('../../utils/pay');
const { maybePromptSubscribe } = require('../../utils/subscribe');

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

    // Share poster — 星光名片样式（Task 7：星阶徽章 + 星光数 + 小程序码）
    showSharePoster: false,
    shareCardImage: '',
    shareCardName: '',
    shareKeyInsight: '',
    userNickname: '',
    starTierName: '',
    stardustTotal: 0,

    // Friend invite poster — "送好友一张牌" (both get +1 free deep reading)
    showInvitePoster: false,
    inviteCode: '',

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

    // 解读正文分区渲染（E3：标题/段落层级恢复，纯视觉不改内容）
    letterSegments: [],

    // Task 4: Reflection question
    reflectionQuestion: '',

    // 开发 03：今日能量关联（解读主题 ↔ 今日能量同频一行）
    energyLink: '',

    // Task 2.7: A/B test — first-paid deep reading price
    priceTestBucket: '9.9',   // '9.9' | '19.9' — set in onLoad from openid hash
    purchasingDeep: false,    // guard double-tap on the paywall CTA
  },

  onLoad(options) {
    // ── Task 2.7: A/B test — first-paid deep reading price (¥9.9 vs ¥19.9) ──
    // Deterministic 50/50 split by openid char-code hash: each user always
    // sees the same price bucket, so conversion can be compared per bucket.
    const user = wx.getStorageSync('user') || {};
    const bucket = (user.openid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 2;
    const priceTestBucket = bucket === 0 ? '9.9' : '19.9';
    this.setData({ priceTestBucket });
    // Persist so purchase events fired from other pages can attach the bucket
    wx.setStorageSync('price_test_bucket', priceTestBucket);

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

    // Analytics: completed reading displayed
    analytics.trackReadingComplete(spread);

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
      // 与 _load() 一致：新生成的解读也要为 drawn_cards 计算 imagePath，
      // 否则牌面图缺失（tarot-card 只能退回 CSS 占位/缩略图）
      this._mapCardImages(result);
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
    // Loading progression: rotate stage copy every ~6s so the 20-40s AI
    // wait feels alive instead of frozen ("正在抽牌 → 星光凝思 → 解牌成文").
    this._immersiveStarted = true;
    this.setData({ loadingStage: 1 });
    this._stageTimer1 = setTimeout(() => {
      if (this._destroyed) return;
      this._tryShowResult();
    }, IMMERSIVE_MAX_MS);
    // Rotate loading-stage copy (does not affect result timing)
    this._stageRotateTimer = setInterval(() => {
      if (this._destroyed) { this._clearStageRotate(); return; }
      const next = (this.data.loadingStage % 3) + 1;
      this.setData({ loadingStage: next });
    }, 6000);
  },

  _clearStageRotate() {
    if (this._stageRotateTimer) {
      clearInterval(this._stageRotateTimer);
      this._stageRotateTimer = null;
    }
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
          .replace(/\[ACTION\](.*?)\[\/ACTION\]/g, '')  // 行动建议已由 action-cards 组件呈现，正文不再重复
          .replace(/\n{3,}/g, '\n\n')
          .trim();
      }

      // Compute image paths for each drawn card
      this._mapCardImages(reading);

      this._cachedReading = reading;
      if (!this._destroyed) { this._tryShowResult(); }
    } catch (err) {
      // Always cache error — even if page was hidden (onShow will pick it up)
      this._cachedError = getFriendlyError(err);
      if (!this._destroyed) { this._tryShowResult(); }
    }
  },

  /** 为 reading.drawn_cards 计算牌面图路径（_load/_createReading/_requestDeepReading 共用） */
  _mapCardImages(reading) {
    if (reading && reading.drawn_cards) {
      reading.drawn_cards = reading.drawn_cards.map(card => ({
        ...card,
        imagePath: computeImagePath(card, card.imageBase),
      }));
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
     解读正文分区（E3 排版 · 纯视觉）
     letterSegments: 把 AI 正文按空行拆段，识别小标题（**...** / 【一、…】
     / 固定标签行）→ {type:'heading'|'para', text}；供 WXML 分区渲染。
     --------------------------------------------------------------- */

  _buildLetterSegments(text) {
    if (!text || typeof text !== 'string') return [];
    const blocks = text.split(/\n{2,}/).map(b => b.trim()).filter(Boolean);
    const segs = [];
    const LABEL_HEADS = ['牌阵总览', '综合解读', '建议与指引', '逐牌解读', '牌阵解读'];
    for (const block of blocks) {
      const trimmed = block.trim();
      // 段首行可能是小标题：**牌阵总览** / 【一、…】 / 固定标签行
      const lines = trimmed.split('\n');
      const firstLine = (lines[0] || '').trim();
      const boldMatch = firstLine.match(/^\*\*(.+?)\*\*$/);
      const deepHead = firstLine.match(/^【[一二三四五六]、?[^】]{2,14}】$/);
      const labelHead = LABEL_HEADS.includes(firstLine.replace(/[*\s]/g, ''));
      let body = trimmed;
      let headText = '';
      if (boldMatch) {
        headText = boldMatch[1];
        body = lines.slice(1).join('\n');
      } else if (deepHead) {
        headText = deepHead[0].replace(/[【】]/g, '');
        body = lines.slice(1).join('\n');
      } else if (labelHead) {
        headText = firstLine;
        body = lines.slice(1).join('\n');
      }
      const cleanBody = body
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\[ACTION\](.*?)\[\/ACTION\]/g, '')
        .trim();
      if (headText) segs.push({ type: 'heading', text: headText });
      if (cleanBody) segs.push({ type: 'para', text: cleanBody });
    }
    return segs;
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

      const letterSegments = this._buildLetterSegments(reading.interpretation);
      const tldr = this._extractTLDR(reading.interpretation);

      // Extract teaching data from drawn cards
      const teachingCards = [];
      if (reading.drawn_cards) {
        for (const card of reading.drawn_cards) {
          if (card.teaching && (card.teaching.symbols?.length > 0 || card.teaching.life_connection)) {
            teachingCards.push({
              card_id: card.card_id,
              card_name: card.card_name,
              // 符号单字符（如「☾」「·」）→ 徽章式渲染，避免被看成“一个点”
              symbols: (card.teaching.symbols || []).map((sym) => ({
                symbol: sym.symbol,
                meaning: sym.meaning,
                isSingle: typeof sym.symbol === 'string' && sym.symbol.trim().length <= 2,
              })),
              life_connection: card.teaching.life_connection || '',
            });
          }
        }
      }
      const hasTeachingData = teachingCards.length > 0;

      const reflectionQuestion = reading.reflection_question || '今天的解读对你意味着什么？';
      this.setData({
        reading, personaDisplay, tldr, teachingCards, hasTeachingData,
        spreadTypeName, pageLoading: false, reflectionQuestion,
        letterSegments,
      });
      // Trigger staggered card entrance animation after render
      this._animateCardReveal();
      // Play reveal sound when reading result appears
      try { playCardRevealSound(); } catch(e) {}
      // 开发 03：今日能量关联（异步 · 失败静默隐藏）
      this._loadEnergyLink(reading);

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

      // ── 星光晨讯订阅引导（Task 6）：抽牌结果页进入时弹一次 ──
      // 幂等：模板未配置/用户已拒绝/同会话已弹过时内部自动跳过。
      // 延迟 1.2s 让解读结果先展示，避免系统弹窗盖住牌面。
      // 赋值前先清掉旧定时器（_tryShowResult 可能被多次触发），防止叠加弹窗
      if (this._subscribeTimer) { clearTimeout(this._subscribeTimer); }
      this._subscribeTimer = setTimeout(() => {
        this._subscribeTimer = null;
        if (this._destroyed) return;
        maybePromptSubscribe();
      }, 1200);
    } else if (this._cachedError) {
      this.setData({ pageLoading: false, pageError: this._cachedError });
    }
  },

  /* ---------------------------------------------------------------
     开发 03 · 今日能量关联
     解读主题 ↔ 今日能量同频：love→爱情 / career→事业 / finance→事业(财运) / general→当日最高
     例：「今日爱情能量 81——牌意与能量同频」（接口失败静默隐藏）
     --------------------------------------------------------------- */
  async _loadEnergyLink(reading) {
    if (!reading) return;
    try {
      const data = await fetchTodayEnergy();
      const byKey = {};
      (data.items || []).forEach((i) => { byKey[i.key] = i.score; });
      let key = '';
      const theme = reading.theme || '';
      if (theme === 'love') key = 'love';
      else if (theme === 'career' || theme === 'finance') key = 'career';
      else if (data.items && data.items.length) {
        key = data.items.reduce((a, b) => (b.score > a.score ? b : a), data.items[0]).key;
      }
      const dimName = { love: '爱情', career: '事业', social: '人际', health: '健康' }[key] || '';
      const score = byKey[key];
      if (!dimName || score === undefined) return;
      this.setData({ energyLink: `今日${dimName}能量 ${score}——牌意与能量同频` });
    } catch (_err) {
      // 静默隐藏，不打扰解读结果
    }
  },

  /* ---------------------------------------------------------------
     Timer Cleanup
     --------------------------------------------------------------- */

  _clearStageTimers() {
    if (this._stageTimer1) { clearTimeout(this._stageTimer1); this._stageTimer1 = null; }
    if (this._quickMinTimer) { clearTimeout(this._quickMinTimer); this._quickMinTimer = null; }
    this._clearStageRotate();
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
    if (this._subscribeTimer) { clearTimeout(this._subscribeTimer); this._subscribeTimer = null; }
  },

  onHide() {
    this._destroyed = true;
    this._clearStageTimers();
    if (this._onboardingTimer) { clearTimeout(this._onboardingTimer); this._onboardingTimer = null; }
    if (this._navBackTimer) { clearTimeout(this._navBackTimer); this._navBackTimer = null; }
    if (this._subscribeTimer) { clearTimeout(this._subscribeTimer); this._subscribeTimer = null; }
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

  /* ---------------------------------------------------------------
     Deep Reading Paywall — A/B test price (Task 2.7)
     Buys the "single deep reading" product (single_reading, grants
     +1 paid reading credit). The A/B bucket varies the CTA price
     shown and is attached to every purchase analytics event.
     Note: the actual charged amount still comes from the backend
     product catalog — this test measures which CTA price converts.
     --------------------------------------------------------------- */
  async onUnlockDeepReading() {
    if (this.data.purchasingDeep) return;
    const bucket = this.data.priceTestBucket || '9.9';

    // Analytics: paywall CTA clicked — funnel step (Task 2.4)
    analytics.trackPaywallClick('reading_complete');

    try {
      await checkLogin();
    } catch (err) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    const product = { id: 'single_reading', price: Number(bucket) };

    // Analytics: CTA click + purchase intent — attach A/B bucket
    analytics.trackEvent('deep_reading_unlock_cta', { priceTestBucket: bucket });
    analytics.trackPurchaseStart(product, { priceTestBucket: bucket });

    this.setData({ purchasingDeep: true });
    wx.showLoading({ title: '创建订单...', mask: true });
    try {
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: product.id },
      });
      wx.hideLoading();

      // 统一支付入口：xpay 虚拟支付 / 旧 JSAPI 双通道（P0-1）
      startPay(order, {
        product,
        success: () => {
          // Analytics: purchase completed — attach A/B bucket
          analytics.trackPurchaseComplete(product, Number(bucket), { priceTestBucket: bucket });
          this.setData({ purchasingDeep: false });
          wx.showToast({ title: '解锁成功 ✦', icon: 'success' });
          // P0-2 fix: the purchase grants +1 paid reading credit — re-run the
          // reading with depth=deep so the user actually receives the deep
          // interpretation they paid for (backend consumes the credit).
          this._requestDeepReading();
        },
        fail: (err) => {
          this.setData({ purchasingDeep: false });
          if (err.reason === 'user_cancel') {
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else if (err.reason === 'coming_soon') {
            // 商品即将上线 → 降级弹窗
            showComingSoonModal();
          } else {
            wx.showToast({ title: err.message || '支付失败，请重试', icon: 'none' });
          }
        },
      });
    } catch (err) {
      this.setData({ purchasingDeep: false });
      wx.hideLoading();
      if (isComingSoonError(err)) {
        // 400「该商品即将上线」→ 降级弹窗
        showComingSoonModal();
        return;
      }
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },

  /** P0-2: 深度解读购买成功后，重发一次 depth=deep 的解读请求。
   *  以当前展示的解读为模板（问题/主题/人设沿用），生成深度版替换之。
   *  微信支付回调可能比 requestPayment 成功晚 1-2 秒到账，因此在余额
   *  尚未入账（402）时做短暂重试。
   */
  async _requestDeepReading(retries = 2) {
    const prev = this.data.reading || this._cachedReading || {};
    const spread = prev.spread_type || this._pendingSpread || 'three_card';
    const data = {
      spread_type: spread,
      question: prev.question || null,
      theme: prev.theme || 'general',
      persona: prev.persona || null,
      zodiac: '',
      depth: 'deep',
    };
    wx.showLoading({ title: '深度解读生成中...', mask: true });
    try {
      const result = await request(`/readings/spread/${spread}`, {
        method: 'POST',
        data: data,
      });
      wx.hideLoading();
      if (!result || !result.interpretation) {
        wx.showToast({ title: '深度解读生成失败，请重试', icon: 'none' });
        return;
      }
      // 用深度版替换当前解读（同样补齐牌面图路径）
      this._mapCardImages(result);
      this._cachedReading = result;
      this._cachedError = null;
      this._isQuickMode = false;
      this._immersiveStarted = true;
      this._tryShowResult();
      wx.showToast({ title: '深度解读已生成 ✦', icon: 'success' });
    } catch (err) {
      // 支付回调尚未到账（余额为 0 导致 402）— 短暂等待后重试
      if (err.statusCode === 402 && retries > 0) {
        wx.hideLoading();
        setTimeout(() => this._requestDeepReading(retries - 1), 1500);
        return;
      }
      wx.hideLoading();
      wx.showToast({ title: getFriendlyError(err) || '深度解读生成失败', icon: 'none' });
    }
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
    analytics.trackShare('wechat_friend', 'reading');

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

  /** Build the poster data (first card + key insight + nickname). */
  _buildPosterData() {
    const reading = this.data.reading;
    if (!reading || !reading.drawn_cards || reading.drawn_cards.length === 0) {
      return null;
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

    return { cardImage, cardName, keyInsight, nickname };
  },

  /** 星光名片海报（Task 7）：附带星阶徽章 + 星光数 + 小程序码（scene=邀请码） */
  async onOpenSharePoster() {
    const poster = this._buildPosterData();
    if (!poster) {
      wx.showToast({ title: '暂无牌面可生成海报', icon: 'none' });
      return;
    }

    // 拉取星阶/星光数（失败静默降级为 微光/0，海报仍可生成）
    let starTierName = '';
    let stardustTotal = 0;
    try {
      const t = await request('/tasks/status');
      starTierName = (t && t.star_tier_name) || '';
      stardustTotal = (t && t.stardust_total) || 0;
    } catch (_err) {
      // 静默降级
    }

    this.setData({
      showSharePoster: true,
      shareCardImage: poster.cardImage,
      shareCardName: poster.cardName,
      shareKeyInsight: poster.keyInsight,
      userNickname: poster.nickname,
      starTierName,
      stardustTotal,
    });
  },

  onCloseSharePoster() {
    this.setData({ showSharePoster: false });
  },

  /* ---------------------------------------------------------------
     Friend Invite — "送好友一张牌 ✦"
     Opens the invite poster whose QR code carries the user's invite
     code. When a friend scans it, both sides get +1 free deep reading.
     (NOT 诱导分享 — no points, no cash, no "share to moments for reward".)
     --------------------------------------------------------------- */

  async onSendCardToFriend() {
    const poster = this._buildPosterData();
    if (!poster) {
      wx.showToast({ title: '暂无牌面可送', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '生成邀请卡...', mask: true });
    try {
      const res = await request('/share/invite-code');
      wx.hideLoading();
      const inviteCode = (res && res.invite_code) || '';
      if (!inviteCode) {
        wx.showToast({ title: '邀请码获取失败', icon: 'none' });
        return;
      }

      this.setData({
        showInvitePoster: true,
        inviteCode: inviteCode,
        shareCardImage: poster.cardImage,
        shareCardName: poster.cardName,
        shareKeyInsight: poster.keyInsight,
        userNickname: poster.nickname,
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: getFriendlyError(err), icon: 'none' });
    }
  },

  onCloseInvitePoster() {
    this.setData({ showInvitePoster: false });
  },

  onSharePosterToFriend(e) {
    // Forward the poster image path to the native share API
    // WeChat doesn't support custom image via onShareAppMessage directly,
    // so we use wx.shareAppMessage (available in newer base libs)
    // or fall back to letting the user save + share manually
    const imagePath = e.detail && e.detail.imagePath;
    if (imagePath) {
      // Analytics: poster share — distinguish invite poster from reading poster
      const shareType = this.data.showInvitePoster ? 'invite_poster' : 'reading_poster';
      analytics.trackShare('wechat_friend', shareType);
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
      /* UX 修复: 痛点#5 — 收藏为本地存储，toast 明确说明存放位置 */
      wx.showToast({ title: '已收藏（保存在本机）', icon: 'success' });
      return;
    }
    saved.push(reading.id);
    wx.setStorageSync('saved_readings', saved);
    this.setData({ isSaved: true });
    /* UX 修复: 痛点#5 — 收藏为本地存储，toast 明确说明存放位置 */
    wx.showToast({ title: '已收藏（保存在本机）', icon: 'success' });
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
