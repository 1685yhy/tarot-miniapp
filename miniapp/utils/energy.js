/**
 * utils/energy.js — 今日能量（API 优先）+ 星座工具 + mock 兜底
 *
 * 数据源（开发 03 接入后端接口）：
 *   GET /horoscope/daily → { date, zodiac, energy, factors, astral, tarot, summary, tip }
 * 失败降级链：API → 本地缓存（同日）→ mock 兜底（不白屏）。
 * 数据与设计原型 stars-full-flow.html「页 04 能量详情」保持一致。
 * 红线：不预测 / 不恐吓 / 不命运定性 / 健康只说照顾自己。
 */
const { request } = require('./api');

/* ── 四维度能量（mock）── */
const ENERGY = {
  love: {
    key: 'love', name: '爱情', en: 'LOVE', score: 81, level: '高',
    bar: 'linear-gradient(90deg,#D8BC94,#B08F52)', track: 'rgba(176,143,82,.14)',
    num: '#B08F52', chip: '#A87F47',
    note: '受今日月亮牌影响 · 满月能量加持，情绪丰沛',
    catch: '你习惯把感情放得比工作重——这没什么不好。能认真对待心里那份柔软的人，运气不会差到哪里去。',
    why: '今晚满月照进双鱼，情绪像涨潮的海，一波一波涌上来。你不是变脆弱了，是感知的闸门被月光推开——敏感，是今天的超能力。',
    tip: '今天适合把想说的话写下来，而不是憋在心里。想他的时候就承认想他，不必假装云淡风轻。',
    line: '爱自己的方式是：允许今天想他，也允许明天不想。',
    do30: '今晚睡前，把最想对一个人说的话写进日记，不用发出去——写完，就是回应。',
    card: '月亮牌的朦胧 × 满月之夜——话说不出口的时候，先听自己的心。',
  },
  career: {
    key: 'career', name: '事业', en: 'CAREER', score: 73, level: '中高',
    bar: 'linear-gradient(90deg,#D6CFC0,#A29A8B)', track: 'rgba(138,132,120,.15)',
    num: '#8A8478', chip: '#7A7467',
    note: '受今日权杖能量影响 · 稳步推进的一天',
    catch: '你不是没有野心，只是习惯把力气花在别人看不见的地方——这恰恰是你走得稳的原因。',
    why: '今天的权杖能量像一炉烧旺的柴火，不喧哗，却持续发热。满月的余晖正落在你的案头：适合把想了很久的一件事，落地成今天的第一步。',
    tip: '今天适合把「必须做」和「可以缓」分开写成两张清单。先做掉「必须做」里的第一件，剩下的，让它们安安静静排队就好。',
    line: '真正的前进不是跑赢所有人，而是比昨天的自己，多走一步。',
    do30: '现在拿出纸，写下「必须做」的三件事，只完成第一件——完成后，认真夸自己一句。',
    card: '月亮牌让方向朦胧，权杖让脚步诚实——方向看不清时，先把脚下的路走稳。',
  },
  social: {
    key: 'social', name: '人际', en: 'SOCIAL', score: 64, level: '中',
    bar: 'linear-gradient(90deg,#AFC2D1,#7E97AB)', track: 'rgba(126,151,171,.16)',
    num: '#7E97AB', chip: '#6F8CA2',
    note: '受水逆余波影响 · 旧人旧事浮现，先观察再靠近',
    catch: '你对关系其实很敏锐——谁走近了、谁疏远了，你都感觉得到，只是很多时候，选择不说。',
    why: '水逆的余波还没完全退去，旧人旧事像退潮后露出的贝壳，安静地躺在沙滩上。这不是要你回头，而是让你看清：哪些值得捡起，哪些只是路过。',
    tip: '今天适合先观察，再靠近。别人的话听七分，留三分给自己想；想发出去的消息，先放半小时再决定。',
    line: '真正合拍的关系，不需要你用力留住。',
    do30: '打开通讯录，给一位久未联系、却偶尔会想起的人，发一句「最近好吗」。',
    card: '月亮牌的朦胧，正好替你挡住那些急着要看清的眼神。',
  },
  health: {
    key: 'health', name: '健康', en: 'HEALTH', score: 57, level: '偏低',
    bar: 'linear-gradient(90deg,#A7BACB,#6E8799)', track: 'rgba(110,135,153,.16)',
    num: '#6E8799', chip: '#5F7A8E',
    note: '温柔提醒 · 睡眠与休息，是今天的功课',
    catch: '你最近真的很拼——这一点，身体比你更清楚。它不会说话，只会用「累」来轻轻敲门。',
    why: '满月之夜，睡眠容易变浅，心思却容易变重。不是身体出了什么问题，是它在提醒：该把「再撑一撑」换成「歇一歇」了。',
    tip: '今天比平时早半小时上床，手机放远一点。如果觉得累，就把「累」写下来——写出来的疲惫，会轻一半。',
    line: '照顾自己不是偷懒，是让明天的你，还有力气爱这个世界。',
    do30: '现在放下手机，做三次很慢很长的呼吸，让肩膀先松下来。',
    card: '月亮牌今夜轻轻盖在你身上——月光知道，你需要休息。',
  },
};

const ENERGY_KEYS = ['love', 'career', 'social', 'health'];

/* ── 今日星光卡 fallback（Task 4：接口挂了也有数据 · 与后端 energy_engine 同构）── */
// 星光色盘（12 色暖金/细金系 · 与后端 STAR_COLORS 一致 · 仅 fallback 用）
const STAR_COLORS = [
  '#A98B5F', '#E8C97E', '#D9B48F', '#C7B89F',
  '#B8A6D9', '#8FAED6', '#A8C0D9', '#9FC7A8',
  '#7FA8B8', '#E7A8B8', '#C9A9A6', '#D6C2A0',
];
// 中性宜忌池（与后端 NEUTRAL_GUIDANCE 一致 · 静态文案无禁词 · 仅 fallback 用）
const NEUTRAL_GUIDANCE = [
  ['宜·表达心意', '忌·独自纠结'],
  ['宜·往前一小步', '忌·计划排太满'],
  ['宜·给自己留白', '忌·和他人比较'],
  ['宜·温柔待己', '忌·苛责自己'],
  ['宜·早睡早醒', '忌·过度消耗'],
];

/** fallback 星光卡（与后端同算法：同日同人恒定） */
function buildMockStarGuidance() {
  const todayStr = _todayStr();
  const dateSeed = todayStr.split('').reduce((s, ch) => s + (ch >= '0' && ch <= '9' ? Number(ch) : 0), 0);
  const zodiac = _getZodiac();
  const mixSeed = dateSeed + (zodiac ? zodiac.split('').reduce((s, ch) => s + ch.charCodeAt(0), 0) : 0);
  const g = NEUTRAL_GUIDANCE[dateSeed % NEUTRAL_GUIDANCE.length];
  return {
    star_color: STAR_COLORS[mixSeed % STAR_COLORS.length],
    star_number: dateSeed % 9 + 1,
    advice_do: g[0],
    advice_dont: g[1],
  };
}

/** 默认注脚（未抽牌时） */
function getDefaultEnergy() {
  return ENERGY_KEYS.map((k) => ({ key: k, name: ENERGY[k].name, score: ENERGY[k].score, hot: false }));
}

/**
 * 抽牌后的能量注脚（mock：按牌 id 与日期确定性的选出一个高亮维度）
 * 后端接口开发后替换为真实返回。
 */
function getTodayEnergy(cardId) {
  const d = new Date();
  const seed = (cardId ? String(cardId).length : 0) + d.getDate() + d.getMonth();
  const hotIdx = seed % 4;
  return ENERGY_KEYS.map((k, i) => {
    const base = ENERGY[k].score;
    const delta = i === hotIdx ? 5 : 3;
    return {
      key: k,
      name: ENERGY[k].name,
      score: Math.min(99, base + delta),
      hot: i === hotIdx,
    };
  });
}

/* ── 今日能量数据源（API 优先 · 缓存 / mock 兜底）── */

const ENERGY_CACHE_KEY = 'today_energy_cache';
let _memCache = null; // { date, zodiac, data }

function _todayStr() {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function _getZodiac() {
  try { return wx.getStorageSync('zodiac_sign') || ''; } catch (e) { return ''; }
}

/** 分数 → 档位文案（用于详情页大数字旁的小字） */
function levelOf(score) {
  if (score >= 80) return '高';
  if (score >= 65) return '中高';
  if (score >= 50) return '中';
  if (score >= 35) return '偏低';
  return '低';
}

/** {love:81,...} → 注脚条目数组（hot=当日最高维度，首个） */
function buildEnergyItems(energy) {
  const items = ENERGY_KEYS.map((k) => {
    const s = typeof energy[k] === 'number' ? energy[k] : ENERGY[k].score;
    return { key: k, name: ENERGY[k].name, score: s, level: levelOf(s), hot: false };
  });
  let max = -1;
  let hotIdx = -1;
  items.forEach((it, i) => { if (it.score > max) { max = it.score; hotIdx = i; } });
  if (hotIdx >= 0) items[hotIdx].hot = true;
  return items;
}

/** API 响应 → 统一结构（与 mock 兜底同构） */
function normalizeApi(data) {
  const energy = (data && data.energy) || {};
  const items = buildEnergyItems(energy);
  const factors = {};
  ENERGY_KEYS.forEach((k) => {
    factors[k] = Array.isArray(data.factors && data.factors[k])
      ? data.factors[k].filter((f) => f && f.name).map((f) => ({ name: f.name, delta: Number(f.delta) || 0 }))
      : [];
  });
  return {
    date: data.date || _todayStr(),
    source: 'api',
    energy,
    items,
    factors,
    astral: (data.astral && { type: data.astral.type, label: data.astral.label, note: data.astral.note }) || { type: '', label: '', note: '' },
    tarot: (data.tarot && { name: data.tarot.name, name_en: data.tarot.name_en, image: data.tarot.image }) || null,
    summary: (data && data.summary) || '',
    tip: (data && data.tip) || '',
    // Task 4: 今日星光卡（星光色/数/宜忌）— 缺失留空，前端按字段缺失优雅隐藏
    star_color: (data && data.star_color) || '',
    star_number: (data && data.star_number) || '',
    advice_do: (data && data.advice_do) || '',
    advice_dont: (data && data.advice_dont) || '',
  };
}

/** mock 兜底（接口不可用时）→ 统一结构 */
function normalizeMock() {
  const sky = getSkyNote();
  const items = getTodayEnergy('');
  const hot = items.find((i) => i.hot) || items[0];
  const dd = ENERGY[hot.key];
  const factors = {};
  factors[hot.key] = [{ name: sky.phase, delta: 5 }];
  ENERGY_KEYS.forEach((k) => { if (!factors[k]) factors[k] = []; });
  const energy = {};
  items.forEach((i) => { energy[i.key] = i.score; });
  return {
    date: _todayStr(),
    source: 'mock',
    energy,
    items,
    factors,
    astral: { type: 'mock', label: sky.text, note: dd.note },
    tarot: null,
    summary: `${hot.name}能量最盛——${dd.catch}`,
    tip: dd.tip,
    // Task 4: 星光色/数/宜忌 fallback（确定性 · 同日同人恒定）
    ...buildMockStarGuidance(),
  };
}

/**
 * 获取今日能量（登录后走 GET /horoscope/daily，自动带 token）。
 * 降级链：API → 同日本地缓存 → mock 兜底；永不 reject，不白屏。
 * 同一会话内缓存（星座变化会自动重新拉取）。
 * @param {{force?: boolean}} opts force=true 跳过内存缓存强制刷新
 */
async function fetchTodayEnergy(opts = {}) {
  const today = _todayStr();
  const zodiac = _getZodiac();
  if (!opts.force && _memCache && _memCache.date === today && _memCache.zodiac === zodiac) {
    return _memCache.data;
  }

  let data = null;
  // 1) API（有 token 才请求；401/网络失败均被 request 捕获）
  try {
    if (wx.getStorageSync('token')) {
      const api = await request('/horoscope/daily');
      if (api && api.energy) {
        data = normalizeApi(api);
        try { wx.setStorageSync(ENERGY_CACHE_KEY, data); } catch (e) { /* silent */ }
      }
    }
  } catch (err) {
    // 接口失败 → 走缓存 / mock 降级
    console.warn('[energy] /horoscope/daily 请求失败，走降级:', err && err.message);
  }

  // 2) 同日本地缓存
  if (!data) {
    try {
      const cached = wx.getStorageSync(ENERGY_CACHE_KEY);
      if (cached && cached.date === today) {
        data = { ...cached, source: 'cache' };
      }
    } catch (e) { /* silent */ }
  }

  // 3) mock 兜底
  if (!data) {
    data = normalizeMock();
  }

  _memCache = { date: today, zodiac, data };
  return data;
}

/* ── 十二星座（key/name/emoji/dates 与原型完全一致）── */
const ZODIACS = [
  { key: 'aries', name: '白羊座', emoji: '♈', dates: '3.21-4.19' },
  { key: 'taurus', name: '金牛座', emoji: '♉', dates: '4.20-5.20' },
  { key: 'gemini', name: '双子座', emoji: '♊', dates: '5.21-6.21' },
  { key: 'cancer', name: '巨蟹座', emoji: '♋', dates: '6.22-7.22' },
  { key: 'leo', name: '狮子座', emoji: '♌', dates: '7.23-8.22' },
  { key: 'virgo', name: '处女座', emoji: '♍', dates: '8.23-9.22' },
  { key: 'libra', name: '天秤座', emoji: '♎', dates: '9.23-10.23' },
  { key: 'scorpio', name: '天蝎座', emoji: '♏', dates: '10.24-11.22' },
  { key: 'sagittarius', name: '射手座', emoji: '♐', dates: '11.23-12.21' },
  { key: 'capricorn', name: '摩羯座', emoji: '♑', dates: '12.22-1.19' },
  { key: 'aquarius', name: '水瓶座', emoji: '♒', dates: '1.20-2.18' },
  { key: 'pisces', name: '双鱼座', emoji: '♓', dates: '2.19-3.20' },
];

/** 名字 → 星座对象（storage 中 zodiac_sign 存中文名） */
const ZODIAC_BY_NAME = {};
ZODIACS.forEach((z) => { ZODIAC_BY_NAME[z.name] = z; });

/** key → 星座对象 */
const ZODIAC_BY_KEY = {};
ZODIACS.forEach((z) => { ZODIAC_BY_KEY[z.key] = z; });

/** 由出生月日推导星座（原型算法 · 二期接入真实星盘计算） */
function zodiacFromDate(m, d) {
  const rules = [
    [1, 20, 'aquarius'], [2, 19, 'pisces'], [3, 21, 'aries'], [4, 20, 'taurus'],
    [5, 21, 'gemini'], [6, 22, 'cancer'], [7, 23, 'leo'], [8, 23, 'virgo'],
    [9, 23, 'libra'], [10, 24, 'scorpio'], [11, 23, 'sagittarius'], [12, 22, 'capricorn'],
  ];
  let key = 'capricorn';
  rules.forEach((r) => { if (m > r[0] || (m === r[0] && d >= r[1])) key = r[2]; });
  return key;
}

/** 读 storage 的星座名 → 徽章文案（emoji + 名字） */
function getZodiacBadge() {
  let name = '';
  try { name = wx.getStorageSync('zodiac_sign') || ''; } catch (e) { /* silent */ }
  if (!name) return '';
  const z = ZODIAC_BY_NAME[name];
  return z ? `${z.emoji} ${z.name}` : name;
}

/* ── 天象小字（mock：按日期确定性生成月相与月亮落座）── */
const PHASES = ['新月', '娥眉月', '上弦月', '盈凸月', '满月', '亏凸月', '下弦月', '残月'];
const SIGNS = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女', '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼'];

function getSkyNote(date) {
  const d = date || new Date();
  const day = d.getDate();
  const phaseIdx = Math.floor(((day + 13) % 30) / 4); // 月相轮转（mock）
  const signIdx = day % 12;
  const phase = PHASES[phaseIdx] || '满月';
  return { phase, sign: SIGNS[signIdx], text: `${phase} · 月亮在${SIGNS[signIdx]}` };
}

module.exports = {
  ENERGY,
  ENERGY_KEYS,
  getDefaultEnergy,
  getTodayEnergy,
  levelOf,
  buildEnergyItems,
  fetchTodayEnergy,
  ZODIACS,
  ZODIAC_BY_NAME,
  ZODIAC_BY_KEY,
  zodiacFromDate,
  getZodiacBadge,
  getSkyNote,
};
