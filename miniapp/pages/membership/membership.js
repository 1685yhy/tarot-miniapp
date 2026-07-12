// pages/membership/membership.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    products: [],
    pageLoading: true,
    pageError: null,
    purchasing: false,
  },

  async onLoad(options) {
    try {
      const user = await checkLogin();
      const allProducts = await request('/membership/products');
      // Filter to show only membership-type products (hide single_reading/annual_report)
      let products = allProducts.filter(p => p.type === 'membership');
      // If navigated from annual-report page, also include the annual_report product
      if (options && options.product === 'annual_report') {
        const annualReportProduct = allProducts.find(p => p.id === 'annual_report');
        if (annualReportProduct) {
          products = [...products, annualReportProduct];
        }
      }
      // Precompute display strings to avoid WXML method calls
      products = products.map(p => {
        const display = { ...p };
        if (p.id === 'membership_yearly') {
          display.pricePerDay = (p.price / 365).toFixed(2);
        }
        return display;
      });
      this.setData({ products, pageLoading: false });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.onLoad();
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
        signType: params.signType || 'MD5',
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
