// pages/chat/chat.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

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

    // Membership prompt when quota exhausted
    showMembershipPrompt: false,
    membershipPromptText: '',
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
  },

  onUnload() {
    this._destroyed = true;
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
      try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
      this.scrollToBottom();
    } catch (err) {
      if (this._destroyed) return;
      // 402: quota exhausted — show membership prompt instead of retry
      if (err.statusCode === 402) {
        this.setData({
          sending: false,
          aiThinking: false,
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
        sendFailed: true,
        _pendingRetryText: text,
        inputText: text,
        canSend: true,
      });
      wx.showToast({ title: '发送失败，点击消息重试', icon: 'none' });
    }
  },

  /** 重试发送失败的消息 */
  async onRetrySend(e) {
    if (this.data.sending) return;
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

    try {
      const result = await request(`/readings/${this.data.readingId}/chat`, {
        method: 'POST',
        data: { message: text },
      });
      if (this._destroyed) return;
      messages.push({ role: 'assistant', content: result.reply });
      this.setData({ messages, sending: false, aiThinking: false, remainingFree: result.remaining_free, inputText: '', canSend: false });
      try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
      this.scrollToBottom();
    } catch (err) {
      if (this._destroyed) return;
      // 402: quota exhausted — show membership prompt
      if (err.statusCode === 402) {
        this.setData({
          sending: false,
          aiThinking: false,
          showMembershipPrompt: true,
          membershipPromptText: '今日追问已达上限',
        });
        return;
      }
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

  /** Navigate to membership page */
  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
