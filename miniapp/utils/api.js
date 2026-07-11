/**
 * API client with environment-aware base URL.
 *
 * Development:  http://localhost:8000
 * Trial/Preview: https://your-dev-domain.com  (extConfig override)
 * Release:       https://your-production-domain.com  (extConfig override)
 */

const ENV = (() => {
  try {
    const info = wx.getAccountInfoSync();
    return info.miniProgram ? info.miniProgram.envVersion : 'release';
  } catch {
    return 'release';
  }
})();

const ENV_URLS = {
  develop: 'http://localhost:8000',
  trial: 'https://trial-api.tarot.example.com',
  release: 'https://your-domain.com',
};

// Allow override via extConfig (deployed through第三方平台)
let extBaseUrl = null;
try {
  const ext = wx.getExtConfigSync ? wx.getExtConfigSync() : {};
  if (ext.BASE_URL) extBaseUrl = ext.BASE_URL;
} catch {
  // extConfig not available
}

const BASE_URL = extBaseUrl || ENV_URLS[ENV] || 'https://your-domain.com';

// Safety check: fail loudly if placeholder domain leaked into production/trial
if (BASE_URL.includes('your-domain') && ENV !== 'develop') {
  console.error('[tarot] CRITICAL: BASE_URL contains placeholder domain. Configure via extConfig.BASE_URL or update ENV_URLS.');
}

const request = async (url, options = {}) => {
  const token = wx.getStorageSync('token');

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options.header,
      },
      success: (res) => {
        if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.reLaunch({ url: '/pages/index/index' });
          reject(new Error('登录过期'));
        } else if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(res.data?.detail || '请求失败'));
        }
      },
      fail: reject,
    });
  });
};

module.exports = { request, BASE_URL };
