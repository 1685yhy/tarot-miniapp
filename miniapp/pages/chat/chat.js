// pages/chat/chat.js
const { request, getFriendlyError, BASE_URL } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const analytics = require('../../utils/analytics');

/** Derive WebSocket base URL from the REST API base URL. */
const WS_BASE = BASE_URL.replace(/^http/, 'ws').replace(/\/api$/, '');

/** Get free daily chat limit from member status (or fallback) */
function _getFreeChatsLimit() {
  const app = getApp();
  const quota = app.globalData.memberStatus?.free_quota;
  return quota?.daily_chats || 3;
}

// Spread type key → Chinese display name
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
  daily: '每日之牌',
  career_path: '事业路线',
  weekly_outlook: '周运势',
  love_reading: '爱情占卜',
  fortune_telling: '财运占卜',
};

Page({
  data: {
    readingId: '',
    messages: [],
    inputText: '',
    canSend: false,
    sending: false,
    aiThinking: false,
    remainingFree: 0,
    chatFreeTotal: _getFreeChatsLimit(),
    pageLoading: false,
    pageError: null,
    readingContext: null, // { question, spread_type }
    sendFailed: false,     // true when last send failed, shows retry bar
    _pendingRetryText: '', // failed message text to retry

    // WebSocket streaming
    isStreaming: false,    // true while tokens are being streamed (shows cursor)

    // Membership prompt when quota exhausted
    showMembershipPrompt: false,
    membershipPromptText: '',
  },

  /** @type {WebSocketTask|null} */
  _wsTask: null,
  /** @type {number|null} */
  _wsTimeout: null,
  /** Accumulated streaming text for the current message */
  _streamBuffer: '',
  /** True once the first token has been received */
  _streamStarted: false,

  async onLoad(options) {
    this._destroyed = false;
    const readingId = options.readingId || '';
    this.setData({ readingId });

    // No readingId provided — show friendly empty state
    if (!readingId) {
      this.setData({
        pageLoading: false,
        readingContext: { question: '请在解读结果页点击「AI解读」进入', spreadType: '' },
      });
      return;
    }

    this.setData({ pageLoading: true });

    // Load reading context and chat history
    try {
      const reading = await request(`/readings/${readingId}`);
      const spreadTypeName = SPREAD_TYPE_NAMES[reading.spread_type] || reading.spread_type || '';
      this.setData({
        readingContext: {
          question: reading.question || '未指定问题',
          spreadType: reading.spread_type,
          spreadTypeName,
        },
        messages: (reading.chat_messages || []).map(m => ({
          role: m.role,
          content: m.content,
        })),
        pageLoading: false,
      });
      // Scroll to bottom if there are existing messages
      if (reading.chat_messages && reading.chat_messages.length > 0) {
        this._scrollTimer = setTimeout(() => this.scrollToBottom(), 200);
      }
    } catch (err) {
      if (this._destroyed) return;
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }

    // Refresh member status so free chat limit shows real data
    try {
      const app = getApp();
      if (!app.globalData.memberStatus) {
        const user = await checkLogin({ refresh: true });
        app.globalData.memberStatus = { free_quota: user.free_quota };
        this.setData({ chatFreeTotal: _getFreeChatsLimit() });
      }
    } catch (_e) { /* silent degrade */ }

    // Analytics: funnel — chat started
    analytics.funnel('chat_started', { readingId: readingId || '' });
  },

  onUnload() {
    this._destroyed = true;
    this._cleanupWebSocket();
    if (this._scrollTimer) {
      clearTimeout(this._scrollTimer);
      this._scrollTimer = null;
    }
  },

  onHide() {
    if (this._scrollTimer) {
      clearTimeout(this._scrollTimer);
      this._scrollTimer = null;
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    if (this.data.readingId) {
      this.onLoad({ readingId: this.data.readingId });
    }
  },

  onInput(e) {
    const val = e.detail.value;
    this.setData({ inputText: val, canSend: val.trim().length > 0 });
  },

  /** Clean up any active WebSocket connection */
  _cleanupWebSocket() {
    if (this._wsTimeout) {
      clearTimeout(this._wsTimeout);
      this._wsTimeout = null;
    }
    if (this._wsTask) {
      try { this._wsTask.close(); } catch (_e) { /* ignore */ }
      this._wsTask = null;
    }
    this._streamBuffer = '';
    this._streamStarted = false;
  },

  /**
   * Try WebSocket streaming; fall back to REST if connection fails within 3 s.
   */
  async onSend() {
    const text = this.data.inputText.trim();
    if (!text || this.data.sending) return;

    // Analytics: track each sent message
    analytics.trackEvent('chat_message', { readingId: this.data.readingId });

    const messages = [...this.data.messages, { role: 'user', content: text }];
    this.setData({
      messages, inputText: '', canSend: false, sending: true,
      aiThinking: true, sendFailed: false, _pendingRetryText: '',
      isStreaming: false, showMembershipPrompt: false,
    });
    this.scrollToBottom();

    // --- Attempt WebSocket ---
    this._streamBuffer = '';
    this._streamStarted = false;

    const token = wx.getStorageSync('token');
    const wsUrl = `${WS_BASE}/ws/chat/${this.data.readingId}?token=${encodeURIComponent(token)}`;

    // 3-second fallback timer: if WS doesn't open in time, use REST
    this._wsTimeout = setTimeout(() => {
      if (!this._streamStarted) {
        // WS hasn't started streaming — fall back to REST
        this._cleanupWebSocket();
        this._doRestSend(text, messages);
      }
    }, 3000);

    try {
      // Create the WebSocket task
      const task = wx.connectSocket({ url: wsUrl, fail: () => {} });
      this._wsTask = task;

      // Bind event listeners
      task.onOpen(() => {
        // Clear the fallback timer — WS connected
        if (this._wsTimeout) {
          clearTimeout(this._wsTimeout);
          this._wsTimeout = null;
        }
        // Send the user's message
        task.send({ data: text });
      });

      task.onMessage((res) => {
        const data = res.data;

        if (data === '[DONE]') {
          // Streaming complete
          this._streamStarted = true;
          this.setData({
            isStreaming: false,
            aiThinking: false,
            sending: false,
          });
          // Mark last message as complete
          const msgs = [...this.data.messages];
          const last = msgs[msgs.length - 1];
          if (last && last.role === 'assistant') {
            last.streaming = false;
            this.setData({ messages: msgs });
          }
          this.scrollToBottom();
          try { wx.vibrateShort({ type: 'light' }); } catch(_e) {}
          // Clean up
          this._cleanupWebSocket();
          return;
        }

        if (data.startsWith('[ERROR]')) {
          this._streamStarted = true;
          this._cleanupWebSocket();

          const errorMsg = data.replace('[ERROR] ', '');
          // 402 = quota exhausted
          if (errorMsg.startsWith('402')) {
            this.setData({
              sending: false, aiThinking: false, isStreaming: false,
              showMembershipPrompt: true,
              membershipPromptText: '今日追问已达上限',
            });
            return;
          }

          // Other errors: show in a failed message
          const msgs = [...this.data.messages];
          msgs.push({ role: 'assistant', content: `⚠️ ${errorMsg}`, failed: false });
          this.setData({
            messages: msgs, sending: false, aiThinking: false, isStreaming: false,
            sendFailed: true, _pendingRetryText: text,
            inputText: text, canSend: true,
          });
          this.scrollToBottom();
          return;
        }

        // --- Token received ---
        this._streamBuffer += data;

        if (!this._streamStarted) {
          // First token — create the assistant message bubble
          this._streamStarted = true;
          const msgs = [...this.data.messages];
          msgs.push({ role: 'assistant', content: this._streamBuffer, streaming: true });
          this.setData({
            messages: msgs,
            aiThinking: false,
            isStreaming: true,
          });
        } else {
          // Update existing streaming message
          const msgs = [...this.data.messages];
          const last = msgs[msgs.length - 1];
          if (last && last.role === 'assistant') {
            last.content = this._streamBuffer;
            this.setData({ messages: msgs });
          }
        }
        this.scrollToBottom();
      });

      task.onClose(() => {
        if (!this._streamStarted) {
          // WS closed before any tokens — treat as connection failure, fall back
          this._cleanupWebSocket();
          this._doRestSend(text, messages);
          return;
        }
        // Clean up if not already done
        this._cleanupWebSocket();
      });

      task.onError((err) => {
        if (!this._streamStarted) {
          this._cleanupWebSocket();
          this._doRestSend(text, messages);
        }
      });

    } catch (err) {
      // connectSocket threw synchronously — fall back to REST
      if (this._wsTimeout) {
        clearTimeout(this._wsTimeout);
        this._wsTimeout = null;
      }
      this._wsTask = null;
      this._doRestSend(text, messages);
    }
  },

  /**
   * Fallback: send via REST API (existing logic, untouched).
   */
  async _doRestSend(text, messages) {
    if (this._destroyed) return;
    this.setData({ sending: true, aiThinking: true, isStreaming: false });

    try {
      const result = await request(`/readings/${this.data.readingId}/chat`, {
        method: 'POST',
        data: { message: text },
      });
      if (this._destroyed) return;
      messages.push({ role: 'assistant', content: result.reply, streaming: false });
      this.setData({
        messages,
        sending: false,
        aiThinking: false,
        isStreaming: false,
        remainingFree: result.remaining_free,
      });
      try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
      this.scrollToBottom();
    } catch (err) {
      if (this._destroyed) return;
      // 402: quota exhausted — show membership prompt instead of retry
      if (err.statusCode === 402) {
        this.setData({
          sending: false,
          aiThinking: false,
          isStreaming: false,
          showMembershipPrompt: true,
          membershipPromptText: '今日追问已达上限',
        });
        return;
      }
      // 保留用户消息，标记发送失败，允许点击重试
      const lastMsg = messages[messages.length - 1];
      lastMsg.failed = true;
      this.setData({
        messages,
        sending: false,
        aiThinking: false,
        isStreaming: false,
        sendFailed: true,
        _pendingRetryText: text,
        inputText: text,
        canSend: true,
      });
      wx.showToast({ title: '发送失败，点击消息重试', icon: 'none' });
    }
  },

  /** 重试发送失败的消息 (unchanged — REST-only retry) */
  async onRetrySend(e) {
    if (this.data.sending) return;
    if (this.data.isStreaming) return;
    // Only proceed if this message is actually failed
    const isFailed = e && e.currentTarget && e.currentTarget.dataset.failed;
    if (e && !isFailed) return;
    const text = this.data._pendingRetryText;
    if (!text) {
      this.setData({ sendFailed: false, _pendingRetryText: '' });
      return;
    }
    // 清除失败消息，重新发送
    const messages = this.data.messages.filter(m => !m.failed);
    this.setData({ messages, sendFailed: false, _pendingRetryText: '', aiThinking: true, sending: true });

    // Retry uses REST fallback directly (WebSocket may still be unstable)
    await this._doRestSend(text, messages);
  },

  scrollToBottom() {
    wx.createSelectorQuery().select('#chat-bottom').boundingClientRect(() => {
      wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    }).exec();
  },

  /** Navigate to membership page */
  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
