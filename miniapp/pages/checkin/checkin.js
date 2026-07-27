// pages/checkin/checkin.js
const { request, getFriendlyError } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

// ── Level definitions (mirrors backend) ──
const LEVELS = [
  { name: '星光旅人', min: 0, max: 6, badgeColor: '#9A95B8', desc: '开始你的星光之旅' },
  { name: '星辰学徒', min: 7, max: 29, badgeColor: '#B8A9E0', desc: '星辰之路，日渐精进' },
  { name: '月光智者', min: 30, max: 99, badgeColor: '#F4D48C', desc: '智慧如月，普照人心' },
  { name: '银河导师', min: 100, max: 999999, badgeColor: '#FFD700', desc: '银河导师，星光照耀' },
];

function resolveLevel(streak) {
  for (const lv of LEVELS) {
    if (lv.min <= streak && streak <= lv.max) return lv;
  }
  return LEVELS[0];
}

function getWeekDates() {
  const today = new Date();
  const dayOfWeek = today.getDay(); // 0=Sun
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
  const dates = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + mondayOffset + i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    dates.push({
      date: `${y}-${m}-${day}`,
      dayLabel: ['日', '一', '二', '三', '四', '五', '六'][d.getDay()],
      dayNum: d.getDate(),
      isToday: d.toDateString() === today.toDateString(),
    });
  }
  return dates;
}

Page({
  data: {
    loading: true,
    pageError: null,
    checkedIn: false,
    streak: 0,
    checkingIn: false, // guard for rapid double-tap
    reward: '',
    // Week calendar
    weekDates: getWeekDates(),
    checkinHistory: [], // array of date strings user has checked in
    // Level
    level: null,
    nextLevelName: '',
    daysNeeded: 0,
    // Reward animation
    showRewardAnim: false,
    rewardText: '',
    rewardEmoji: '🌟',
    // Membership milestones
    milestones: [
      { days: 7, reward: 1, claimed: false },
      { days: 30, reward: 3, claimed: false },
      { days: 100, reward: 7, claimed: false },
    ],
    // Particle animation
    particles: [],
  },

  _timers: [],

  async onLoad() {
    try {
      await checkLogin();
      await this._loadStatus();
    } catch (err) {
      console.error('[checkin] 加载失败', err);
      this.setData({ pageError: getFriendlyError(err) || '加载失败' });
    } finally {
      this.setData({ loading: false });
    }
  },

  async onShow() {
    // Refresh status when returning from background (e.g. after being sent to mini-program settings)
    // Skip if still initial loading or if already checked in (no need to re-fetch)
    if (!this.data.loading && !this.data.pageError) {
      await this._loadStatus();
    }
  },

  async _loadStatus() {
    try {
      const status = await request('/tasks/status');
      const lv = resolveLevel(status.streak);
      // Guard: API must return level info for next_level / days_needed
      const nextLevelName = (status.level && status.level.next_level) || '';
      const daysNeeded = (status.level && status.level.days_needed) || 0;
      this.setData({
        checkedIn: status.checked_in_today,
        streak: status.streak,
        level: lv,
        nextLevelName,
        daysNeeded,
      });
      // Load checkin history for the week
      await this._loadWeekHistory();
    } catch (err) {
      console.error('[checkin] 获取状态失败', err);
    }
  },

  async _loadWeekHistory() {
    // 注意：这是基于 streak 的客户端近似，而非真实的每日签到历史。
    // streak 表示「连续签到天数截至今天」，因此我们标记今天及之前 (streak-1) 天。
    // 仅标记落在当前周范围内的日期。
    // 如需精确的每日历史，应由后端提供专用接口返回完整签到记录。
    try {
      const streak = this.data.streak;
      const weekDates = this.data.weekDates;
      const today = new Date();
      const history = [];

      // 标记今天及之前 (streak-1) 个连续日
      for (let i = 0; i < streak; i++) {
        const d = new Date(today);
        d.setDate(today.getDate() - i);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const dateStr = `${y}-${m}-${day}`;
        // 仅当该日期落在当前周范围内才标记
        if (weekDates.some(wd => wd.date === dateStr)) {
          history.push(dateStr);
        }
      }

      this.setData({ checkinHistory: history });
    } catch (err) {
      console.error('[checkin] 获取历史失败', err);
    }
  },

  async onCheckIn() {
    if (this.data.checkedIn || this.data.checkingIn) return;
    this.setData({ checkingIn: true });

    wx.showLoading({ title: '签到中...' });
    try {
      const result = await request('/tasks/checkin', { method: 'POST' });
      this.setData({
        checkedIn: result.signed_in,
        streak: result.streak,
        checkingIn: false,
      });

      // Show reward animation (with membership celebration if applicable)
      if (result.reward_type === 'membership') {
        const msg = `🎉 连续签到${result.streak}天！获得${result.reward_days}天会员体验 ✦`;
        this._showRewardAnim(msg, 'membership');
      } else {
        this._showRewardAnim(result.reward);
      }

      // Reload level info
      const lv = resolveLevel(result.streak);
      this.setData({ level: lv, daysNeeded: Math.max(0, lv.max + 1 - result.streak) });

      // Reload week history
      await this._loadWeekHistory();

      wx.hideLoading();
    } catch (err) {
      this.setData({ checkingIn: false });
      wx.hideLoading();
      wx.showToast({ title: '签到失败，请重试', icon: 'none' });
    }
  },

  _showRewardAnim(rewardText, rewardType) {
    // Determine emoji based on reward type
    const rewardEmoji = rewardType === 'membership' ? '👑' : '🌟';

    // Generate golden particles
    const particles = [];
    for (let i = 0; i < 12; i++) {
      particles.push({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 0.5,
        size: 6 + Math.random() * 10,
      });
    }
    this.setData({
      showRewardAnim: true,
      rewardText,
      rewardEmoji,
      particles,
    });

    // Auto-hide after 2.5s (tracked for cleanup on page unload)
    this._timers.push(setTimeout(() => {
      this.setData({ showRewardAnim: false });
    }, 2500));
  },

  onUnload() {
    this._clearTimers();
  },

  onHide() {
    this._clearTimers();
  },

  _clearTimers() {
    this._timers.forEach(t => clearTimeout(t));
    this._timers = [];
  },

  onRetry() {
    this.setData({ pageError: null, loading: true });
    this.onLoad();
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
