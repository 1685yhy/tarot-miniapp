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
    this.setData({ messages, inputText: '', canSend: false, sending: true, aiThinking: true,
      sendFailed: false, _pendingRetryText: '' });
    this.scrollToBottom();

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
      // 保留用户消息，标记发送失败，允许点击重试
      const lastMsg = messages[messages.length - 1];
      lastMsg.failed = true;
      this.setData({
        messages,
        sending: false,
        aiThinking: false,
        sendFailed: true,
        _pendingRetryText: text,
        inputText: text,
        canSend: true,
      });
      wx.showToast({ title: '发送失败，点击消息重试', icon: 'none' });
    }
  },

  /** 重试发送失败的消息 */
  async onRetrySend() {
    if (this.data.sending) return;
    const text = this.data._pendingRetryText;
    if (!text) {
      this.setData({ sendFailed: false, _pendingRetryText: '' });
      return;
    }
    // 清除失败消息，重新发送
    const messages = this.data.messages.filter(m => !m.failed);
    this.setData({ messages, sendFailed: false, _pendingRetryText: '', aiThinking: true, sending: true });

    try {
      const result = await request(`/readings/${this.data.readingId}/chat`, {
        method: 'POST',
        data: { message: text },
      });
      if (this._destroyed) return;
      messages.push({ role: 'assistant', content: result.reply });
      this.setData({ messages, sending: false, aiThinking: false, remainingFree: result.remaining_free, inputText: '', canSend: false });
      this.scrollToBottom();
    } catch (err) {
      if (this._destroyed) return;
      messages[messages.length - 1] = { role: 'user', content: text, failed: true };
      this.setData({ messages, sending: false, aiThinking: false, inputText: text, canSend: true,
        sendFailed: true, _pendingRetryText: text });
    }
  },

  scrollToBottom() {
    wx.createSelectorQuery().select('#chat-bottom').boundingClientRect(() => {
      wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    }).exec();
  },
});
