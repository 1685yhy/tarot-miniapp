/**
 * Performance monitoring utility for Starlight Tarot miniapp
 * Tracks key metrics: app launch, first page ready, and reports via lifecycle hooks.
 *
 * Usage:
 *   const perf = require('../../utils/performance');
 *   perf.mark('appLaunch');        // in App.onLaunch
 *   perf.mark('firstPageReady');   // in Page.onReady of first page
 *   perf.report();                 // upload to monitoring endpoint
 */

const perf = {
  appLaunch: 0,
  firstPageReady: 0,
  pageReady: {},
};

/**
 * Mark a performance timestamp.
 * @param {string} name - Metric name (e.g. 'appLaunch', 'firstPageReady')
 */
function mark(name) {
  if (typeof name !== 'string') return;
  if (perf[name] && perf[name] > 0) return; // first mark wins
  perf[name] = Date.now();
}

/**
 * Mark a specific page's onReady timestamp.
 * @param {string} pageName - Page route or identifier
 */
function markPageReady(pageName) {
  if (typeof pageName !== 'string') return;
  if (perf.pageReady[pageName]) return; // first ready wins
  perf.pageReady[pageName] = Date.now();
}

/**
 * Compute durations relative to appLaunch.
 * Returns { metric, durationMs } objects.
 */
function computeDurations() {
  if (!perf.appLaunch) return [];
  const launch = perf.appLaunch;
  const durations = [];

  if (perf.firstPageReady > 0) {
    durations.push({
      metric: 'firstPageReady',
      durationMs: perf.firstPageReady - launch,
    });
  }

  Object.keys(perf.pageReady).forEach((page) => {
    durations.push({
      metric: `pageReady:${page}`,
      durationMs: perf.pageReady[page] - launch,
    });
  });

  return durations;
}

/**
 * Report performance metrics to the monitoring endpoint.
 * Fire-and-forget — does not block the main thread.
 * Falls back to console.warn if endpoint is unreachable.
 */
function report() {
  const durations = computeDurations();
  if (durations.length === 0) return;

  // Also log to console in debug mode for local inspection
  const { BASE_URL } = require('./api');
  if (!BASE_URL || BASE_URL.includes('your-domain') || BASE_URL.includes('example.com')) {
    console.log('[perf]', JSON.stringify(durations));
    return;
  }

  wx.request({
    url: `${BASE_URL}/performance`,
    method: 'POST',
    data: {
      metrics: durations,
      platform: 'wechat',
      timestamp: Date.now(),
      sdk: wx.getAccountInfoSync ? wx.getAccountInfoSync().miniProgram.envVersion : 'unknown',
    },
    fail: () => {
      // Silent degrade
    },
  });
}

/**
 * Get a human-readable summary of key metrics.
 * Used for debugging / development console output.
 */
function summary() {
  const durations = computeDurations();
  if (durations.length === 0) return 'No performance data collected yet.';
  return durations.map((d) => `${d.metric}: ${d.durationMs}ms`).join('\n');
}

module.exports = {
  perf,
  mark,
  markPageReady,
  report,
  summary,
};
