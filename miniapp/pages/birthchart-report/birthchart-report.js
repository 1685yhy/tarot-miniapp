// pages/birthchart-report/birthchart-report.js
// 本命星盘深度报告（开发 05 · 二期核心付费点）
// 会员免费；非会员 19.9 解锁（birthchart_report 商品 → 权益 birthchart_paid）
// 流程：校验权益 → POST /user/birthchart/report（AI 生成一次并缓存）→ 展示四段
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const { fetchBirthchart } = require('../../utils/birthchart');
const { drawBirthchartPoster } = require('../../utils/canvas-poster');
const analytics = require('../../utils/analytics');
const { startPay, isComingSoonError, showComingSoonModal } = require('../../utils/pay');

const PRODUCT = 'birthchart_report';

const SECTIONS = [
  { key: 'character', title: '性格底色', icon: '☀', desc: '日月升合一 · 更完整的你' },
  { key: 'relation', title: '关系模式', icon: '☽', desc: '亲密与友谊中的相处之道' },
  { key: 'annual_theme', title: '年度主题', icon: '✦', desc: '今年的成长课题与方向' },
  { key: 'card_advice', title: '牌面建议', icon: '🃏', desc: '一张牌 + 今天就能做的小事' },
];

Page({
  data: {
    state: 'checking', // checking | loading | paywall | report | error
    sections: SECTIONS,
    report: null,       // { character, relation, annual_theme, card_advice, generated_at }
    chart: null,
    isMember: false,
    birthchartPaid: false,
    purchasing: false,
    sharePosterPath: '',
    showSharePoster: false,
    sharePosterDrawing: false,
    errorMsg: '',
  },

  async onLoad() {
    analytics.trackEvent('birthchart_report_open', {});
    this._init();
  },

  async _init() {
    this.setData({ state: 'checking' });
    try {
      // 权益状态（会员 / 单次解锁）
      const user = await checkLogin({ refresh: true });
      const isMember = !!(user && user.is_member);
      const birthchartPaid = !!(user && user.birthchart_paid);
      this.setData({ isMember, birthchartPaid });

      // 星盘数据（出生信息是否完整）
      const chart = await fetchBirthchart({ force: true });
      if (!chart.birth || !chart.birth.date) {
        // 未填出生日期 → 引导
        wx.showModal({
          title: '先完善星盘',
          content: '填写出生日期与时间，才能生成深度星图报告 ✦',
          confirmText: '去填写',
          cancelText: '暂不',
          success: (res) => {
            if (res.confirm) {
              wx.redirectTo({ url: '/pages/birth-info/birth-info' });
            } else {
              this.setData({ state: 'error', errorMsg: '请先完善出生信息' });
            }
          },
        });
        return;
      }
      this.setData({ chart });

      if (isMember || birthchartPaid) {
        await this._generateReport();
      } else {
        this.setData({ state: 'paywall' });
        analytics.trackPaywallView('birthchart_report');
      }
    } catch (err) {
      this.setData({ state: 'error', errorMsg: getFriendlyError(err) });
    }
  },

  /** 生成/读取深度报告（后端缓存）；支付回调可能晚 1-2 秒到账 → 402 短暂重试 */
  async _generateReport(retries = 3) {
    this.setData({ state: 'loading' });
    try {
      wx.showLoading({ title: '星光照见中...', mask: true });
      const report = await request('/user/birthchart/report', { method: 'POST', timeout: 120000 });
      wx.hideLoading();
      this.setData({ state: 'report', report });
      analytics.trackEvent('birthchart_report_generated', { cached: report.cached });
    } catch (err) {
      wx.hideLoading();
      if (err.statusCode === 402 && retries > 0) {
        // 支付回调尚未到账 — 短暂等待后重试
        setTimeout(() => this._generateReport(retries - 1), 1500);
        return;
      }
      if (err.statusCode === 402) {
        // 权益过期/被回收 → 回到付费墙
        this.setData({ state: 'paywall', errorMsg: '' });
        analytics.trackPaywallView('birthchart_report');
        return;
      }
      this.setData({ state: 'error', errorMsg: getFriendlyError(err) });
    }
  },

  /** 19.9 解锁：下单 → 微信支付 → 生成报告 */
  async onUnlock(e) {
    if (this.data.purchasing) return;
    analytics.funnel('purchase_started', { product: PRODUCT });
    this.setData({ purchasing: true });
    try {
      wx.showLoading({ title: '创建订单...' });
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: PRODUCT },
      });
      wx.hideLoading();

      // 统一支付入口：xpay 虚拟支付 / 旧 JSAPI 双通道（P0-1）
      startPay(order, {
        product: { id: PRODUCT },
        success: () => {
          this.setData({ purchasing: false, birthchartPaid: true });
          analytics.trackPurchaseComplete({ id: PRODUCT }, 19.9, {});
          wx.showToast({ title: '解锁成功 ✦', icon: 'success' });
          this._generateReport();
        },
        fail: (err) => {
          this.setData({ purchasing: false });
          if (err.reason === 'user_cancel') {
            analytics.trackPurchaseFail({ id: PRODUCT }, 'user_cancel');
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else if (err.reason === 'coming_soon') {
            // 商品即将上线 → 降级弹窗（不进失败漏斗）
            showComingSoonModal();
          } else {
            analytics.trackPurchaseFail({ id: PRODUCT }, 'payment_failed');
            wx.showToast({ title: err.message || '支付失败，请重试', icon: 'none' });
          }
        },
      });
    } catch (err) {
      this.setData({ purchasing: false });
      wx.hideLoading();
      if (isComingSoonError(err)) {
        // 400「该商品即将上线」→ 降级弹窗（不进失败漏斗）
        showComingSoonModal();
        return;
      }
      analytics.trackPurchaseFail({ id: PRODUCT }, 'order_failed');
      if (err.statusCode === 503) {
        // 微信支付商户未开通 JSAPI 权限 → 明确提示
        wx.showModal({
          title: '支付暂未开通',
          content: '微信支付商户尚未配置完成，请稍后再试。',
          showCancel: false,
        });
        return;
      }
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },

  /** 分享图：canvas 海报 → 预览 */
  async onSharePoster() {
    if (this.data.sharePosterDrawing) return;
    this.setData({ sharePosterDrawing: true });
    analytics.trackEvent('birthchart_report_poster', {});
    try {
      wx.showLoading({ title: '绘制分享图...' });
      const path = await new Promise((resolve, reject) => {
        drawBirthchartPoster('birthchart-poster', {
          context: this,
          elements: this._posterElements(),
          quote: (this.data.report && this.data.report.character || '').slice(0, 60),
          nickname: '',
          dateText: this._fmtDate(),
          onSuccess: resolve,
          onError: reject,
        });
      });
      wx.hideLoading();
      this.setData({ sharePosterPath: path, showSharePoster: true, sharePosterDrawing: false });
    } catch (err) {
      wx.hideLoading();
      this.setData({ sharePosterDrawing: false });
      wx.showToast({ title: '分享图生成失败', icon: 'none' });
    }
  },

  _posterElements() {
    const chart = this.data.chart || {};
    return ['sun', 'moon', 'rising'].map((role) => {
      const el = chart[role];
      if (!el) return null;
      return {
        icon: el.icon,
        displayName: el.displayName,
        line: el.line,
        approx: el.approx,
      };
    }).filter(Boolean);
  },

  _fmtDate() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}.${m}.${day}`;
  },

  onClosePoster() {
    this.setData({ showSharePoster: false, sharePosterPath: '' });
  },

  /** 保存分享图到相册 */
  onSavePoster() {
    const path = this.data.sharePosterPath;
    if (!path) return;
    wx.saveImageToPhotosAlbum({
      filePath: path,
      success: () => {
        analytics.trackShare('album', 'birthchart_report_poster');
        wx.showToast({ title: '已保存到相册 ✦', icon: 'success' });
        this.setData({ showSharePoster: false });
      },
      fail: (err) => {
        if (err.errMsg && err.errMsg.includes('auth')) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在设置中允许保存图片到相册',
            confirmText: '去设置',
            success: (res) => {
              if (res.confirm) wx.openSetting();
            },
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      },
    });
  },

  onPreviewPoster() {
    const path = this.data.sharePosterPath;
    if (path) wx.previewImage({ urls: [path] });
  },

  onGoElements() {
    wx.navigateTo({ url: '/pages/birthchart/birthchart' });
  },

  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onRetry() {
    this._init();
  },

  onShareAppMessage() {
    const chart = this.data.chart || {};
    const sun = chart.sun || {};
    return {
      title: sun.displayName ? `我的本命星盘：${sun.displayName} ✦` : '星光映照 · 看看你的本命星盘',
      path: '/pages/birthchart/birthchart',
    };
  },
});
