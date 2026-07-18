// pages/chat/chat.js
const { request, getFriendlyError } = require('../../utils/api');

Page({
  data: {
    readingId: '',
    messages: [],
    inputText: '',
    canSend: false,
    sending: false,
    aiThinking: false,
    remainingFree: 0,
    pageLoading: false,
    pageError: null,
    readingContext: null, // { question, spread_type }
    sendFailed: false,     // true when last send failed, shows retry bar
    _pendingRetryText: '', // failed message text to retry
  },

  async onLoad(options) {
    this._destroyed = false;
    const readingId = options.readingId || '';
    this.setData({ readingId, pageLoading: true });

    // Load reading context and chat history
    try {
      const reading = await request(`/readings/${readingId}`);
      this.setData({
        readingContext: {
          question: reading.question || '未指定问题',
          spreadType: reading.spread_type,
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
  },

  onUnload() {
    this._destroyed = true;
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

  async onSend() {
    const text = this.data.inputText.trim();
    if (!text || this.data.sending) return;

    const messages = [...this.data.messages, { role: 'user', content: text }];
    this.setData({ messages, inputText: '', canSend: false, sending: true, aiThinking: true });

    try {
      const result = await request(`/readings/${this.data.readingId}/chat`, {
        method: 'POST',
        data: { message: text },
      });
      if (this._destroyed) return;
      messages.push({ role: 'assistant', content: result.reply });
      this.setData({
        messages,
        sending: false,
        aiThinking: false,
        remainingFree: result.remaining_free,
      });
      this.scrollToBottom();
    } catch (err) {
      if (this._destroyed) return;
      // 移除失败的消息，保留输入内容供重试
      const messagesWithoutFailed = this.data.messages.slice(0, -1);
      this.setData({
        messages: messagesWithoutFailed,
        sending: false,
        aiThinking: false,
        sendFailed: true,
        _pendingRetryText: text,
        inputText: text,
        canSend: true,
      });
      wx.showToast({ title: '发送失败，请重试', icon: 'none' });
    }
  },

  /** 重试上次发送失败的消息 */
  onRetrySend() {
    const text = this.data._pendingRetryText;
    if (!text) {
      this.setData({ sendFailed: false, _pendingRetryText: '' });
      return;
    }
    this.setData({ sendFailed: false, _pendingRetryText: '', inputText: text, canSend: true });
    this.onSend();
  },

  scrollToBottom() {
    wx.createSelectorQuery().select('#chat-bottom').boundingClientRect(() => {
      wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    }).exec();
  },
});
