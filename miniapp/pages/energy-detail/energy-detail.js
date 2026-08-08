// pages/energy-detail/energy-detail.js
// 今日屏能量注脚 → 点击进入；chips 页内切换维度
// 数据源：GET /horoscope/daily（真实接口 · 分数 / factors / summary / tip）
// 降级：接口失败 → 本地缓存 → mock 兜底（utils/energy.js fetchTodayEnergy）
const { ENERGY, ENERGY_KEYS, fetchTodayEnergy } = require('../../utils/energy');
const analytics = require('../../utils/analytics');

Page({
  data: {
    dims: [],          // chips：{key, name}
    dimKey: 'love',
    dd: null,          // 当前维度详情（真实分数 + 真实 factors/tip + mock 文案兜底）
    todayCardName: '月亮牌',
    todayCardEn: '',
    energySource: '',  // 'api' | 'cache' | 'mock'（降级提示用）
    loading: true,
  },

  onLoad(options) {
    const dims = ENERGY_KEYS.map((k) => ({ key: k, name: ENERGY[k].name }));
    const requested = options && options.dim;
    const dimKey = ENERGY_KEYS.indexOf(requested) >= 0 ? requested : 'love';

    // 与今日牌的关联：今日屏抽牌后写入 storage
    let cardName = '';
    try { cardName = wx.getStorageSync('today_card_name') || ''; } catch (e) { /* silent */ }
    if (!cardName) {
      const app = getApp();
      cardName = (app.globalData.dailyCard && (app.globalData.dailyCard.name_zh || app.globalData.dailyCard.name_cn)) || '';
    }

    this.setData({ dims, dimKey, todayCardName: cardName || '月亮牌' });
    wx.setNavigationBarTitle({ title: `今日能量 · ${ENERGY[dimKey].name}` });
    analytics.trackEvent('energy_detail_view', { dim: dimKey });
    this._loadEnergy();
  },

  /** 拉取今日能量（真实接口 / 降级），并应用到当前维度 */
  async _loadEnergy() {
    const data = await fetchTodayEnergy();
    this._energy = data;
    this._applyDim(this.data.dimKey, data);
    this.setData({ energySource: data.source, loading: false });
  },

  /** 维度数据组装：分数/level/factors/tip 用接口值，配色与走心文案用 mock 兜底 */
  _applyDim(key, data) {
    const item = (data.items || []).find((i) => i.key === key) || { score: ENERGY[key].score, level: '中' };
    const mock = ENERGY[key];
    const factors = (data.factors && data.factors[key]) || [];
    const astral = data.astral || {};
    const dd = {
      ...mock,
      score: item.score,
      level: item.level || '中',
      // 大数字下方注脚：真实天象（如「节气 · 立秋 · 月亮在摩羯」）
      note: astral.label ? `天象 · ${astral.label}` : mock.note,
      // 认领层：今日总分评（真实 summary）
      catch: data.summary || mock.catch,
      // 为什么今天这样：真实 factors（如「满月 +6 · 圣杯六 +2」）+ astral note 补充
      factors: factors.map((f) => ({ ...f })),
      factorsText: factors.map((f) => `${f.name} ${f.delta >= 0 ? '+' : ''}${f.delta}`).join(' · '),
      astralNote: astral.note || '',
      // 温柔提示：真实 tip
      tip: data.tip || mock.tip,
      // 金句 / 30 秒小事 / 牌关联：mock 走心文案（无数据断言，仅风格化）
      line: mock.line,
      do30: mock.do30,
      card: mock.card,
    };
    this.setData({ dd, dimKey: key });
  },

  onSwitchDim(e) {
    const key = e.currentTarget.dataset.key;
    if (!key || key === this.data.dimKey) return;
    this.setData({ dimKey: key });
    if (this._energy) {
      this._applyDim(key, this._energy);
    }
    wx.setNavigationBarTitle({ title: `今日能量 · ${ENERGY[key].name}` });
    try { wx.vibrateShort({ type: 'light' }); } catch (err) { /* silent */ }
    analytics.trackEvent('energy_detail_switch', { dim: key });
  },

  /** 接口失败（降级到 mock/缓存）后点击重新获取 */
  async onRefreshEnergy() {
    wx.showLoading({ title: '重新获取中...' });
    const data = await fetchTodayEnergy({ force: true });
    this._energy = data;
    this._applyDim(this.data.dimKey, data);
    this.setData({ energySource: data.source });
    wx.hideLoading();
    if (data.source !== 'api') {
      wx.showToast({ title: '网络未恢复 · 稍后再试', icon: 'none' });
    } else {
      wx.showToast({ title: '能量已刷新 ✦', icon: 'success' });
    }
  },

  /** 与今日牌的关联文案（把 mock 里的「月亮牌」替换为今日实际牌名） */
  cardLinkText() {
    const dd = this.data.dd;
    const tpl = dd && dd.card ? dd.card : '';
    if (!tpl) return '';
    return tpl.split('月亮牌').join(this.data.todayCardName);
  },

  onBack() {
    wx.navigateBack({ delta: 1 });
  },
});
