const { request } = require('./api');

const login = async () => {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (res) => {
        try {
          const data = await request('/auth/login', {
            method: 'POST',
            data: { code: res.code },
          });
          wx.setStorageSync('token', data.token);
          wx.setStorageSync('user', data.user);
          resolve(data.user);
        } catch (err) {
          reject(err);
        }
      },
      fail: reject,
    });
  });
};

// 开发模式：后端没有真实微信AppSecret时，用dev-login绕过
const devLogin = async () => {
  const data = await request('/auth/dev-login', { method: 'POST' });
  wx.setStorageSync('token', data.token);
  wx.setStorageSync('user', data.user);
  return data.user;
};

const checkLogin = async (options = {}) => {
  const token = wx.getStorageSync('token');
  if (token) {
    // refresh=true 时从服务端拉取最新数据，避免缓存过时（如刚购买的会员状态）
    if (options.refresh) {
      try {
        const freshData = await request('/membership/status');
        // 合并进缓存，兼容 partial 返回
        const cachedUser = wx.getStorageSync('user') || {};
        const freshUser = { ...cachedUser, ...freshData };
        wx.setStorageSync('user', freshUser);
        return freshUser;
      } catch {
        // 刷新失败降级到缓存
        return wx.getStorageSync('user');
      }
    }
    return wx.getStorageSync('user');
  }
  // 先试真登录，失败则fallback到dev登录
  try {
    return await login();
  } catch (err) {
    console.warn('[auth] 微信登录失败，使用开发模式登录:', err.message);
    return await devLogin();
  }
};

module.exports = { login, checkLogin };
