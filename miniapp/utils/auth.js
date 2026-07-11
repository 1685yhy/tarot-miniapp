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

const checkLogin = async () => {
  const token = wx.getStorageSync('token');
  if (!token) {
    return await login();
  }
  return wx.getStorageSync('user');
};

module.exports = { login, checkLogin };
