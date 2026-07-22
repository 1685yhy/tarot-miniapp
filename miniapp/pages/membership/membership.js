// pages/membership/membership.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

const TRIAL_STORAGE_KEY = 'trial_expiry';
const TRIAL_MEMBER_KEY = 'is_trial_member';
const TRIAL_DURATION_MS = 3 * 24 * 60 * 60 * 1000; // 3 days

Page({
  data: {
    pageLoading: true,
    pageError: null,
    purchasing: false,
    isTrialActive: false,
    trialExpiryDate: null,
    trialDaysLeft: 0,
    comparisonRows: [
      { label: '每日解读', free: '1次', pro: '无限' },
      { label: '每日追问', free: '3次', pro: '无限' },
      { label: '可用牌阵', free: '4种基础', pro: '10种全部' },
      { label: '行动建议', free: '✓', pro: '✓' },
      { label: '年度报告', free: '✗', pro: '✓' },
      { label: '每日一牌教学', free: '✓', pro: '✓' },
      { label: '解读历史回顾', free: '✓', pro: '✓' },
      { label: '专属客服', free: '✗', pro: '✓' },
    ],
    // 定价卡片数据（固定值，不依赖后端）
    pricingMonthly: {
      id: 'membership_monthly',
      name: '月度会员',
      price: 19.9,
      type: 'membership',
    },
    pricingYearly: {
      id: 'membership_yearly',
      name: '年度会员',
      price: 168,
      type: 'membership',
    },
    pricingStudent: {
      id: 'membership_student',
      name: '学生会员',
      price: 9.9,
      type: 'membership',
    },
  },

  async onLoad(options) {
    try {
      await checkLogin();
      this._checkTrialStatus();
      this.setData({ pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: getFriendlyError(err) });
    }
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
        wx.removeStorageSync(TRIAL_STORAGE_KEY);
        wx.removeStorageSync(TRIAL_MEMBER_KEY);
      }
    }
  },

  onReady() {
    // Analytics & accessibility hook — reserved for future use
  },

  onHide() {
    // Cleanup hook — reserved for future use
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
  },

  /** 开启 3 天免费试用 */
  onStartTrial() {
    const trialExpiry = Date.now() + TRIAL_DURATION_MS;
    wx.setStorageSync(TRIAL_STORAGE_KEY, trialExpiry);
    wx.setStorageSync(TRIAL_MEMBER_KEY, true);
    this.setData({
      isTrialActive: true,
      trialExpiryDate: trialExpiry,
      trialDaysLeft: 3,
    });
    wx.showToast({ title: '试用已开启！3天内畅享全部功能', icon: 'success' });
    // 跳转到首页，让用户立即体验
    setTimeout(() => {
      wx.switchTab({ url: '/pages/index/index' });
    }, 1500);
  },

  async onPurchase(e) {
    if (this.data.purchasing) return;
    const product = e.currentTarget.dataset.product;
    this.setData({ purchasing: true });
    try {
      wx.showLoading({ title: '创建订单...' });
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: product.id },
      });
      wx.hideLoading();

      // Check if payment is configured
      if (!order.payment_params) {
        this.setData({ purchasing: false });
        wx.showModal({
          title: '支付未配置',
          content: '微信支付商户尚未配置完成。请先在服务器 .env 中配置 WECHAT_MCH_ID 和 WECHAT_API_KEY_V3。',
          showCancel: false,
        });
        return;
      }

      // Call WeChat Pay JSAPI
      const params = order.payment_params;
      if (!params) {
        this.setData({ purchasing: false });
        wx.showToast({ title: '支付参数错误', icon: 'none' });
        return;
      }

      wx.requestPayment({
        timeStamp: params.timeStamp,
        nonceStr: params.nonceStr,
        package: params.package,
        // NOTE: 如果后端签名仍使用 MD5，需要同步升级到 HMAC-SHA256
        signType: params.signType || 'HMAC-SHA256',
        paySign: params.paySign,
        success: () => {
          this.setData({ purchasing: false });
          wx.showToast({ title: '支付成功！', icon: 'success' });
          setTimeout(() => {
            wx.redirectTo({ url: '/pages/reading/reading' });
          }, 1500);
        },
        fail: (err) => {
          this.setData({ purchasing: false });
          if (err.errMsg && err.errMsg.includes('cancel')) {
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else {
            wx.showToast({ title: '支付失败，请重试', icon: 'none' });
          }
        },
      });
    } catch (err) {
      this.setData({ purchasing: false });
      wx.hideLoading();
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },
});
