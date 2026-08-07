const { request } = require('./api');
const { DEV_LOGIN_KEY } = require('./config');

let loginPromise = null;

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
// 安全：仅此端点携带 X-Dev-Key 保护密钥（开发环境才可用的旁路登录）
const devLogin = async () => {
  const data = await request('/auth/dev-login', {
    method: 'POST',
    header: { 'X-Dev-Key': DEV_LOGIN_KEY },
  });
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
      } catch(e) {
        // 刷新失败降级到缓存
        return wx.getStorageSync('user');
      }
    }
    return wx.getStorageSync('user');
  }

  // 进行中锁：防止并发调用重复发起登录请求
  if (loginPromise) {
    return loginPromise;
  }

  loginPromise = (async () => {
    try {
      // 先试真登录，失败则视环境决定是否降级到dev登录
      try {
        return await login();
      } catch (err) {
        if (typeof __wxConfig !== 'undefined' && __wxConfig.envVersion !== 'release') {
          console.warn('[auth] 微信登录失败，使用开发模式登录:', err.message);
          return await devLogin();
        }
        // 正式版（release）不降级，让调用方的错误处理提示用户重试
        console.warn('[auth] 微信登录失败:', err.message);
        throw err;
      }
    } finally {
      loginPromise = null; // 完成后清锁
    }
  })();

  return loginPromise;
};

module.exports = { login, checkLogin };
