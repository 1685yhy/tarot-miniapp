// pages/star-report/star-report.js
// =================================================================
// 星象月报（SDD P2 · T7-5 报告页 + T7-6 海报）
//   ?tab=week|month 双 Tab；星光卷轴版式（E3 奶油疗愈，零新视觉）
//   周报五段：星运曲线 → 星尘统计 → 牌运回顾 → AI 周寄语 → 星光色带
//   月报六段：天象事件表 → 手账汇总 → TOP3 → 星尘与星阶 → 下月展望 → AI 总评
//   非会员预览态：未解锁区块毛玻璃模糊 + 锁形标记；底部吸底
//     「解锁全文 4.9/19.9」→ POST /report/{type}/unlock → utils/pay.js
//     → 成功刷新全文（仿 reading-result 402 重试回调模式）
//     「开通会员免费看」→ pages/membership/membership
//   海报：周报 → weekly-report-poster 组件；月报 → share-poster(mode=month_report)
//   数据源：GET /report/week|month；GET /report/month/poster（脱敏）
// =================================================================
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');
const analytics = require('../../utils/analytics');
const { startPay, isComingSoonError, showComingSoonModal } = require('../../utils/pay');
const { findCard } = require('../../utils/cards');

// ── 定价（与后端 PRODUCTS weekly_report 4.9 / monthly_report 19.9 对齐）──
const UNLOCK_PRICE = { week: '4.9', month: '19.9' };
const PRODUCT_ID = { week: 'weekly_report', month: 'monthly_report' };

// ── 月度天象事件「一句宜忌」（活动预告非运势预测 · 合规 2.4）──
const EVENT_GUIDANCE = {
  new_moon: '宜·许下心愿，种一颗星光',
  full_moon: '宜·复盘与释放，收一束月光',
  mercury_retrograde: '慢行的日子要来了 · 宜·回顾整理',
  solar_term: '宜·顺应节律，照顾身体',
  meteor_shower: '宜·抬头看天，许一个愿望',
  eclipse: '宜·放慢节奏，安静休息',
  opposite_sun: '宜·平衡内外，温柔待己',
};

// ── 月名（期头/海报标题用）──
const MONTH_NAMES = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月'];

// =====================================================================
//  周期工具（客户端确定性生成最近 4 期）
// =====================================================================

function _pad(n) {
  return n < 10 ? '0' + n : '' + n;
}

/** '2026-W33' → 该周周一（Date） */
function _weekKeyToMonday(key) {
  const m = String(key || '').match(/^(\d{4})-W(\d{2})$/);
  if (!m) return null;
  const y = Number(m[1]);
  const w = Number(m[2]);
  const jan4 = new Date(y, 0, 4);
  const dow = (jan4.getDay() + 6) % 7; // 周一=0
  return new Date(y, 0, 4 - dow + (w - 1) * 7);
}

/** Date → ISO 周键 '2026-W33' */
function _isoWeekKey(d) {
  const date = new Date(d.getTime());
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + 3 - ((date.getDay() + 6) % 7));
  const week1 = new Date(date.getFullYear(), 0, 4);
  const week = 1 + Math.round(((date - week1) / 86400000 - 3 + ((week1.getDay() + 6) % 7)) / 7);
  return `${date.getFullYear()}-W${_pad(week)}`;
}

function _fmtMD(d) {
  return `${d.getMonth() + 1}.${d.getDate()}`;
}

/** 周报最近 4 期：['2026-W33', ...] → [{key, label}]，label "8.3 ~ 8.9" */
function buildWeekPeriods(latestKey) {
  const list = [];
  const monday = _weekKeyToMonday(latestKey);
  if (!monday) return list;
  for (let i = 0; i < 4; i++) {
    const start = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() - i * 7);
    const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6);
    list.push({
      key: _isoWeekKey(start),
      label: `${_fmtMD(start)} ~ ${_fmtMD(end)}`,
    });
  }
  return list;
}

/** 月报最近 4 期：['2026-08', ...] → [{key, label}]，label "8月" */
function buildMonthPeriods(latestKey) {
  const list = [];
  const m = String(latestKey || '').match(/^(\d{4})-(\d{2})$/);
  if (!m) return list;
  const y = Number(m[1]);
  const mon = Number(m[2]);
  const now = new Date();
  for (let i = 0; i < 4; i++) {
    let yy = y;
    let mm = mon - i;
    if (mm <= 0) {
      mm += 12;
      yy -= 1;
    }
    list.push({
      key: `${yy}-${_pad(mm)}`,
      label: yy === now.getFullYear() ? `${mm}月` : `${yy}.${_pad(mm)}`,
    });
  }
  return list;
}

/** '2026-08' → {y, m} 或 null */
function _parseMonthPeriod(key) {
  const m = String(key || '').match(/^(\d{4})-(\d{2})$/);
  return m ? { y: Number(m[1]), m: Number(m[2]) } : null;
}

// =====================================================================
//  Page
// =====================================================================

Page({
  data: {
    tab: 'week',               // 'week' 星光一周 | 'month' 星光月度卷轴
    loading: true,
    error: null,
    report: null,              // GET /report/week|month 完整响应
    currentPeriod: '',
    periods: [],               // 最近 4 期 [{key, label}]
    locked: false,             // 非会员未解锁 → 预览态
    unlockPrice: '4.9',
    purchasing: false,
    starTierName: '',          // 期头星阶徽章（GET /tasks/status）
    isEmpty: false,            // 空态（无数据月/周）→ "夜空等着被你点亮"
    // 周报海报
    showWeeklyPoster: false,
    weeklyReportData: null,
    weeklyCardImage: '',
    // 月报封面海报
    showMonthPoster: false,
    monthPosterData: null,
    eventGuidance: EVENT_GUIDANCE,
    // 期头（设计 2.4：「你的第 N 周星光记录」/「八月的星光卷轴」）
    heroTitle: '你的星光一周',
    heroPeriod: '',
    journalBrightPct: 0, // 手账亮暗比例（WXML 不支持函数调用，JS 预计算）
    cardList: [],        // 牌运横滑列表（预计算卡图路径）
  },

  onLoad(options) {
    const tab = options && options.tab === 'month' ? 'month' : 'week';
    this.setData({
      tab,
      unlockPrice: UNLOCK_PRICE[tab],
      // 页面级分享标题（分享给朋友）
    });
    wx.setNavigationBarTitle({
      title: tab === 'month' ? '星光月度卷轴' : '星光一周',
    });
    // 期头星阶徽章（无则隐藏，绝不降级印「微光」）
    request('/tasks/status')
      .then((s) => {
        if (s && s.star_tier_name) this.setData({ starTierName: s.star_tier_name });
      })
      .catch(() => { /* 静默：徽章非关键 */ });
    this._loadReport(null);
  },

  onShow() {
    // 从会员页返回（新开通会员）→ 锁态静默刷新为全文
    if (this._firstShown !== false && this.data.report && this.data.locked) {
      this._loadReport(this.data.currentPeriod, { silent: true });
    }
    this._firstShown = false;
  },

  /* ---------------------------------------------------------------
     数据加载（period 缺省 = 后端默认上一完整周期）
     --------------------------------------------------------------- */
  async _loadReport(period, opts = {}) {
    const tab = this.data.tab;
    if (!opts.silent) this.setData({ loading: true, error: null });
    try {
      const url = period ? `/report/${tab}?period=${period}` : `/report/${tab}`;
      const res = await request(url);
      const report = res || {};
      const periods = tab === 'week'
        ? buildWeekPeriods(report.period)
        : buildMonthPeriods(report.period);
      const body = report.report || {};
      // 空态判定：周（曲线全空+星尘0+解读0）/ 月（解读0+手账无+星尘0）
      let isEmpty = false;
      if (tab === 'week') {
        const curve = (body.curve || []).filter((p) => p && p.total != null);
        const sd = body.stardust || {};
        const cards = body.cards || {};
        isEmpty = curve.length === 0 && (sd.total || 0) === 0 && (cards.readings_count || 0) === 0;
      } else if (report.locked) {
        // 锁定预览只下发 {astral_events, note} → 空态仅依据可见字段判定
        isEmpty = ((body.astral_events) || []).length === 0;
      } else {
        const cards = body.cards || {};
        const j = body.journal;
        const sd = body.stardust || {};
        isEmpty = (cards.readings_count || 0) === 0 && (!j || !j.active_days) && (sd.estimated || 0) === 0;
      }
      const journal = body.journal || {};
      const cardList = ((body.cards && body.cards.card_list) || []).map((c) => {
        const found = c && c.name ? findCard(c.name) : null;
        return { ...(c || {}), image: found && found.image ? found.image : '' };
      });
      this.setData({
        report,
        currentPeriod: report.period || period || '',
        periods,
        locked: !!report.locked,
        isEmpty,
        loading: false,
        error: null,
        journalBrightPct: journal.bright_ratio != null ? Math.round(journal.bright_ratio * 100) : 0,
        cardList,
        ...this._buildHero(tab, report, periods),
      });
      // 支付回调尚未到账（解锁后仍 locked）→ 短暂等待后重试（仿 reading-result 402 模式）
      if (report.locked && opts.afterUnlock && (opts.retries || 0) > 0) {
        const expectPeriod = report.period || period || '';
        const tab = this.data.tab;
        setTimeout(() => {
          // 重试窗口内可能已切 Tab / 换期 → 放弃重试，避免用旧 period 请求新 tab（422 覆盖错误态）
          if (this.data.tab !== tab || this.data.currentPeriod !== expectPeriod || this.data.loading) return;
          this._loadReport(period, { afterUnlock: true, retries: (opts.retries || 0) - 1 });
        }, 1500);
      }
    } catch (err) {
      if (opts.silent) return; // 静默刷新失败不打扰
      this.setData({ loading: false, error: getFriendlyError(err) });
    }
  },

  /* ---------------------------------------------------------------
     期头文案（设计 2.4）：周报「你的第 N 周星光记录」/ 月报「八月的星光卷轴」
     --------------------------------------------------------------- */
  _buildHero(tab, report, periods) {
    const period = (report && report.period) || '';
    if (tab === 'week') {
      const wm = String(period).match(/^(\d{4})-W(\d{2})$/);
      const weekNum = wm ? Number(wm[2]) : 0;
      const cur = (periods || []).find((p) => p.key === period);
      return {
        heroTitle: '你的星光一周',
        heroPeriod: weekNum ? `第 ${weekNum} 周星光记录 · ${cur ? cur.label : ''}` : (cur ? cur.label : ''),
      };
    }
    const pm = _parseMonthPeriod(period);
    return {
      heroTitle: '星光月度卷轴',
      heroPeriod: pm
        ? `${pm.y}年${pm.m}月 · ${MONTH_NAMES[pm.m - 1] || `${pm.m}月`}的星光卷轴`
        : '',
    };
  },

  /* ---------------------------------------------------------------
     Tab 切换（周报 / 月报）
     --------------------------------------------------------------- */
  onSwitchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.tab) return;
    this.setData({
      tab,
      report: null,
      locked: false,
      currentPeriod: '',
      periods: [],
      loading: true,
      error: null,
      isEmpty: false,
      showWeeklyPoster: false,
      showMonthPoster: false,
      unlockPrice: UNLOCK_PRICE[tab],
      heroTitle: tab === 'month' ? '星光月度卷轴' : '你的星光一周',
      heroPeriod: '',
    });
    wx.setNavigationBarTitle({
      title: tab === 'month' ? '星光月度卷轴' : '星光一周',
    });
    this._loadReport(null);
  },

  /* ---------------------------------------------------------------
     报告期切换（最近 4 期）
     --------------------------------------------------------------- */
  onSwitchPeriod(e) {
    const key = e.currentTarget.dataset.key;
    if (!key || key === this.data.currentPeriod) return;
    this._loadReport(key);
  },

  onRetry() {
    this._loadReport(this.data.currentPeriod || null);
  },

  /* ---------------------------------------------------------------
     非会员解锁（POST /report/{type}/unlock → utils/pay.js）
     --------------------------------------------------------------- */
  async onUnlock() {
    if (this.data.purchasing) return;
    const type = this.data.tab;
    const product = {
      id: PRODUCT_ID[type],
      price: Number(UNLOCK_PRICE[type]),
    };

    try {
      await checkLogin();
    } catch (err) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }

    analytics.trackPurchaseStart(product);
    this.setData({ purchasing: true });
    wx.showLoading({ title: '创建订单...', mask: true });
    try {
      const order = await request(`/report/${type}/unlock`, { method: 'POST' });
      wx.hideLoading();

      startPay(order, {
        product,
        success: () => {
          analytics.trackPurchaseComplete(product, product.price);
          this.setData({ purchasing: false });
          wx.showToast({ title: '解锁成功 ✦', icon: 'success' });
          // 支付回调可能比支付成功晚 1-2 秒到账 → 解锁后重试 3 次（仿 reading-result 402 模式）
          this._loadReport(this.data.currentPeriod, { afterUnlock: true, retries: 3 });
        },
        fail: (err) => {
          this.setData({ purchasing: false });
          if (err.reason === 'user_cancel') {
            wx.showToast({ title: '支付已取消', icon: 'none' });
          } else if (err.reason === 'coming_soon') {
            showComingSoonModal();
          } else {
            wx.showToast({ title: err.message || '支付失败，请重试', icon: 'none' });
          }
        },
      });
    } catch (err) {
      this.setData({ purchasing: false });
      wx.hideLoading();
      if (isComingSoonError(err)) {
        showComingSoonModal();
        return;
      }
      wx.showToast({ title: getFriendlyError(err) || '下单失败', icon: 'none' });
    }
  },

  /* 开通会员免费看 → 会员页 */
  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  /* ---------------------------------------------------------------
     生成海报（周报 → weekly-report-poster；月报 → month-report-poster）
     --------------------------------------------------------------- */
  onGenPoster() {
    if (this.data.locked) {
      wx.showToast({ title: '解锁后可生成海报 ✦', icon: 'none' });
      return;
    }
    if (!this.data.report) return;
    if (this.data.tab === 'week') this._openWeekPoster();
    else this._openMonthPoster();
  },

  _openWeekPoster() {
    const r = this.data.report;
    const cards = (r.report && r.report.cards) || {};
    let cardImage = '';
    if (cards.most_card && cards.most_card.name) {
      const found = findCard(cards.most_card.name);
      cardImage = found && found.image ? found.image : '';
    }
    this.setData({
      weeklyReportData: r.report,
      weeklyCardImage: cardImage,
      showWeeklyPoster: true,
    });
  },

  async _openMonthPoster() {
    wx.showLoading({ title: '生成海报中...', mask: true });
    try {
      const data = await request(`/report/month/poster?period=${this.data.currentPeriod}`);
      wx.hideLoading();
      if (!data || !data.period) {
        wx.showToast({ title: '先看报告，再分享星光 ✦', icon: 'none' });
        return;
      }
      // 海报标题前缀（「八月 · 星光月度卷轴」）；跨年月份带年份
      const pm = _parseMonthPeriod(data.period);
      const nowYear = new Date().getFullYear();
      const monthLabel = pm
        ? (pm.y === nowYear ? MONTH_NAMES[pm.m - 1] || `${pm.m}月` : `${pm.y}年${MONTH_NAMES[pm.m - 1] || `${pm.m}月`}`)
        : '';
      this.setData({ monthPosterData: { ...data, periodLabel: monthLabel }, showMonthPoster: true });
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: getFriendlyError(err) || '海报生成失败', icon: 'none' });
    }
  },

  onCloseWeeklyPoster() {
    this.setData({ showWeeklyPoster: false });
  },

  /** 分享周报海报：打点（POST /share/track share_type="week_report"） */
  onShareWeeklyPoster(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'week_report');
    request('/share/track', {
      method: 'POST',
      data: { channel: 'wechat_friend', share_type: 'week_report', ref_id: this.data.currentPeriod || '' },
    }).catch(() => { /* 打点失败静默 */ });
    if (wx.showShareImageMenu) {
      wx.showShareImageMenu({ path: imagePath, fail: () => {} });
    } else {
      wx.showToast({ title: '请先保存海报，再从相册分享', icon: 'none', duration: 2000 });
    }
  },

  onCloseMonthPoster() {
    this.setData({ showMonthPoster: false, monthPosterData: null });
  },

  /** 分享月报封面海报：打点（share_type="month_report"） */
  onShareMonthPoster(e) {
    const imagePath = e.detail && e.detail.imagePath;
    if (!imagePath) return;
    analytics.trackShare('wechat_friend', 'month_report');
    request('/share/track', {
      method: 'POST',
      data: { channel: 'wechat_friend', share_type: 'month_report', ref_id: this.data.currentPeriod || '' },
    }).catch(() => { /* 打点失败静默 */ });
    if (wx.showShareImageMenu) {
      wx.showShareImageMenu({ path: imagePath, fail: () => {} });
    } else {
      wx.showToast({ title: '请先保存海报，再从相册分享', icon: 'none', duration: 2000 });
    }
  },

  /* ---------------------------------------------------------------
     分享给朋友（页面级）
     --------------------------------------------------------------- */
  onShareAppMessage() {
    const tab = this.data.tab;
    const period = this.data.currentPeriod || '';
    if (tab === 'month') {
      const pm = _parseMonthPeriod(period);
      const monthLabel = pm ? MONTH_NAMES[pm.m - 1] || `${pm.m}月` : '本月';
      // 分享文案（设计 2.4）："我的八月星象月报 · 本月点亮 N 颗星 ✦"
      const body = this.data.report && this.data.report.report;
      const activeDays = (body && body.journal && body.journal.active_days) || 0;
      return {
        title: activeDays > 0
          ? `我的${monthLabel}星象月报 · 本月点亮 ${activeDays} 颗星 ✦`
          : `我的${monthLabel}星象月报 ✦`,
        path: `/pages/star-report/star-report?tab=month`,
      };
    }
    return {
      title: '我的星光一周 · 星象周报 ✦',
      path: '/pages/star-report/star-report?tab=week',
    };
  },
});
