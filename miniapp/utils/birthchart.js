/**
 * utils/birthchart.js — 本命星盘三要素数据层（开发 05）
 *
 * 数据源：
 *   GET /user/birthchart          → { birth, sun, moon, rising, missing, message }
 *   POST /user/birthchart/report  → 深度报告（会员免费 / birthchart_report 19.9 解锁）
 *
 * 三要素角色元信息（☀ 太阳 / ☽ 月亮 / ✦ 上升），与原型页 05/06 一致。
 * 缺失提示：missing=['birth_date'] → 去出生信息页；missing=['birth_time'] → 补时间解锁上升。
 */
const { request } = require('./api');

const CHART_CACHE_KEY = 'birthchart_data';

/** 三要素角色元信息 */
const ROLES = {
  sun: { role: 'sun', icon: '☀', roleName: '太阳', label: '核心动力' },
  moon: { role: 'moon', icon: '☽', roleName: '月亮', label: '情绪底色' },
  rising: { role: 'rising', icon: '✦', roleName: '上升', label: '他人眼中的我' },
};

/** 星座 key → { name, emoji }（与 utils/energy.js ZODIACS 一致） */
const ZODIAC_BY_KEY = {
  aries: { name: '白羊座', emoji: '♈' },
  taurus: { name: '金牛座', emoji: '♉' },
  gemini: { name: '双子座', emoji: '♊' },
  cancer: { name: '巨蟹座', emoji: '♋' },
  leo: { name: '狮子座', emoji: '♌' },
  virgo: { name: '处女座', emoji: '♍' },
  libra: { name: '天秤座', emoji: '♎' },
  scorpio: { name: '天蝎座', emoji: '♏' },
  sagittarius: { name: '射手座', emoji: '♐' },
  capricorn: { name: '摩羯座', emoji: '♑' },
  aquarius: { name: '水瓶座', emoji: '♒' },
  pisces: { name: '双鱼座', emoji: '♓' },
};

let _memCache = null; // { fingerprint, data }

function _fingerprintOf(chart) {
  const b = (chart && chart.birth) || {};
  return `${b.date || ''}|${b.time || ''}|${b.city || ''}`;
}

/**
 * 拉取三要素（登录后走 API；失败/未登录回退本地缓存，永不 reject）。
 * 内存 + storage 双缓存；同一出生信息指纹内复用。
 * @param {{force?: boolean}} opts
 * @returns {Promise<Object>} 归一化 chart（无数据时返回 null 骨架）
 */
async function fetchBirthchart(opts = {}) {
  const fpLocal = _localBirthFingerprint();
  if (!opts.force && _memCache && _memCache.fingerprint === fpLocal) {
    return _memCache.data;
  }

  let data = null;
  try {
    if (wx.getStorageSync('token')) {
      const api = await request('/user/birthchart');
      if (api && api.birth) {
        data = normalizeChart(api);
        try { wx.setStorageSync(CHART_CACHE_KEY, data); } catch (e) { /* silent */ }
      }
    }
  } catch (err) {
    // 未登录 / 网络失败 → 本地缓存
    console.warn('[birthchart] /user/birthchart 请求失败，走本地缓存:', err && err.message);
  }

  if (!data) {
    try {
      const cached = wx.getStorageSync(CHART_CACHE_KEY);
      if (cached && cached.birth && _fingerprintOf(cached) === fpLocal) {
        data = cached;
      }
    } catch (e) { /* silent */ }
  }

  _memCache = { fingerprint: fpLocal, data: data || emptyChart() };
  return _memCache.data;
}

/** 本地 birth_info storage 指纹（出生信息未保存时为空） */
function _localBirthFingerprint() {
  let birth = null;
  try { birth = wx.getStorageSync('birth_info') || null; } catch (e) { /* silent */ }
  if (!birth || !birth.date) return '';
  return `${birth.date}|${birth.time || ''}|${birth.city || ''}`;
}

/** API 响应 → 页面统一结构（补齐角色元信息与展示字段） */
function normalizeChart(api) {
  const elements = {};
  ['sun', 'moon', 'rising'].forEach((role) => {
    const raw = api[role];
    if (!raw) { elements[role] = null; return; }
    const meta = ZODIAC_BY_KEY[raw.zodiac] || { name: raw.name, emoji: '' };
    const r = ROLES[role];
    elements[role] = {
      key: role,
      icon: r.icon,
      roleName: r.roleName,
      sign: meta.emoji,
      zodiac: raw.zodiac,
      name: raw.name || meta.name,
      displayName: `${r.roleName} · ${raw.name || meta.name}`,
      label: raw.label || r.label,
      line: raw.text || '',
      approx: !!raw.approx,
      detail: raw.detail || null,
    };
  });
  return {
    birth: api.birth || { date: null, time: null, city: null, complete: false },
    sun: elements.sun,
    moon: elements.moon,
    rising: elements.rising,
    missing: Array.isArray(api.missing) ? api.missing : [],
    message: api.message || '',
  };
}

/** 无数据骨架（未登录 / 未填出生信息） */
function emptyChart() {
  return {
    birth: { date: null, time: null, city: null, complete: false },
    sun: null, moon: null, rising: null,
    missing: ['birth_date'], message: '填出生日期，点亮太阳与月亮 ✦',
  };
}

/** 同步读缓存（页面 onShow 快速渲染用） */
function getCachedChart() {
  try {
    const cached = wx.getStorageSync(CHART_CACHE_KEY);
    if (cached && cached.birth) return cached;
  } catch (e) { /* silent */ }
  return emptyChart();
}

/** 缺失提示 → 页面指引（text + 跳转路由） */
function missingHint(chart) {
  const missing = (chart && chart.missing) || [];
  if (missing.includes('birth_date')) {
    return { text: '完善出生日期，点亮你的星盘 ✦', route: '/pages/birth-info/birth-info' };
  }
  if (missing.includes('birth_time')) {
    return { text: '补全出生时间解锁上升 ✦', route: '/pages/birth-info/birth-info' };
  }
  return { text: '', route: '' };
}

/** 卡片列表（神谕主屏/星盘页共用）：缺失要素为 null 占位 */
function chartToCards(chart) {
  return ['sun', 'moon', 'rising'].map((role) => chart[role]).filter(Boolean);
}

module.exports = {
  ROLES,
  ZODIAC_BY_KEY,
  fetchBirthchart,
  getCachedChart,
  normalizeChart,
  missingHint,
  chartToCards,
};
