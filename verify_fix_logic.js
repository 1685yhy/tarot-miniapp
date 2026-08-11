// verify_fix_logic.js — T8-4 Fix round 逻辑验证（真实 resonance.js + mock wx/API）
// 覆盖：wx:key gid 唯一 / 隐身回读 / give 404 vanished / flyStar 单实例 key 匹配
const Module = require('module');
const path = require('path');

let pageObj = null;
let toastLog = [];
let requestCalls = [];
let storage = { token: 'test-token' };

const wxMock = {
  getStorageSync: (k) => storage[k],
  setStorageSync: (k, v) => { storage[k] = v; },
  showToast: (o) => toastLog.push(o),
  showModal: () => {},
  reLaunch: () => {},
  stopPullDownRefresh: () => {},
};

const apiMock = {
  request: async (url, opts) => { requestCalls.push({ url, opts }); return {}; },
  getFriendlyError: (e) => '网络异常',
};
const cardsMock = { findCard: () => null, computeImagePath: () => '' };
const energyMock = { ZODIAC_BY_KEY: { capricorn: { emoji: '♑', name: '摩羯座' } } };
const analyticsMock = { trackEvent: () => {} };

const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === '../../utils/api') return apiMock;
  if (request === '../../utils/cards') return cardsMock;
  if (request === '../../utils/energy') return energyMock;
  if (request === '../../utils/analytics') return analyticsMock;
  return origLoad.apply(this, arguments);
};
global.wx = wxMock;
global.Page = (cfg) => {
  // 模拟小程序运行时：setData 合并进 data（含深层对象替换，足够覆盖本页用法）
  pageObj = Object.assign({}, cfg, {
    data: JSON.parse(JSON.stringify(cfg.data || {})),
    setData(updates) {
      Object.keys(updates).forEach((k) => {
        this.data[k] = updates[k];
      });
    },
  });
  pageObj.isLoggedIn = !!storage.token;
};
global.getApp = () => ({});
global.Component = () => {};

require('/mnt/e/tarot-miniapp/miniapp/pages/resonance/resonance.js');

const results = [];
function check(name, cond, detail) {
  results.push({ name, pass: !!cond, detail: detail || '' });
  console.log((cond ? 'PASS' : 'FAIL') + ' | ' + name + (detail ? ' | ' + detail : ''));
}

(async () => {
  // ========== 场景 1：重复 type 分组 → gid 唯一（wx:key 依据） ==========
  const wall1 = {
    active_count: 5,
    my_card: null,
    groups: [
      { type: 'zodiac', label: '同星座的星光 · 摩羯座', members: [{ uid: 'u1', alias: 'A', zodiac: 'capricorn', star_number: 5, card: { name_zh: '月亮' }, tier_name: '星辉', resonate_count: 1, resonated_by_me: false }] },
      { type: 'zodiac', label: '同星座的星光 · 狮子座', members: [{ uid: 'u2', alias: 'B', zodiac: 'capricorn', star_number: 6, card: { name_zh: '太阳' }, tier_name: '星辉', resonate_count: 0, resonated_by_me: false }] },
      { type: 'number', label: '同星光数的星光 · 5', members: [{ uid: 'u3', alias: 'C', zodiac: 'capricorn', star_number: 5, card: { name_zh: '命运之轮' }, tier_name: '星尘', resonate_count: 2, resonated_by_me: false }] },
      { type: 'fallback', label: '同星光的星', members: [] },
    ],
  };
  pageObj._applyWall(wall1);
  const gids = pageObj.data.groups.map((g) => g.gid);
  check('gid 唯一（4 组 type 含重复 zodiac）', new Set(gids).size === gids.length, gids.join(','));
  check('gid 与 type 区分（同 type 不同 gid）', pageObj.data.groups[0].gid !== pageObj.data.groups[1].gid, gids[0] + ' vs ' + gids[1]);

  // ========== 场景 2：隐身回读（my_card.visible） ==========
  const wall2 = {
    active_count: 1,
    my_card: { alias: '我', zodiac: 'capricorn', star_number: 5, card: { name_zh: '月亮' }, tier_name: '星辉', received_today: 2, visible: false },
    groups: [],
  };
  pageObj.setData({ visible: true }); // 默认开
  pageObj._applyWall(wall2);
  check('隐身用户重进页：visible 回读 false', pageObj.data.visible === false, 'visible=' + pageObj.data.visible);

  const wall2b = JSON.parse(JSON.stringify(wall2));
  wall2b.my_card.visible = true;
  pageObj._applyWall(wall2b);
  check('可见用户：visible 保持 true', pageObj.data.visible === true, 'visible=' + pageObj.data.visible);

  const wall2c = JSON.parse(JSON.stringify(wall2));
  delete wall2c.my_card.visible; // 旧契约（无字段）→ 保持原默认，不误改
  pageObj.setData({ visible: true });
  pageObj._applyWall(wall2c);
  check('旧契约缺 visible 字段：不误改开关', pageObj.data.visible === true);

  // ========== 场景 3：give 404 → vanished（按钮文案「星已远」，非「已共鸣」） ==========
  pageObj._applyWall(wall1);
  pageObj._handleGiveError({ statusCode: 404, message: '这颗星不在夜空中' }, 0, 0);
  const m = pageObj.data.groups[0].members[0];
  check('404 → vanished=true', m.vanished === true);
  check('404 → resonatedByMe 保持 false（文案不是「已共鸣」）', m.resonatedByMe === false);
  const toast404 = toastLog.filter((t) => t.title && t.title.indexOf('夜空中') !== -1);
  check('404 toast 与按钮文案一致（夜空中）', toast404.length >= 1, toast404[0] && toast404[0].title);

  // vanished 后点击 → 直接 toast，不发请求
  const before = requestCalls.length;
  pageObj.isLoggedIn = true;
  pageObj._giving = false;
  pageObj.data.visible = true;
  await pageObj.onGiveResonance({ currentTarget: { dataset: { uid: 'u1', gidx: 0, midx: 0 } } });
  check('vanished 卡再点：不发请求', requestCalls.length === before, 'calls=' + requestCalls.length);

  // ========== 场景 4：flyStar 单实例（按 member.key 匹配，跨组同 uid 只渲染点击那张） ==========
  // 同一 uid u9 出现在组 0（同星座）和组 3（兜底）—— 构造后端真实可达的跨组重复
  const wall3 = {
    active_count: 2,
    my_card: null,
    groups: [
      { type: 'zodiac', label: '同星座的星光 · 摩羯座', members: [{ uid: 'u9', alias: 'X', zodiac: 'capricorn', star_number: 5, card: { name_zh: '月亮' }, tier_name: '星辉', resonate_count: 0, resonated_by_me: false }] },
      { type: 'fallback', label: '同星光的星', members: [{ uid: 'u9', alias: 'X', zodiac: 'capricorn', star_number: 5, card: { name_zh: '月亮' }, tier_name: '星辉', resonate_count: 0, resonated_by_me: false }, { uid: 'u10', alias: 'Y', zodiac: 'capricorn', star_number: 6, card: { name_zh: '太阳' }, tier_name: '星辉', resonate_count: 0, resonated_by_me: false }] },
    ],
  };
  pageObj._applyWall(wall3);
  apiMock.request = async (url) => { if (url === '/resonance/give') return { limit: 10, count_today: 1 }; return {}; };
  pageObj._giving = false;
  pageObj.data.isLoggedIn = true;
  await pageObj.onGiveResonance({ currentTarget: { dataset: { uid: 'u9', gidx: 1, midx: 0 } } });
  const fs = pageObj.data.flyStar;
  const keyOfClicked = pageObj.data.groups[1].members[0].key; // 点击的是兜底组第一张
  check('flyStar 携带被点卡 key', fs && fs.key === keyOfClicked, 'key=' + (fs && fs.key) + ' expected=' + keyOfClicked);
  check('flyStar 不含 uid 匹配字段（不再跨组重复渲染）', fs && fs.uid === undefined);
  const sameUidOtherKey = pageObj.data.groups[0].members[0].key;
  check('同 uid 另一组卡 key 不同（wxml 只匹配一张）', sameUidOtherKey !== keyOfClicked, sameUidOtherKey + ' vs ' + keyOfClicked);
  // 更新后 members 仍保留 key（onGiveResonance 重建 groups 不丢 key）
  check('give 后 key 保留', pageObj.data.groups[1].members[0].key === keyOfClicked);
  check('give 后同组第二张 key 不变', pageObj.data.groups[1].members[1].key === '1-1-u10', pageObj.data.groups[1].members[1].key);

  // ========== 场景 5：onCardImgError 保留 gid（wx:key 不回退） ==========
  const targetKey = pageObj.data.groups[0].members[0].key;
  const gidBefore = pageObj.data.groups[0].gid;
  pageObj.onCardImgError({ currentTarget: { dataset: { key: targetKey } } });
  check('imgError 重建组仍带 gid', pageObj.data.groups[0].gid === gidBefore, pageObj.data.groups[0].gid);

  // ========== 场景 6：wx:key 与 fly-star 条件静态一致性 ==========
  const wxml = require('fs').readFileSync('/mnt/e/tarot-miniapp/miniapp/pages/resonance/resonance.wxml', 'utf8');
  check('wxml 外层 wx:key=gid', /wx:key="gid"/.test(wxml));
  check('wxml 无 wx:key=type', !/wx:key="type"/.test(wxml));
  check('wxml flyStar 按 key 匹配', /flyStar\.key === member\.key/.test(wxml));
  check('wxml 无 flyStar.uid 匹配', !/flyStar\.uid === member\.uid/.test(wxml));
  check('wxml 星已远文案', /星已远/.test(wxml));
  check('wxml give-btn--gone 类', /give-btn--gone/.test(wxml));

  const failed = results.filter((r) => !r.pass);
  console.log('\n===== ' + (results.length - failed.length) + '/' + results.length + ' passed =====');
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.error('HARNESS ERROR:', e); process.exit(2); });
