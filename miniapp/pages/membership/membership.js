// pages/membership/membership.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

Page({
  data: {
    products: [],
    user: null,
    loading: true,
  },

  async onLoad() {
    try {
      const user = await checkLogin();
      const products = await request('/membership/products');
      this.setData({ user, products, loading: false });
    } catch (err) {
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  async onPurchase(e) {
    const product = e.currentTarget.dataset.product;
    try {
      wx.showLoading({ title: '创建订单...' });
      const order = await request('/orders', {
        method: 'POST',
        data: { product_type: product.id },
      });
      wx.hideLoading();

      wx.showModal({
        title: '确认支付',
        content: `${product.name}\n¥${product.price}`,
        confirmText: '支付',
        success: async (res) => {
          if (res.confirm) {
            // In production, call wx.requestPayment with the order params
            wx.showToast({ title: '支付成功！', icon: 'success' });
            setTimeout(() => {
              wx.switchTab({ url: '/pages/profile/profile' });
            }, 1500);
          }
        },
      });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '下单失败', icon: 'none' });
    }
  },
});
