// pages/birth-info/birth-info.js
// 出生信息（可选）：日期自动推导星座 → 存入 storage 'birth_info' + 上报服务端
// 二期接入月亮/上升真实星盘计算；数据仅用于星座计算，绝不外传
const { ZODIACS, ZODIAC_BY_KEY, zodiacFromDate } = require('../../utils/energy');
const { request } = require('../../utils/api');
const analytics = require('../../utils/analytics');

const BIRTH_KEY = 'birth_info';
const MONTH_DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

Page({
  data: {
    editing: true,          // false → 已填摘要
    saved: null,            // { date, time, city, zodiac }
    year: '1996',
    month: 8,
    day: 8,
    time: '',
    city: '',
    years: [],              // picker 范围 ['1940年' ... '2026年']
    months: [],
    days: [],
    yearIndex: 0,
    monthIndex: 0,
    dayIndex: 0,
    derived: null,          // 当前日期推导出的星座 {emoji, name}
    derivedKey: '',
  },

  onLoad() {
    // 读取已保存数据（如有）
    let saved = null;
    try { saved = wx.getStorageSync(BIRTH_KEY) || null; } catch (e) { /* silent */ }
    const years = [];
    for (let y = 2026; y >= 1940; y--) years.push(`${y}年`);
    const months = [];
    for (let m = 1; m <= 12; m++) months.push(`${m}月`);
    const days = [];
    for (let d = 1; d <= 31; d++) days.push(`${d}日`);

    let year = 1996, month = 8, day = 8;
    if (saved && saved.date) {
      const parts = String(saved.date).split('-');
      year = parseInt(parts[0], 10) || 1996;
      month = parseInt(parts[1], 10) || 8;
      day = parseInt(parts[2], 10) || 8;
    }

    this.setData({
      saved,
      editing: !saved,
      years, months, days,
      year, month, day,
      time: saved ? (saved.time || '') : '',
      city: saved ? (saved.city || '') : '',
      yearIndex: Math.max(0, 2026 - year),
      monthIndex: month - 1,
      dayIndex: day - 1,
    });
    this._syncDays();
    this._updateDerived();
    analytics.trackEvent('birth_info_open', {});
  },

  _syncDays() {
    const maxDay = MONTH_DAYS[this.data.month - 1];
    const days = [];
    for (let d = 1; d <= maxDay; d++) days.push(`${d}日`);
    let dayIndex = this.data.dayIndex;
    if (dayIndex >= maxDay) dayIndex = maxDay - 1;
    this.setData({ days, dayIndex });
  },

  _updateDerived() {
    const key = zodiacFromDate(this.data.month, this.data.day);
    const z = ZODIAC_BY_KEY[key];
    this.setData({ derived: z, derivedKey: key });
  },

  onYearChange(e) {
    const yearIndex = Number(e.detail.value);
    const year = 2026 - yearIndex;
    this.setData({ year, yearIndex });
  },

  onMonthChange(e) {
    const month = Number(e.detail.value) + 1;
    this.setData({ month, monthIndex: Number(e.detail.value) });
    this._syncDays();
    this._updateDerived();
  },

  onDayChange(e) {
    this.setData({ dayIndex: Number(e.detail.value) });
    this._syncDays();
    this._updateDerived();
  },

  onTimeInput(e) {
    this.setData({ time: e.detail.value });
  },

  onCityInput(e) {
    this.setData({ city: e.detail.value });
  },

  onSave() {
    const { year, month, day, time, city, derived, derivedKey } = this.data;
    const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const birth = { date, time: String(time).trim(), city: String(city).trim(), zodiac: derivedKey };
    wx.setStorageSync(BIRTH_KEY, birth);

    // 上报出生信息到服务端（POST /user/birth · 失败不阻塞保存）
    request('/user/birth', {
      method: 'POST',
      data: { birth_date: date, birth_time: birth.time || null, birth_city: birth.city || null },
    }).catch(() => {
      // 静默：不上报不阻塞页面（星盘二期前仅本地使用）
    });

    // 未设置星座时，用出生日期自动补上
    let zodiacSign = '';
    try { zodiacSign = wx.getStorageSync('zodiac_sign') || ''; } catch (e) { /* silent */ }
    if (!zodiacSign && derived) {
      wx.setStorageSync('zodiac_sign', derived.name);
      wx.setStorageSync('zodiac_onboarding_done', true);
      wx.setStorageSync('onboarding_completed', true);
      wx.showToast({ title: `星盘已保存 · 已为你记下${derived.name} ✦`, icon: 'none', duration: 2200 });
    } else {
      wx.showToast({ title: '星盘已保存 · 月亮与上升将在二期点亮 ✦', icon: 'none', duration: 2200 });
    }
    analytics.trackEvent('birth_info_saved', { zodiac: derivedKey });
    this.setData({ saved: birth, editing: false });
  },

  onEdit() {
    this.setData({ editing: true });
  },

  /** 已填摘要：日期格式化（1996年08月08日） */
  fmtDate(dateStr) {
    if (!dateStr) return '';
    const parts = String(dateStr).split('-');
    if (parts.length !== 3) return dateStr;
    return `${parts[0]}年${parts[1]}月${parts[2]}日`;
  },

  zodiacName(key) {
    const z = ZODIAC_BY_KEY[key];
    return z ? `${z.emoji} ${z.name}` : '';
  },
});
