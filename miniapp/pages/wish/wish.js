// pages/wish/wish.js — 新月许愿（开发 04 · 星光记录为主角的「我的流」）
// 原型页 13：月相动画 + 愿望输入 → 成功态「已交给月光」+ 愿望归档
const { request, getFriendlyError } = require('../../utils/api');
const { maybePromptSubscribe } = require('../../utils/subscribe');

// 愿望分类 chips（只影响输入占位文案，分类随正文一起存）
const WISH_CATS = ['事业', '感情', '健康', '其他'];

// 状态展示元数据（与后端 wishes.status 对应）
const STATUS_META = {
  active: { label: '生长中', cls: 'wish-status--active' },
  grown: { label: '已生长', cls: 'wish-status--grown' },
  answered: { label: '待回应', cls: 'wish-status--answered' },
};

const MAX_ACTIVE = 10;

Page({
  data: {
    // 月相
    moon: null,          // {phase, emoji, label, next_new_moon, next_full_moon}
    moonLine: '',        // "娥眉月 · 新月 08.13 → 满月 08.28"
    moonLoading: true,

    // 输入态
    stage: 'input',      // input | done
    text: '',
    cats: WISH_CATS,
    cat: WISH_CATS[0],

    // 成功态
    doneWish: null,      // {content, created_at}
    blessing: '',        // AI 温柔回应

    // 归档列表
    wishes: [],
    activeCount: 0,
    listLoading: true,

    // 状态
    submitting: false,
    pageError: null,
  },

  onLoad() {
    this._load();
  },

  async _load() {
    this.setData({ moonLoading: true, listLoading: true });
    // 月相 + 愿望列表并行拉取，失败静默降级（不阻塞页面）
    const [moonRes, wishRes] = await Promise.allSettled([
      request('/moon/phase'),
      request('/wishes'),
    ]);

    let moon = null;
    let moonLine = '';
    if (moonRes.status === 'fulfilled' && moonRes.value) {
      moon = moonRes.value;
      const nm = (moon.next_new_moon || '').slice(5).replace('-', '.');
      const fm = (moon.next_full_moon || '').slice(5).replace('-', '.');
      moonLine = `${moon.emoji} ${moon.label} · 新月 ${nm} → 满月 ${fm}`;
    }

    const wishes = (wishRes.status === 'fulfilled' && wishRes.value && wishRes.value.wishes) || [];
    const activeCount = (wishRes.status === 'fulfilled' && wishRes.value) ? (wishRes.value.active_count || 0) : wishes.filter(w => w.status === 'active').length;

    this.setData({
      moon,
      moonLine,
      moonLoading: false,
      wishes: this._decorate(wishes),
      activeCount,
      listLoading: false,
      pageError: null,
    });
  },

  _decorate(wishes) {
    return (wishes || []).map(w => ({
      ...w,
      statusLabel: STATUS_META[w.status] ? STATUS_META[w.status].label : '生长中',
      statusCls: STATUS_META[w.status] ? STATUS_META[w.status].cls : 'wish-status--active',
      dateLabel: w.created_at ? w.created_at.slice(0, 10).replace(/-/g, '.') : '',
    }));
  },

  onRetry() {
    this._load();
  },

  onInput(e) {
    this.setData({ text: e.detail.value });
  },

  onPickCat(e) {
    this.setData({ cat: e.currentTarget.dataset.cat });
  },

  /** 许愿 → 交给月光 */
  async onSubmit() {
    if (this.data.submitting) return;
    const content = (this.data.text || '').trim();
    if (!content) {
      wx.showToast({ title: '先写下你的愿望吧', icon: 'none' });
      return;
    }
    if (content.length > 100) {
      wx.showToast({ title: '愿望最长 100 字', icon: 'none' });
      return;
    }
    if (this.data.activeCount >= MAX_ACTIVE) {
      wx.showToast({ title: `同时生长的愿望最多 ${MAX_ACTIVE} 条，满月时记得回望`, icon: 'none', duration: 2500 });
      return;
    }

    this.setData({ submitting: true });
    try {
      const wish = await request('/wishes', { method: 'POST', data: { content } });

      // AI 一句温柔回应（失败静默降级）
      let blessing = '';
      try {
        const b = await request(`/wishes/${wish.id}/bless`, { method: 'POST' });
        blessing = b.blessing || '';
      } catch (_err) { /* silent */ }

      this.setData({
        stage: 'done',
        text: '',
        doneWish: {
          ...wish,
          ticketLabel: wish.moon_phase === 'new_moon' ? '新月许愿' : '愿望',
        },
        blessing,
        submitting: false,
      });
      wx.vibrateShort && wx.vibrateShort({ type: 'light' });
      await this._refreshList();

      // 星光晨讯订阅引导（幂等：模板未配置/已拒绝/同会话已弹过时自动跳过）
      this._subscribeTimer = setTimeout(() => {
        this._subscribeTimer = null;
        maybePromptSubscribe();
      }, 600);
    } catch (err) {
      this.setData({ submitting: false });
      wx.showToast({ title: getFriendlyError(err) || '许愿失败，请稍后再试', icon: 'none', duration: 2500 });
    }
  },

  /** 再写一个 */
  onWriteAnother() {
    this.setData({ stage: 'input', doneWish: null, blessing: '' });
  },

  /** 查看我的满月复盘 */
  onGoReview() {
    wx.navigateTo({ url: '/pages/review/review' });
  },

  /** 愿望卡片 → 满月复盘页（从归档进入） */
  onGoReviewFromArchive() {
    wx.navigateTo({ url: '/pages/review/review' });
  },

  /** 删除愿望（属主可删 · 二次确认） */
  onDeleteWish(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '放下这个愿望',
      content: '删除后月光就不再保管它了，确定吗？',
      confirmText: '放下',
      confirmColor: '#B08F52',
      cancelText: '再想想',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request(`/wishes/${id}`, { method: 'DELETE' });
          wx.showToast({ title: '已放下 ✦', icon: 'none' });
          await this._refreshList();
        } catch (_err) {
          wx.showToast({ title: '删除失败，请稍后再试', icon: 'none' });
        }
      },
    });
  },

  async _refreshList() {
    try {
      const res = await request('/wishes');
      const wishes = this._decorate(res.wishes || []);
      this.setData({
        wishes,
        activeCount: res.active_count || wishes.filter(w => w.status === 'active').length,
      });
    } catch (_err) { /* silent */ }
  },

  onUnload() {
    if (this._subscribeTimer) { clearTimeout(this._subscribeTimer); this._subscribeTimer = null; }
  },
});
