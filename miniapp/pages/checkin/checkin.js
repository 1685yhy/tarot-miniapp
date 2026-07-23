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
    // Particle animation
    particles: [],
  },

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
      this.setData({
        checkedIn: status.checked_in_today,
        streak: status.streak,
        level: lv,
        nextLevelName: status.level.next_level,
        daysNeeded: status.level.days_needed,
      });
      // Load checkin history for the week
      await this._loadWeekHistory();
    } catch (err) {
      console.error('[checkin] 获取状态失败', err);
    }
  },

  async _loadWeekHistory() {
    // Get all checkins for this week range from the backend
    // Since we don't have a dedicated endpoint, we leverage the fact
    // that the streak info tells us consecutive days, and we build
    // the week display from local logic
    try {
      // We'll do a simple approach: mark today and consecutive past days
      const streak = this.data.streak;
      const weekDates = this.data.weekDates;
      const today = new Date();
      const todayStr = weekDates.find(d => d.isToday)?.date;

      // For a more accurate history, we check which dates in the week are checked in
      // Based on streak, we know the user has checked in for `streak` consecutive days ending today
      const history = [];
      for (const d of weekDates) {
        const dateObj = new Date(d.date);
        const diffDays = Math.round((today - dateObj) / (24 * 60 * 60 * 1000));
        if (diffDays >= 0 && diffDays < streak) {
          history.push(d.date);
        }
      }
      this.setData({ checkinHistory: history });
    } catch (err) {
      console.error('[checkin] 获取历史失败', err);
    }
  },

  async onCheckIn() {
    if (this.data.checkedIn) return;

    wx.showLoading({ title: '签到中...' });
    try {
      const result = await request('/tasks/checkin', { method: 'POST' });
      this.setData({
        checkedIn: result.signed_in,
        streak: result.streak,
      });

      // Show reward animation
      this._showRewardAnim(result.reward);

      // Reload level info
      const lv = resolveLevel(result.streak);
      this.setData({ level: lv, daysNeeded: Math.max(0, lv.max + 1 - result.streak) });

      // Reload week history
      await this._loadWeekHistory();

      wx.hideLoading();
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: '签到失败，请重试', icon: 'none' });
    }
  },

  _showRewardAnim(rewardText) {
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
      particles,
    });

    // Auto-hide after 2.5s
    setTimeout(() => {
      this.setData({ showRewardAnim: false });
    }, 2500);
  },

  onRetry() {
    this.setData({ pageError: null, loading: true });
    this.onLoad();
  },
});
