/**
 * API 客户端 —— 环境感知的 Base URL 配置
 * =============================================
 *
 * 【部署前必改】 将下方 ENV_URLS.release 中的占位符替换为真实域名：
 *
 *    release: 'https://api.your-domain.com'
 *
 * 或通过 第三方平台 (extConfig) 的 BASE_URL 参数注入（优先级更高）。
 *
 * 环境检测逻辑：
 *   - develop  → 开发环境使用 IP 直连后端 （即使 release URL 是占位符也不受影响）
 *   - trial    → 使用 extConfig 中 BASE_URL 或 ENV_URLS.trial
 *   - release  → 使用 extConfig 中 BASE_URL 或 ENV_URLS.release（发布前必须替换占位符！）
 */

const ENV = (() => {
  try {
    const info = wx.getAccountInfoSync();
    return info.miniProgram ? info.miniProgram.envVersion : 'release';
  } catch(e) {
    return 'release';
  }
})();

/**
 * 环境 URL 映射表
 * ------------------------------------------------------------
 * deploy   开发用直接 IP (nginx:80 → backend:8000)
 * trial    体验版域名（替换为你的测试域名）
 * release  【★ 部署前必须修改 ★】替换为生产域名
 */
const ENV_URLS = {
  develop: 'http://124.221.233.214/api',
  trial: 'https://xingxiang.chat/api',
  release: 'https://xingxiang.chat/api',
};

// 允许通过 extConfig 覆盖 BASE_URL（第三方平台托管场景）
let extBaseUrl = null;
try {
  const ext = wx.getExtConfigSync ? wx.getExtConfigSync() : {};
  if (ext.BASE_URL) extBaseUrl = ext.BASE_URL;
} catch(e) {
  // extConfig not available
}

// 最终 BASE_URL：extConfig > 环境映射表 > 兜底
const BASE_URL = extBaseUrl || ENV_URLS[ENV] || 'https://your-domain.com';

/**
 * 占位符检测（双重保障）
 *   - develop 环境下：如果 release URL 仍为占位符，不影响开发（但会在控制台提示）
 *   - trial/release 下检测到占位符 → 直接报错，防止带着占位符上线
 */
if (BASE_URL.includes('your-domain') && ENV !== 'develop') {
  console.error(
    '[tarot] 严重错误：BASE_URL 仍包含占位符 "your-domain"！\n' +
    '  请在 api.js 中将 ENV_URLS.release 替换为真实域名，\n' +
    '  或通过第三方平台的 extConfig.BASE_URL 传入正确地址。'
  );
  // 给用户可见提示，避免带着占位符上线
  wx.showModal({
    title: 'API 配置错误',
    content: '正式环境 BASE_URL 仍为占位符 "your-domain"，请联系开发者修改 api.js 中的 release URL。',
    showCancel: false,
  });
} else if (BASE_URL.includes('your-domain') && ENV === 'develop') {
  console.warn(
    '[tarot] 提醒：release URL 仍为占位符 "your-domain"。\n' +
    '  开发环境不受影响（已使用开发环境直连），但部署到正式环境前务必修改。'
  );
}

const MAX_RETRIES = 2;

const request = async (url, options = {}, retryCount = 0) => {
  const token = wx.getStorageSync('token');

  // AI endpoints take ~20-40s; use long timeout. Other endpoints use 15s.
  const isAiEndpoint = url.includes('/spread/') || url.includes('/chat') || url.includes('/reinterpret');
  const timeout = options.timeout || (isAiEndpoint ? 120000 : 15000);

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${url}`,
      method: options.method || 'GET',
      data: options.data,
      timeout,
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
          const err = new Error(res.data?.detail || '请求失败');
          err.statusCode = res.statusCode;
          reject(err);
        }
      },
      fail: (err) => {
        // 网络错误时自动重试，不重试 HTTP 错误（4xx/5xx 已在 success 中处理）
        if (retryCount < MAX_RETRIES) {
          const delay = Math.pow(2, retryCount) * 1000; // 指数退避: 1s, 2s
          setTimeout(() => {
            resolve(request(url, options, retryCount + 1));
          }, delay);
          return;
        }
        reject(err);
      },
    });
  });
};

/**
 * 将原始错误转为用户可理解的中文文案
 * @param {Error|{message?:string,statusCode?:number}} err
 * @returns {string} 友好的中文错误消息
 */
function getFriendlyError(err) {
  if (!err) return '连接异常，请稍后重试';
  const msg = (err.message || '').toLowerCase();
  const status = err.statusCode;

  if (status === 402) return '剩余次数不足';
  if (status === 429 || msg.includes('too many')) return '请求过于频繁，请稍后重试';
  if (status === 500 || msg.includes('500') || msg.includes('internal server')) return '服务器繁忙，请稍后重试';
  if (status === 502 || status === 503 || status === 504) return '服务暂不可用，请稍后重试';
  if (status === 404 || msg.includes('not found')) return '请求的资源不存在';
  if (status === 401 || msg.includes('unauthorized') || msg.includes('登录过期')) return '登录已过期，请重新登录';
  if (status === 403 || msg.includes('forbidden')) return '暂无访问权限';
  if (msg.includes('network') || msg.includes('timeout') || msg.includes('abort') || msg.includes('fail')) return '网络连接异常，请检查网络后重试';

  // 保留后端返回的友好中文消息，屏蔽英文/技术消息
  if (err.message && !/^[a-zA-Z]/.test(err.message)) {
    return err.message; // 中文消息直接展示
  }
  return '连接异常，请稍后重试';
}

module.exports = { request, BASE_URL, getFriendlyError };
