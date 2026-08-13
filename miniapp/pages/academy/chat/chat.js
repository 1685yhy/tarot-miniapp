// pages/academy/chat/chat.js —— 陪学小星 · 半屏对话页（SDD P2 阶段3 · T6-6）
//
// 页面 = 底部半屏卡片（顶部遮罩点击返回，视觉与设计 1.2 半屏对话一致）：
//   1. 头部：小星头像（E3 文字星灵头像 ✦）+ 名字 + 关闭
//   2. 气泡对话：小星（星光色气泡 + 头像）/ 用户（奶油气泡）；回答 ≤200 字
//   3. 降级文案（degraded）原样展示，气泡轻微弱化以示区别
//   4. 免费配额提示「今日还可问 N 次」；402 → 系统行 + 输入禁用
//   5. 底部常驻「仅供娱乐 · 星光映照」
//
// 接口：POST /academy/chat {card_id, message} → {reply, remaining, degraded}
//       remaining 为 null（会员）不展示配额；402 detail 以系统行展示
// 数据降级：网络/服务异常 → 系统行提示 + 恢复输入（可再次发送）；不发空消息。
//
// 入口：学习卡页「问小星」→ /pages/academy/chat/chat?card_id=N（T6-5 已链接）

const { request, getFriendlyError } = require('../../../utils/api');
const analytics = require('../../../utils/analytics');

// 开场问候（E3 语气，进页即有内容不空屏）
const GREETING = '我是小星 ✦ 你手里这张牌的任何疑问，都可以问我——牌意、典故，还是生活里的联想。';

// 402 兜底文案（后端 detail 优先，此处仅防御空值）
const QUOTA_EXHAUSTED_FALLBACK = '今天的小星课堂结束啦，明天再来 ✦';

Page({
  data: {
    cardId: null,
    messages: [],      // {role: 'user'|'assistant'|'system', content, degraded?}
    inputText: '',
    canSend: false,
    sending: false,
    aiThinking: false,

    // 配额提示（由 remaining 归一化：null/未知 → 不展示）
    showQuota: false,
    quotaText: '',
    quotaExhausted: false, // 配额用尽 → 输入禁用

    scrollInto: '',    // scroll-view 滚动锚点（msg-<index>）
  },

  _destroyed: false,
  _msgSeq: 0, // 消息自增 id（wx:key 用；列表只追加，id 单调稳定）

  onLoad(options) {
    this._destroyed = false;
    const cardId = Number(options.card_id);
    if (!cardId) {
      this.setData({
        messages: [{ role: 'system', content: '缺少卡牌编号，请从学习卡页进入 ✦', id: this._msgSeq++ }],
      });
      return;
    }
    this.setData({
      cardId,
      messages: [{ role: 'assistant', content: GREETING, id: this._msgSeq++ }],
    });
    analytics.trackEvent('academy_chat_open', { card_id: cardId });
  },

  onUnload() {
    // 页面销毁守卫：异步回调不再 setData
    this._destroyed = true;
  },

  /** 关闭：遮罩/✕ → 返回上一页 */
  onClose() {
    wx.navigateBack({ fail: () => wx.reLaunch({ url: '/pages/academy/academy' }) });
  },

  onInput(e) {
    const val = e.detail.value;
    this.setData({ inputText: val, canSend: val.trim().length > 0 });
  },

  /** 发送：空输入守卫 + 发送中/配额用尽守卫 */
  async onSend() {
    const text = this.data.inputText.trim();
    if (!text || this.data.sending || this.data.quotaExhausted) return;
    if (!this.data.cardId) return;

    const messages = [...this.data.messages, { role: 'user', content: text, id: this._msgSeq++ }];
    this.setData({ messages, inputText: '', canSend: false, sending: true, aiThinking: true });
    this._scrollBottom();

    analytics.trackEvent('academy_chat_send', { card_id: this.data.cardId });

    try {
      const res = await request('/academy/chat', {
        method: 'POST',
        data: { card_id: this.data.cardId, message: text },
      });
      if (this._destroyed) return;
      // 回答 ≤200 字为后端契约（ACADEMY_CHAT_MAX_LEN），前端原样展示
      messages.push({
        role: 'assistant',
        content: (res && res.reply) || '',
        degraded: !!(res && res.degraded),
        id: this._msgSeq++,
      });
      this.setData({ messages, sending: false, aiThinking: false });
      this._applyRemaining(res ? res.remaining : -1);
      this._scrollBottom();
      try { wx.vibrateShort({ type: 'light' }); } catch (_e) {}
    } catch (err) {
      if (this._destroyed) return;
      if (err.statusCode === 402) {
        // 配额用尽：后端 detail 以系统行展示（原样），输入禁用
        this.setData({
          messages: [...this.data.messages, {
            role: 'system',
            content: err.message || QUOTA_EXHAUSTED_FALLBACK,
            id: this._msgSeq++,
          }],
          sending: false,
          aiThinking: false,
          quotaExhausted: true,
          showQuota: true,
          quotaText: '今日陪学次数已用完，明天再来 ✦',
        });
        this._scrollBottom();
        return;
      }
      // 其他异常：系统行提示 + 恢复输入内容（用户可直接再发）
      this.setData({
        messages: [...this.data.messages, {
          role: 'system',
          content: getFriendlyError(err),
          id: this._msgSeq++,
        }],
        sending: false,
        aiThinking: false,
        inputText: text,
        canSend: true,
      });
      this._scrollBottom();
    }
  },

  /** remaining（int|null）→ 配额提示；null/未知 → 不展示 */
  _applyRemaining(remaining) {
    if (typeof remaining !== 'number' || remaining < 0) {
      this.setData({ showQuota: false, quotaText: '' });
      return;
    }
    if (remaining > 0) {
      this.setData({
        showQuota: true,
        quotaText: `今日还可问 ${remaining} 次`,
        quotaExhausted: false,
      });
    } else {
      // 最后一条已答完：提示 + 禁用输入（与 402 同一收口）
      this.setData({
        showQuota: true,
        quotaText: '今日陪学次数已用完，明天再来 ✦',
        quotaExhausted: true,
      });
    }
  },

  /** 滚动到底部（scroll-into-view 锚点 = 最新一条消息） */
  _scrollBottom() {
    const last = this.data.aiThinking ? 'msg-typing' : `msg-${this.data.messages.length - 1}`;
    this.setData({ scrollInto: last });
  },
});
