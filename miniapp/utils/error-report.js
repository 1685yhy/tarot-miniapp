/**
 * 前端错误静默上报 —— 与后端 POST /monitor/error 配合
 * =====================================================
 *
 * 用途：App.onError / App.onUnhandledRejection 捕获的 JS 异常，
 *       以 metric='js_error' 落库到后端 performance_events 表。
 *
 * 原则：
 *   - 静默：上报失败 / BASE_URL 未配置 / 参数异常时一律不打扰用户、不抛出
 *   - 限长：message/stack 截断后上报，避免超长 payload
 *   - 懒加载：require('./api') 在函数内部引入，避免循环依赖
 *
 * 用法：
 *   const errorReport = require('./utils/error-report');
 *   errorReport.reportError(err);              // err 可以是 Error / string / {message, stack}
 *   errorReport.reportError('加载失败', '', 'pages/index/index');
 */

function _extract(err) {
  // 归一化各种异常形态为 { message, stack }
  if (err === null || err === undefined) return { message: 'unknown error', stack: '' };
  if (typeof err === 'string') return { message: err, stack: '' };
  if (err instanceof Error) {
    return { message: err.message || String(err), stack: err.stack || '' };
  }
  if (typeof err === 'object') {
    return {
      message: err.message !== undefined ? String(err.message) : String(err),
      stack: err.stack !== undefined ? String(err.stack) : '',
    };
  }
  return { message: String(err), stack: '' };
}

/** 当前页面路由（如 pages/index/index），供错误归属定位 */
function currentPage() {
  try {
    const pages = getCurrentPages();
    const top = pages[pages.length - 1];
    return top && top.route ? top.route : '';
  } catch (e) {
    return '';
  }
}

/**
 * 静默上报前端错误。
 * @param {Error|string|object} err - 错误对象 / 错误信息
 * @param {string} [stack] - 覆盖的堆栈（不传则从 err 中提取）
 * @param {string} [page] - 页面路径（不传则取当前页面）
 */
function reportError(err, stack, page) {
  try {
    const detail = _extract(err);
    const finalStack = stack || detail.stack || '';
    const finalPage = page || currentPage();

    // 后端 BASE_URL 未配置（占位符）时不发请求，仅在控制台提示
    const { BASE_URL } = require('./api');
    if (!BASE_URL || BASE_URL.includes('your-domain') || BASE_URL.includes('example.com')) {
      console.warn('[error-report] BASE_URL 未配置，跳过上报:', detail.message);
      return;
    }

    wx.request({
      url: `${BASE_URL}/monitor/error`,
      method: 'POST',
      data: {
        message: String(detail.message).slice(0, 2000),
        stack: String(finalStack).slice(0, 8000),
        page: String(finalPage).slice(0, 255),
        platform: 'wechat',
        ts: Date.now(),
      },
      timeout: 10000,
      fail: () => {
        // 静默：上报失败不影响业务
      },
    });
  } catch (e) {
    // 兜底：reportError 自身绝不允许抛出
  }
}

module.exports = {
  reportError,
  currentPage,
};
