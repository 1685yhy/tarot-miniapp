// dev-meet-verify.js —— 星辰相遇页（T2-4）逻辑级自动化验证
//
// 方式：真实加载 miniapp 真实代码（meet.js + utils/api.js + utils/cards.js +
// utils/energy.js + utils/analytics.js），仅 stub wx/getApp/Page 全局。
// 覆盖：表单交互 → quick 合盘 payload → 结果三屏归一化 → 估算标注 →
// 分享文案 → 我的相遇列表 → 邀请码拉取（arraybuffer→临时文件→弹层）→
// 保存相册 → 错误降级（quick 500 / 直链 404）。
// 运行：node dev-meet-verify.js   （退出码 0 = 全过）

const path = require('path');
const assert = require('assert');

const MINIAPP = '/mnt/e/tarot-miniapp/miniapp';

// ── wx 全量 stub（测试可注入） ──
const wxState = {
  storage: {},
  reqLog: [],
  responses: [],          // 队列：{statusCode, data} | {__fail}
  toasts: [],
  modals: [],
  navs: [],
  previewed: [],
  fsWriteLog: [],
  saveLog: [],
  _reqNo: 0,
};

const wx = {
  getAccountInfoSync: () => ({ miniProgram: { envVersion: 'develop' } }),
  getExtConfigSync: () => ({}),
  getStorageSync: (k) => (k in wxState.storage ? wxState.storage[k] : ''),
  setStorageSync: (k, v) => { wxState.storage[k] = v; },
  removeStorageSync: (k) => { delete wxState.storage[k]; },
  reportAnalytics: () => {},
  request(opts) {
    wxState.reqLog.push({ no: ++wxState._reqNo, url: opts.url, method: opts.method, data: opts.data, header: opts.header, responseType: opts.responseType });
    const respond = wxState.responses.shift();
    if (respond === undefined) {
      throw new Error(`NO RESPONSE QUEUED for ${opts.url}`);
    }
    setTimeout(() => {
      if (respond.__fail) opts.fail({ errMsg: respond.__fail });
      else opts.success({ statusCode: respond.statusCode, data: respond.data });
    }, 0);
    return { abort() {} };
  },
  showToast: (o) => { wxState.toasts.push(o); },
  showModal: (o) => { wxState.modals.push(o); },
  navigateTo: (o) => { wxState.navs.push(o.url); },
  reLaunch: (o) => { wxState.navs.push('RELAUNCH:' + (o && o.url)); },
  previewImage: (o) => { wxState.previewed.push(o.urls[0]); },
  openSetting: () => { wxState.modals.push({ __openedSetting: true }); },
  stopPullDownRefresh: () => {},
  env: { USER_DATA_PATH: '/tmp/miniapp-user' },
  getFileSystemManager: () => ({
    writeFile: (o) => {
      wxState.fsWriteLog.push({ filePath: o.filePath, encoding: o.encoding, dataLen: o.data && o.data.byteLength });
      if (wxState.fsWriteFail) o.fail({ errMsg: 'writeFile:fail' });
      else o.success();
    },
  }),
  saveImageToPhotosAlbum: (o) => {
    wxState.saveLog.push(o.filePath);
    if (wxState.saveHandler) wxState.saveHandler(o);
  },
};

global.wx = wx;
global.getApp = () => ({ globalData: {} });

// ── Page 捕获 ──
let pageConfig = null;
global.Page = (cfg) => { pageConfig = cfg; };

// ── 加载真实代码（require 真实文件；utils 依赖的 wx 已在 global） ──
require(path.join(MINIAPP, 'pages/meet/meet.js'));
assert.ok(pageConfig, 'Page() 未捕获到配置');

// ── 页面实例工厂（setData 支持 'res.cards[0].imgError' 路径键） ──
function setPath(obj, key, value) {
  const parts = key.replace(/\[(\d+)\]/g, '.$1').split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}
function makePage() {
  const inst = Object.create(pageConfig);
  inst.data = JSON.parse(JSON.stringify(pageConfig.data));
  inst.setData = function (patch) {
    Object.keys(patch).forEach((k) => {
      if (k.indexOf('.') >= 0 || k.indexOf('[') >= 0) setPath(this.data, k, patch[k]);
      else this.data[k] = patch[k];
    });
  };
  return inst;
}
function resetWx() {
  wxState.storage = {};
  wxState.reqLog = [];
  wxState.responses = [];
  wxState.toasts = [];
  wxState.modals = [];
  wxState.navs = [];
  wxState.previewed = [];
  wxState.fsWriteLog = [];
  wxState.saveLog = [];
  wxState.fsWriteFail = false;
  wxState.saveHandler = null;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 真实后端同构响应（test_meet.py 的 quick 形态） ──
function quickResponse(overrides = {}) {
  return {
    meet_id: 'm-1111',
    relation: 'friend',
    a: {
      zodiac: 'leo', name_zh: '狮子座',
      sun: { zodiac: 'leo', name_zh: '狮子座' },
      moon: { zodiac: 'cancer', name_zh: '巨蟹座' },
      rising: { zodiac: 'taurus', name_zh: '金牛座' },
    },
    b: {
      zodiac: 'aries', name_zh: '白羊座',
      sun: { zodiac: 'aries', name_zh: '白羊座' },
      moon: { zodiac: 'gemini', name_zh: '双子座' },
      rising: null,
    },
    score: 92,
    level_name: '星光共鸣',
    factors: [
      { role: 'sun', score: 95, reason: '同元素·火象相映 +8' },
      { role: 'moon', score: 88, reason: '月亮落座互补 +6' },
      { role: 'rising', score: 82, reason: '上升同元素 +4' },
    ],
    cards: [
      { position: '关系之牌', card_id: 1, name_zh: '恋人', meaning_snippet: '一段彼此照亮的关系正在发生', tip: '这段关系的星光之牌是「恋人」——一段彼此照亮的关系正在发生' },
      { position: '星光之牌', card_id: 2, name_zh: '星星', meaning_snippet: '在对方眼中你是希望本身', tip: '在对方眼中，你是「星星」——希望本身' },
      { position: '相处之牌', card_id: 3, name_zh: '权杖二', meaning_snippet: '先并肩走一段', tip: '先并肩走一段' },
    ],
    tips: ['你们的星光节奏是慢热的——先并肩走一段，再慢慢看清彼此的方向。', '给彼此留一点安静的空间，想念反而会自己长出来。'],
    estimated: false,
    estimate_note: '',
    ...overrides,
  };
}

(async () => {
  let pass = 0;
  const ok = (name) => { pass++; console.log(`  ✓ ${name}`); };
  const assertThrows = (fn, re) => {
    try { fn(); } catch (e) { if (re.test(e.message)) return; throw e; }
    throw new Error(`expected throw matching ${re}`);
  };

resetWx();
  // ═══ 1. 表单初始态与交互 ═══
  console.log('══ 1. 表单初始态与交互');
  {
    const p = makePage();
    assert.strictEqual(p.data.step, 'form');
    assert.strictEqual(p.data.zodiacs.length, 12);
    const els = {};
    p.data.zodiacs.forEach((z) => { els[z.element] = (els[z.element] || 0) + 1; });
    assert.deepStrictEqual(els, { fire: 3, earth: 3, air: 3, water: 3 }, '12宫格元素 4×3');
    p.data.zodiacs.forEach((z) => assert.ok(z.elementBg && z.elementBg.startsWith('rgba'), `元素底色 ${z.key}`));
    assert.strictEqual(p.data.relations.length, 4);
    assert.strictEqual(p.data.relationKey, 'friend');
    assert.ok(p.data.relations[0].selected && p.data.relations.filter((r) => r.selected).length === 1);
    assert.strictEqual(p.data.hasZodiac, false);
    assert.strictEqual(p.data.hasBirth, false);
    ok('初始态：4 徽章 + 12 宫格元素底色 + 布尔预计算');

    p.onRelationTap({ currentTarget: { dataset: { key: 'love' } } });
    assert.strictEqual(p.data.relationKey, 'love');
    assert.strictEqual(p.data.relations.filter((r) => r.selected).length, 1);
    p.onZodiacTap({ currentTarget: { dataset: { key: 'aries' } } });
    assert.strictEqual(p.data.zodiacKey, 'aries');
    assert.strictEqual(p.data.hasZodiac, true);
    p.onDateChange({ detail: { value: '1995-03-21' } });
    assert.strictEqual(p.data.birthDate, '1995-03-21');
    assert.strictEqual(p.data.birthDateText, '3.21');
    assert.strictEqual(p.data.hasBirth, true);
    p.onTimeChange({ detail: { value: '14:30' } });
    assert.strictEqual(p.data.birthTime, '14:30');
    p.onClearBirth();
    assert.strictEqual(p.data.birthDate, '');
    assert.strictEqual(p.data.birthTime, '');
    assert.strictEqual(p.data.hasBirth, false);
    ok('关系/星座/出生交互 + 清除');
  }

resetWx();
  // ═══ 2. 未选星座点开始 → 拦截提示 ═══
  {
    const p = makePage();
    p.onStart();
    assert.strictEqual(p.data.step, 'form');
    assert.strictEqual(wxState.reqLog.length, 0);
    assert.ok(wxState.toasts.some((t) => t.title.indexOf('先选一个星座') >= 0));
    ok('未选星座 → toast 拦截，不发请求');
  }

resetWx();
  // ═══ 3. quick 主链路：payload + 结果三屏归一化 ═══
  {
    const p = makePage();
    p.onZodiacTap({ currentTarget: { dataset: { key: 'aries' } } });
    p.onRelationTap({ currentTarget: { dataset: { key: 'love' } } });
    p.onDateChange({ detail: { value: '1995-03-21' } });
    p.onTimeChange({ detail: { value: '14:30' } });
    wxState.responses.push({ statusCode: 200, data: quickResponse() });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } }); // quick 后静默刷新列表
    p.onStart();
    assert.strictEqual(p.data.step, 'loading');
    await sleep(15);
    const req = wxState.reqLog[0];
    assert.ok(req.url.endsWith('/meet/quick'), `url ${req.url}`);
    assert.strictEqual(req.method, 'POST');
    assert.deepStrictEqual(req.data, {
      relation: 'love', zodiac_b: 'aries', b_birth_date: '1995-03-21', b_birth_time: '14:30',
    });
    assert.strictEqual(p.data.step, 'result');
    const res = p.data.res;
    assert.strictEqual(res.score, 92);
    assert.strictEqual(res.scoreText, '92');
    assert.strictEqual(res.levelName, '星光共鸣');
    assert.strictEqual(res.a.name, '狮子座');
    assert.strictEqual(res.b.name, '白羊座');
    assert.ok(p._shareTitle().indexOf('92') >= 0 && p._shareTitle().indexOf('星光相映') >= 0);
    assert.ok(res.disclaimer.indexOf('仅供娱乐') >= 0);
    assert.strictEqual(p.data.hasResult, true);
    assert.strictEqual(p.data.hasFactors, true);
    assert.strictEqual(p.data.hasCards, true);
    assert.strictEqual(p.data.hasTips, true);
    assert.strictEqual(res.factors.length, 3);
    assert.strictEqual(res.factors[0].roleName, '太阳');
    assert.strictEqual(res.factors[1].roleName, '月亮');
    assert.strictEqual(res.factors[2].roleName, '上升');
    assert.strictEqual(res.factors[0].barWidth, '95%');
    assert.ok(res.factors[0].reason.indexOf('相映') >= 0);
    assert.strictEqual(res.cards.length, 3);
    assert.ok(res.cards[0].image.indexOf('major_06_the_lovers.webp') >= 0, res.cards[0].image);
    assert.ok(res.cards[0].hasImage);
    assert.strictEqual(res.cards[0].snippet.length > 0, true);
    assert.strictEqual(res.tips.length, 2);
    assert.strictEqual(p.data.estimated, false);
    assert.strictEqual(res.estimateNote, '');
    assert.strictEqual(p._meetId, 'm-1111');
    ok('quick 全链路：payload 正确 + 结果三屏字段归一化（圆环/要素/三牌/提示/免责）');
  }

resetWx();
  // ═══ 4. 仅时间无日期 → 提示 + 不设置（避免静默丢弃与后端 400） ═══
  {
    const p = makePage();
    p.onZodiacTap({ currentTarget: { dataset: { key: 'taurus' } } });
    p.onTimeChange({ detail: { value: '09:00' } });
    assert.strictEqual(p.data.birthTime, '');
    assert.strictEqual(p.data.hasBirth, false);
    assert.ok(wxState.toasts.some((t) => t.title === '请先选择出生日期'));
    // 先选日期再选时间 → 正常设置 + 文案预计算
    p.onDateChange({ detail: { value: '1995-03-21' } });
    assert.strictEqual(p.data.birthDateLabel, '3.21');
    p.onTimeChange({ detail: { value: '09:00' } });
    assert.strictEqual(p.data.birthTime, '09:00');
    assert.strictEqual(p.data.birthTimeLabel, '09:00');
    wxState.responses.push({ statusCode: 200, data: quickResponse() });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onStart();
    await sleep(15);
    const req = wxState.reqLog[0];
    assert.deepStrictEqual(req.data, { relation: 'friend', zodiac_b: 'taurus', b_birth_date: '1995-03-21', b_birth_time: '09:00' });
    assert.strictEqual(p.data.submitLabel, '开始合盘 ✦'); // 结果后复原
    ok('时间无日期 → toast 拦截；先日期后时间 → payload 完整');
  }

resetWx();
  // ═══ 5. estimated=true 估算标注 + 缺要素徽章 ═══
  {
    const p = makePage();
    p.onZodiacTap({ currentTarget: { dataset: { key: 'gemini' } } });
    const est = quickResponse({
      estimated: true,
      estimate_note: '缺少月亮、上升，已按 100% 太阳重归一化，结果仅供参考',
      b: {
        zodiac: 'gemini', name_zh: '双子座',
        sun: { zodiac: 'gemini', name_zh: '双子座' },
        moon: null, rising: null,
      },
    });
    wxState.responses.push({ statusCode: 200, data: est });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onStart();
    await sleep(15);
    assert.strictEqual(p.data.estimated, true);
    assert.ok(p.data.res.estimateNote.indexOf('太阳') >= 0);
    assert.strictEqual(p.data.res.b.hasMoon, false);
    assert.strictEqual(p.data.res.b.hasRising, false);
    assert.strictEqual(p.data.res.a.hasMoon, true);
    ok('estimated=true → 空态标注「月亮落座未知按太阳估算」文案走后端');
  }

resetWx();
  // ═══ 6. 未知牌名 → 图片占位不破版；score 缺失 → '--' + 兜底分享 ═══
  {
    const p = makePage();
    p.onZodiacTap({ currentTarget: { dataset: { key: 'libra' } } });
    const odd = quickResponse({
      score: null, level_name: null, estimated: false,
      cards: [{ position: '关系之牌', card_id: 1, name_zh: '不存在的牌', meaning_snippet: '', tip: 'xx' }],
    });
    wxState.responses.push({ statusCode: 200, data: odd });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onStart();
    await sleep(15);
    assert.strictEqual(p.data.res.scoreText, '--');
    assert.strictEqual(p._shareTitle().indexOf('星光相遇了') >= 0, true);
    assert.strictEqual(p.data.res.cards[0].image, '');
    assert.strictEqual(p.data.res.cards[0].hasImage, false);
    assert.strictEqual(p.data.res.cards[0].cardVisible, false);
    assert.strictEqual(p.data.res.cards[0].cardFallback, true);
    assert.strictEqual(p.data.hasCards, true);
    ok('脏数据降级：未知牌名占位 + score 缺失兜底分享');
  }

resetWx();
  // ═══ 7. quick 失败（500）→ 错误态 + 友好文案 ═══
  {
    const p = makePage();
    p.onZodiacTap({ currentTarget: { dataset: { key: 'scorpio' } } });
    wxState.responses.push({ statusCode: 500, data: { detail: '服务器繁忙' } });
    p.onStart();
    await sleep(15);
    assert.strictEqual(p.data.step, 'error');
    assert.ok(p.data.errorMsg.length > 0);
    ok('quick 500 → 错误屏 + 重新连接');
  }

resetWx();
  // ═══ 8. 直链 meet_id：onLoad → GET /meet/{id} 渲染结果 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 200, data: quickResponse({ meet_id: 'm-share' }) });
    p.onLoad({ meet_id: 'm-share' });
    await sleep(15);
    const req = wxState.reqLog[0];
    assert.ok(req.url.endsWith('/meet/m-share'));
    assert.strictEqual(p.data.step, 'result');
    assert.strictEqual(p.data.res.scoreText, '92');
    ok('直链 onLoad meet_id → 详情渲染结果');
  }

resetWx();
  // ═══ 9. 直链 404 → 优雅回落输入屏 + 提示（不发崩溃） ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 404, data: { detail: '相遇记录不存在' } });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onLoad({ meet_id: 'm-404' });
    await sleep(15);
    assert.strictEqual(p.data.step, 'form');
    assert.ok(wxState.toasts.some((t) => t.title.indexOf('这场相遇还没开始') >= 0));
    assert.strictEqual(p.data.hasMeets, false);
    ok('直链 404 → 回落表单 + 「发起一场」提示');
  }

resetWx();
  // ═══ 10. 我的相遇列表 ═══
  {
    const p = makePage();
    wxState.responses.push({
      statusCode: 200,
      data: {
        meetings: [
          { meet_id: 'm1', relation: 'friend', b_name: '白羊座', score: 88, level_name: '星光相映', created_at: '2026-08-09T10:00:00' },
          { meet_id: 'm2', relation: 'work', b_name: '摩羯座', score: null, level_name: null, created_at: '2026-08-08T09:00:00' },
          { meet_id: 'm3', relation: 'love', b_name: '天秤座', score: 72, level_name: '星光相映', created_at: '' },
          { meet_id: 'm4', relation: 'family', b_name: '双鱼座', score: 66, level_name: '星光相伴', created_at: '2026-08-07T08:00:00' },
          { meet_id: 'm5', relation: 'friend', b_name: '巨蟹座', score: 90, level_name: '星光共鸣', created_at: '2026-08-06T07:00:00' },
          { meet_id: 'm6', relation: 'friend', b_name: '金牛座', score: 80, level_name: '星光相映', created_at: '2026-08-05T06:00:00' },
        ],
      },
    });
    p.onLoad({});
    await sleep(15);
    assert.strictEqual(p.data.hasMeets, true);
    assert.strictEqual(p.data.meets.length, 5, '最多展示 5 条');
    assert.strictEqual(p.data.meets[0].relationLabel, '朋友');
    assert.strictEqual(p.data.meets[0].scoreText, '88');
    assert.strictEqual(p.data.meets[0].dateText, '8.9');
    assert.strictEqual(p.data.meets[1].scoreText, '--');
    assert.strictEqual(p.data.meets[2].dateText, '');
    ok('我的相遇列表归一化（截断 5 条/缺失兜底/日期格式化）');
  }

resetWx();
  // ═══ 11. 列表失败 → 静默降级 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 500, data: { detail: '服务器繁忙' } });
    p.onLoad({});
    await sleep(15);
    assert.strictEqual(p.data.hasMeets, false);
    assert.strictEqual(p.data.step, 'form');
    ok('列表失败 → 静默降级不阻塞');
  }

resetWx();
  // ═══ 12. 点我的相遇项 → 回看详情 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 200, data: quickResponse({ meet_id: 'm1' }) });
    p.onMeetItemTap({ currentTarget: { dataset: { id: 'm1' } } });
    await sleep(15);
    assert.ok(wxState.reqLog[0].url.endsWith('/meet/m1'));
    assert.strictEqual(p.data.step, 'result');
    ok('我的相遇点项 → 详情回看');
  }

resetWx();
  // ═══ 13. 邀请：POST /meet/invite arraybuffer → 临时文件 → 弹层 ═══
  {
    const p = makePage();
    wxState.storage.token = 'tok-1';
    p._meetId = 'm-1111';
    wxState.responses.push({ statusCode: 200, data: Buffer.from([0x89, 0x50, 0x4e, 0x47]) });
    p.onInvite();
    const req = wxState.reqLog[0];
    assert.ok(req.url.endsWith('/meet/invite'), req.url);
    assert.strictEqual(req.method, 'POST');
    assert.deepStrictEqual(req.data, { meet_id: 'm-1111' });
    assert.strictEqual(req.responseType, 'arraybuffer');
    assert.strictEqual(req.header.Authorization, 'Bearer tok-1');
    await sleep(15);
    assert.strictEqual(wxState.fsWriteLog.length, 1);
    assert.ok(wxState.fsWriteLog[0].filePath.indexOf('meet-invite-m-1111.png') >= 0);
    assert.strictEqual(wxState.fsWriteLog[0].encoding, 'binary');
    assert.strictEqual(wxState.fsWriteLog[0].dataLen, 4);
    assert.strictEqual(p.data.inviteVisible, true);
    assert.ok(p.data.inviteQrPath.indexOf('meet-invite-m-1111.png') >= 0);
    assert.strictEqual(p.data.inviting, false);
    ok('邀请：鉴权头 + arraybuffer + 二进制写临时文件 + 弹层展示');
  }

resetWx();
  // ═══ 14. 邀请失败（400 已加入）→ JSON detail 解码提示 ═══
  {
    const p = makePage();
    p._meetId = 'm-1111';
    const jsonBuf = Buffer.from(JSON.stringify({ detail: '好友已加入，无需再次邀请' }), 'utf8');
    wxState.responses.push({ statusCode: 400, data: jsonBuf });
    p.onInvite();
    await sleep(15);
    assert.strictEqual(p.data.inviting, false);
    assert.strictEqual(p.data.inviteVisible, false);
    assert.ok(wxState.toasts.some((t) => t.title === '好友已加入，无需再次邀请'));
    ok('邀请 400 → 解码 JSON detail 提示（幂等）');
  }

resetWx();
  // ═══ 15. 保存邀请码到相册（成功 + 未授权降级） ═══
  {
    const p = makePage();
    p._qrPath = '/tmp/qr.png';
    wxState.saveHandler = (o) => o.success();
    p.onSaveInviteQr();
    assert.strictEqual(wxState.saveLog.length, 1);
    assert.ok(wxState.toasts.some((t) => t.title.indexOf('已保存') >= 0));
    assert.strictEqual(p.data.inviteSaving, false);
    ok('保存邀请码 → 相册成功');

    const p2 = makePage();
    p2._qrPath = '/tmp/qr2.png';
    wxState.saveHandler = (o) => o.fail({ errMsg: 'saveImageToPhotosAlbum:fail auth deny' });
    p2.onSaveInviteQr();
    assert.strictEqual(wxState.modals.length, 1);
    assert.ok(wxState.modals[0].content.indexOf('相册权限') >= 0);
    ok('保存邀请码 → 未授权 → 引导设置（长按二维码兜底提示）');
  }

resetWx();
  // ═══ 16. 分享文案 ═══
  {
    const p = makePage();
    const withScore = quickResponse({ score: 92 });
    wxState.responses.push({ statusCode: 200, data: withScore });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onZodiacTap({ currentTarget: { dataset: { key: 'aries' } } });
    p.onStart();
    await sleep(15);
    const share = p.onShareAppMessage();
    assert.ok(share.title.indexOf('92') >= 0 && share.title.indexOf('星光相映 ✦') >= 0);
    assert.ok(share.path.indexOf('meet_id=m-1111') >= 0);
    const noScore = p.onShareAppMessage.call(makePage());
    assert.ok(noScore.title.indexOf('星光相遇了') >= 0);
    ok('分享卡片：分数版 + 无分数兜底 + 直链 path');
  }

resetWx();
  // ═══ 17. 结果页辅助：展开/收起、牌图失败占位、返回表单 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 200, data: quickResponse() });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onZodiacTap({ currentTarget: { dataset: { key: 'aries' } } });
    p.onStart();
    await sleep(15);
    p.onToggleFactors();
    assert.strictEqual(p.data.expandedFactors, true);
    assert.strictEqual(p.data.whyLabel, '收起');
    p.onToggleFactors();
    assert.strictEqual(p.data.expandedFactors, false);
    assert.strictEqual(p.data.whyLabel, '为什么');
    p.onCardImgError({ currentTarget: { dataset: { index: 1 } } });
    assert.strictEqual(p.data.res.cards[1].cardVisible, false);
    assert.strictEqual(p.data.res.cards[1].cardFallback, true);
    p.onBackToForm();
    assert.strictEqual(p.data.step, 'form');
    assert.strictEqual(p.data.submitLabel, '开始合盘 ✦');
    ok('展开「为什么」/ 牌图失败占位（可见性布尔翻转）/ 换一个 TA 再算');
  }

resetWx();
  // ═══ 18. 错误态重试：直链失败后 onRetry 重拉详情 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 404, data: { detail: '相遇记录不存在' } });
    wxState.responses.push({ statusCode: 200, data: { meetings: [] } });
    p.onLoad({ meet_id: 'm-404' });
    await sleep(15);
    wxState.responses.push({ statusCode: 200, data: quickResponse({ meet_id: 'm-404' }) });
    p._meetId = 'm-404';
    p.data.step = 'error';
    p.onRetry();
    await sleep(15);
    assert.ok(wxState.reqLog.some((r) => r.url.endsWith('/meet/m-404')));
    ok('onRetry（detail）→ 重拉详情');
  }

resetWx();
  // ═══ 19. 审查 P1-1 回归：quick 失败时旧 _meetId 残留 → onRetry 回表单，不重载旧详情 ═══
  {
    const p = makePage();
    // 先有旧详情结果（_meetId 残留 + _lastOp='detail'）
    p._meetId = 'm-old';
    // 用户回表单发起新 quick → 失败
    wxState.responses.push({ statusCode: 500, data: { detail: '服务器繁忙' } });
    p.onZodiacTap({ currentTarget: { dataset: { key: 'aries' } } });
    p.onStart();
    await sleep(15);
    assert.strictEqual(p.data.step, 'error');
    assert.strictEqual(p._lastOp, 'quick');
    assert.strictEqual(p.data.submitLabel, '开始合盘 ✦');
    const reqsBefore = wxState.reqLog.length;
    p.onRetry();
    await sleep(15);
    assert.strictEqual(p.data.step, 'form', 'quick 失败重试应回表单');
    assert.strictEqual(wxState.reqLog.length, reqsBefore, '不应触发旧详情请求');
    ok('quick 失败 + 旧 _meetId 残留 → onRetry 回表单（P1-1 修复验证）');
  }

resetWx();
  // ═══ 20. 详情 500 → 错误屏（与 quick 错误态一致），重新连接重拉 ═══
  {
    const p = makePage();
    wxState.responses.push({ statusCode: 500, data: { detail: '服务器繁忙' } });
    p.onLoad({ meet_id: 'm-500' });
    await sleep(15);
    assert.strictEqual(p.data.step, 'error');
    assert.ok(p.data.errorMsg.length > 0);
    wxState.responses.push({ statusCode: 200, data: quickResponse({ meet_id: 'm-500' }) });
    p.onRetry();
    await sleep(15);
    assert.strictEqual(p.data.step, 'result');
    ok('详情 500 → 错误屏 + 重新连接重拉详情');
  }

resetWx();
  // ═══ 21. 邀请 401 → 清 token + 回首页（与 api.js 统一口径） ═══
  {
    const p = makePage();
    wxState.storage.token = 'tok-expired';
    p._meetId = 'm-1111';
    wxState.responses.push({ statusCode: 401, data: Buffer.from(JSON.stringify({ detail: '登录过期' }), 'utf8') });
    p.onInvite();
    await sleep(15);
    assert.strictEqual(p.data.inviting, false);
    assert.strictEqual(p.data.inviteLabel, '邀请 TA 相遇 ✦');
    assert.strictEqual(wxState.storage.token, undefined, 'token 已清除');
    assert.strictEqual(wx.getStorageSync('token'), '', 'getStorageSync 语义与 api.js 一致');
    assert.ok(wxState.navs.some((n) => n.indexOf('RELAUNCH:/pages/index/index') >= 0), 'reLaunch 首页');
    ok('邀请 401 → 清 token + reLaunch 首页');
  }

  console.log(`\nALL PASS: ${pass} 项断言组通过`);
  process.exit(0);
})().catch((e) => {
  console.error('\nFAIL:', e.message);
  console.error(e.stack);
  process.exit(1);
});
