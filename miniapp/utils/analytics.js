// WeChat analytics wrapper
//
// Two channels:
//   1. Local: wx.reportAnalytics — WeChat MP console (no-op for unconfigured events)
//   2. Server: fire-and-forget POST to /api/performance (backend monitor endpoint)
//
// Server events never block the UI and degrade silently on failure.

const analytics = {
  // Track page view
  pageView(pageName) {
    wx.reportAnalytics('page_view', { page: pageName, timestamp: Date.now() });
  },
  // Track button/CTA clicks
  trackEvent(eventName, data = {}) {
    wx.reportAnalytics(eventName, { ...data, timestamp: Date.now() });
  },
  // Track conversion funnel
  funnel(step, data = {}) {
    wx.reportAnalytics('conversion_funnel', { step, ...data, timestamp: Date.now() });
  },

  /**
   * Core event sink: local WeChat analytics + fire-and-forget POST to
   * the backend monitoring endpoint. Never blocks the UI.
   * @param {string} eventType - analytics event name
   * @param {object} data - event payload
   * @private
   */
  _track(eventType, data = {}) {
    // Local WeChat analytics (safe no-op if event is not pre-configured)
    try {
      wx.reportAnalytics(eventType, { ...data, timestamp: Date.now() });
    } catch (_e) { /* silent */ }

    // Server-side: fire-and-forget — must never affect UX
    try {
      const { BASE_URL } = require('./api');
      if (!BASE_URL || BASE_URL.includes('your-domain') || BASE_URL.includes('example.com')) {
        console.log('[analytics]', eventType, JSON.stringify(data));
        return;
      }
      wx.request({
        url: `${BASE_URL}/performance`,
        method: 'POST',
        data: {
          page: 'analytics',
          metric: eventType,
          event_type: eventType,
          ...data,
          timestamp: Date.now(),
          platform: 'wechat',
        },
        fail: () => { /* silent degrade — analytics must never break UX */ },
      });
    } catch (_e) { /* silent */ }
  },

  /** App launch — records launch source (scene + query params) */
  trackAppLaunch(options) {
    const opt = options || {};
    const query = opt.query || {};
    const queryStr = (query && typeof query === 'object')
      ? JSON.stringify(query).slice(0, 500)
      : String(query || '');
    this._track('app_launch', {
      scene: opt.scene != null ? String(opt.scene) : '',
      path: opt.path || '',
      query: queryStr,
    });
  },

  /** Daily card draw */
  trackDailyDraw() {
    this._track('daily_draw', {});
  },

  /** Completed reading */
  trackReadingComplete(spreadType) {
    this._track('reading_complete', { spread_type: spreadType || 'unknown' });
  },

  /** Share behavior */
  trackShare(channel, type) {
    this._track('share', { channel: channel || 'unknown', share_type: type || 'unknown' });
  },

  /** Free trial start */
  trackTrialStart() {
    this._track('trial_start', {});
  },

  /** Purchase intent */
  trackPurchaseStart(product, extra = {}) {
    this._track('purchase_start', {
      product: (product && product.id) || (typeof product === 'string' ? product : 'unknown'),
      ...extra,
    });
  },

  /** Completed purchase */
  trackPurchaseComplete(product, amount, extra = {}) {
    const productId = (product && product.id) || (typeof product === 'string' ? product : 'unknown');
    const price = typeof amount === 'number' ? amount : ((product && product.price) || 0);
    this._track('purchase_complete', { product: productId, amount: price, ...extra });
  },

  /** Paywall impression */
  trackPaywallView(source) {
    this._track('paywall_view', { source: source || 'unknown' });
  },

  /** Paywall CTA clicked — user tapped the unlock/subscribe button */
  trackPaywallClick(source) {
    this._track('paywall_click', { source: source || 'unknown' });
  },

  /** Purchase attempt failed — reason: user_cancel | payment_failed | payment_not_configured | invalid_payment_params | order_failed */
  trackPurchaseFail(product, reason) {
    this._track('purchase_fail', {
      product: (product && product.id) || (typeof product === 'string' ? product : 'unknown'),
      reason: reason || 'unknown',
    });
  },

  /** Trial period ended without conversion */
  trackTrialExpire() {
    this._track('trial_expire', {});
  },
};

module.exports = analytics;
