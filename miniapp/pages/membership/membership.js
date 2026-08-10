// pages/membership/membership.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const analytics = require('../../utils/analytics');
const { startPay, isComingSoonError, showComingSoonModal } = require('../../utils/pay');

const TRIAL_STORAGE_KEY = 'trial_expiry';
const TRIAL_MEMBER_KEY = 'is_trial_member';
const TRIAL_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

Page({
  data: {
    pageLoading: true,
    pageError: null,
    purchasing: false,
    isTrialActive: false,
    trialExpiryDate: null,
    trialDaysLeft: 0,
    comparisonRows: [], // dynamically populated from API on load
    comparisonSavings: {
      monthly: { value: '¥297', save: '¥277' },
      yearly: { value: '¥3,613', save: '¥3,445' },
    },
    paymentSuccess: false,
    showCelebration: false,

    // P2-3: 权益对比表 / 补充解读包 默认折叠
    cmpExpanded: false,
    packExpanded: false,
    unlockedBenefits: [
      { icon: '✨', text: '已解锁 10 种牌阵' },
      { icon: '💬', text: '无限 AI 追问' },
      { icon: '🎭', text: '3 位专属塔罗师' },
      { icon: '📊', text: '年度运势报告' },
    ],
    // 定价卡片数据（固定值，不依赖后端；API返回时会被覆盖）
    pricingMonthly: {
      id: 'membership_monthly',
      name: '月度会员',
      price: 19.9,
      type: 'membership',
      displayPrice: '19.9',
    },
    pricingYearly: {
      id: 'membership_yearly',
      name: '年度会员',
      price: 168,
      type: 'membership',
      displayPrice: '168',
      displayDaily: '¥0.46',
      displaySavingText: '相比月度省 30%',
    },
    pricingStudent: {
      id: 'membership_student',
      name: '特惠会员',
      price: 9.9,
      type: 'membership',
      displayPrice: '9.9',
      displayOriginalPrice: '19.9',
    },
    // 补充包（一次性购买，不自动续费）
    pricingPack3: {
      id: 'reading_pack_3',
      name: '3次深度解读包',
      price: 9.9,
      type: 'reading_pack',
      displayPrice: '9.90',
      displayUnitPrice: '¥3.30/次',
    },
    pricingPack10: {
      id: 'reading_pack_10',
      name: '10次深度解读包',
      price: 29.9,
      type: 'reading_pack',
      displayPrice: '29.90',
      displayUnitPrice: '¥2.99/次 · 省¥69',
    },
  },

  async onLoad(options) {
    // Analytics: page view + pricing funnel
    analytics.pageView('membership');
    analytics.funnel('pricing_viewed');
    // Analytics: paywall impression
    analytics.trackPaywallView('membership_page');

    try {
      const user = await checkLogin({ refresh: true });
      const app = getApp();
      app.globalData.memberStatus = { free_quota: user.free_quota || {} };
      this._populateComparisonTable(user);
      this._checkTrialStatus();
      // Fetch dynamic pricing from API (falls back to hardcoded values on failure)
      await this._fetchProducts();
      this.setData({ pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
  },

  /** Populate comparison table from real membership status data */
  _populateComparisonTable(user) {
    const quota = user.free_quota || {};
    const dailyReadings = quota.daily_readings || 3;
    const dailyChats = quota.daily_chats || 3;
    this.setData({
      comparisonRows: [
        { label: '每日解读', free: `${dailyReadings}次`, pro: '无限' },
        { label: '每日追问', free: `${dailyChats}次`, pro: '无限' },
        { label: '可用牌阵', free: '4种基础', pro: '10种全部' },
        { label: '行动建议', free: '✓', pro: '✓' },
        { label: '年度报告', free: '✗', pro: '✓' },
        { label: '每日一牌教学', free: '✓', pro: '✓' },
        { label: '解读历史回顾', free: '✓', pro: '✓' },
        { label: '专属客服', free: '✗', pro: '✓' },
      ],
    });
  },

  /* ---------------------------------------------------------------
     Dynamic Pricing — fetch products from API, fall back to hardcoded
     --------------------------------------------------------------- */

  /** Fetch product list from API and populate pricing cards */
  async _fetchProducts() {
    try {
      const products = await request('/membership/products');
      if (Array.isArray(products) && products.length > 0) {
        const pricing = this._mapProductsToPricing(products);
        this.setData(pricing);
      }
    } catch (err) {
      console.warn('[membership] API fetch failed, using hardcoded pricing:', err.message);
      // Hardcoded values already in data with displayProps — no action needed
    }
  },

  /** Map API product array to pricing card data with computed display properties */
  _mapProductsToPricing(products) {
    const map = {};
    products.forEach(p => { map[p.id] = p; });

    const m   = map['membership_monthly']  || { price: 19.9,  name: '月度会员' };
    const y   = map['membership_yearly']   || { price: 168,   name: '年度会员' };
    const s   = map['membership_student']  || { price: 9.9,   name: '特惠会员' };
    const p3  = map['reading_pack_3']       || { price: 9.9,  name: '3次深度解读包' };
    const p10 = map['reading_pack_10']      || { price: 29.9, name: '10次深度解读包' };
    const sr  = map['single_reading']       || { price: 9.9,  name: '单次深度占卜' };

    const mp  = m.price;
    const yp  = y.price;
    const sp  = s.price;
    const srp = sr.price;

    // Computed display values
    const dailyCost       = (yp / 365).toFixed(2);
    const yearlyVsMonthly = Math.round((1 - yp / (mp * 12)) * 100);

    // Comparison savings (marketing-value multipliers)
    const monthlyValue = Math.round(mp * 15);
    const monthlySave  = Math.round(mp * 14);
    const yearlyValue  = Math.round(yp * 21.5);
    const yearlySave   = Math.round(yp * 20.5);

    // Pack per-reading costs
    const p3Unit  = (p3.price / 3).toFixed(2);
    const p10Unit = (p10.price / 10).toFixed(2);
    const p10Save = Math.round(srp * 10 - p10.price);

    return {
      pricingMonthly: {
        id: 'membership_monthly', name: m.name, price: mp, type: 'membership',
        displayPrice: mp % 1 === 0 ? String(mp) : mp.toFixed(1),
      },
      pricingYearly: {
        id: 'membership_yearly', name: y.name, price: yp, type: 'membership',
        displayPrice: String(Math.round(yp)),
        displayDaily: `¥${dailyCost}`,
        displaySavingText: `相比月度省 ${yearlyVsMonthly}%`,
      },
      pricingStudent: {
        id: 'membership_student', name: s.name, price: sp, type: 'membership',
        displayPrice: sp % 1 === 0 ? String(sp) : sp.toFixed(1),
        displayOriginalPrice: mp % 1 === 0 ? String(mp) : mp.toFixed(1),
      },
      pricingPack3: {
        id: 'reading_pack_3', name: p3.name, price: p3.price, type: 'reading_pack',
        displayPrice: p3.price.toFixed(2),
        displayUnitPrice: `¥${p3Unit}/次`,
      },
      pricingPack10: {
        id: 'reading_pack_10', name: p10.name, price: p10.price, type: 'reading_pack',
        displayPrice: p10.price.toFixed(2),
        displayUnitPrice: `¥${p10Unit}/次 · 省¥${p10Save}`,
      },
      comparisonSavings: {
        monthly: { value: `¥${monthlyValue}`, save: `¥${monthlySave}` },
        yearly:  { value: `¥${yearlyValue}`,  save: `¥${yearlySave}` },
      },
    };
  },

  /** 检查本地试用状态 */
  _checkTrialStatus() {
    const expiry = wx.getStorageSync(TRIAL_STORAGE_KEY);
    const isTrial = wx.getStorageSync(TRIAL_MEMBER_KEY);
    if (expiry && isTrial) {
      const now = Date.now();
      if (now < expiry) {
        const daysLeft = Math.ceil((expiry - now) / (24 * 60 * 60 * 1000));
        this.setData({
          isTrialActive: true,
          trialExpiryDate: expiry,
          trialDaysLeft: daysLeft,
        });
      } else {
        // 试用已过期，清除状态
        // Analytics: trial ended without conversion (Task 2.4)
        analytics.trackTrialExpire();
        wx.removeStorageSync(TRIAL_STORAGE_KEY);
        wx.removeStorageSync(TRIAL_MEMBER_KEY);
      }
    }
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onUnload() {
    this._clearTimers();
  },

  onHide() {
    this._clearTimers();
  },

  _clearTimers() {
    if (this._timers) {
      this._timers.forEach(t => clearTimeout(t));
      this._timers = [];
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  /** 开启 7 天免费试用 */
  onStartTrial() {
    // Analytics: free trial started
    analytics.trackTrialStart();
    const trialExpiry = Date.now() + TRIAL_DURATION_MS;
    wx.setStorageSync(TRIAL_STORAGE_KEY, trialExpiry);
    wx.setStorageSync(TRIAL_MEMBER_KEY, true);
    this.setData({
      isTrialActive: true,
      trialExpiryDate: trialExpiry,
      trialDaysLeft: 7,
    });
    wx.showToast({ title: '试用已开启！7天内畅享全部功能', icon: 'success' });
    // 跳转到首页，让用户立即体验
    if (!this._timers) this._timers = [];
    this._timers.push(setTimeout(() => {
      wx.switchTab({ url: '/pages/index/index' });
    }, 1500));
  },

  async onPurchase(e) {
    if (this.data.purchasing) return;
    const product = e.currentTarget.dataset.product;

    // Task 2.7: A/B price bucket — set by reading-result onLoad, attach to
    // every purchase event so conversion can be compared per bucket
    const abBucket = wx.getStorageSync('price_test_bucket');
    const abExtra = abBucket ? { priceTestBucket: abBucket } : {};

    // Analytics: funnel — purchase started
    analytics.funnel('purchase_started', { product: product.id, ...abExtra });
    // Analytics: purchase intent
    analytics.trackPurchaseStart(product, abExtra);

    this.setData({ purchasing: true });
    try {
      wx.showLoading({ title: '创建订单...' });
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: product.id },
      });
      wx.hideLoading();

      // 统一支付入口：xpay 虚拟支付 / 旧 JSAPI 双通道（P0-1）
      startPay(order, {
        product,
        success: () => {
          // Analytics: purchase completed
          analytics.trackPurchaseComplete(product, product.price, abExtra);
          this.setData({ purchasing: false, paymentSuccess: true, showCelebration: true });
          // Auto-navigate back after 2s celebration
          if (!this._timers) this._timers = [];
          this._timers.push(setTimeout(() => {
            this.setData({ showCelebration: false });
            wx.redirectTo({ url: '/pages/reading/reading' });
          }, 2500));
        },
        fail: (err) => {
          this.setData({ purchasing: false });
          if (err.reason === 'user_cancel') {
            analytics.trackPurchaseFail(product, 'user_cancel');
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else if (err.reason === 'coming_soon') {
            // 商品即将上线 → 降级弹窗（不进失败漏斗）
            showComingSoonModal();
          } else {
            analytics.trackPurchaseFail(product, 'payment_failed');
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
      analytics.trackPurchaseFail(product, 'order_failed');
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },

  /** 购买补充包（复用 onPurchase 的逻辑） */
  onPurchasePack(e) {
    // Delegate to onPurchase with the same data format
    this.onPurchase(e);
  },

  /** P2-3: 展开/收起权益对比表 */
  onToggleCmp() {
    this.setData({ cmpExpanded: !this.data.cmpExpanded });
  },

  /** P2-3: 展开/收起补充解读包 */
  onTogglePack() {
    this.setData({ packExpanded: !this.data.packExpanded });
  },

  /** 补充包详情：简单提示一次性、永不过期 */
  onPackDetail() {
    wx.showModal({
      title: '什么是「深度解读包」？',
      content: '一次性购买，永不过期。不限制使用期限，每次解读消耗1次，用完为止。不与会员权益冲突，会员同样可以叠加购买。',
      showCancel: false,
      confirmText: '知道了',
    });
  },

});
