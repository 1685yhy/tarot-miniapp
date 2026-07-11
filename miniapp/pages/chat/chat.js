// pages/chat/chat.js
const { request } = require('../../utils/api');

Page({
  data: {
    readingId: '',
    messages: [],
    inputText: '',
    sending: false,
    remainingFree: 0,
  },

  onLoad(options) {
    this.setData({ readingId: options.readingId || '' });
  },

  onInput(e) {
    this.setData({ inputText: e.detail.value });
  },

  async onSend() {
    const text = this.data.inputText.trim();
    if (!text || this.data.sending) return;

    const messages = [...this.data.messages, { role: 'user', content: text }];
    this.setData({ messages, inputText: '', sending: true });

    try {
      const result = await request(`/readings/${this.data.readingId}/chat`, {
        method: 'POST',
        data: { message: text },
      });
      messages.push({ role: 'assistant', content: result.reply });
      this.setData({
        messages,
        sending: false,
        remainingFree: result.remaining_free,
      });
    } catch (err) {
      wx.showToast({ title: '发送失败', icon: 'none' });
      this.setData({ sending: false });
    }
  },

  scrollToBottom() {
    wx.createSelectorQuery().select('#chat-bottom').boundingClientRect(() => {
      wx.pageScrollTo({ scrollTop: 99999, duration: 200 });
    }).exec();
  },
});
