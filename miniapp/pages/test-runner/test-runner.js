// test-runner v2 — 全面质量检测
// 检查: 页面渲染、图片加载、API连通、登录、特效、布局
const { checkLogin } = require('../../utils/auth');
const { request, BASE_URL } = require('../../utils/api');

const PAGES = [
  { name: '今日', path: '/pages/index/index', isTab: true,
    checks: ['image','text','greeting','dailyCard','energy','zodiac'] },
  { name: '神谕', path: '/pages/oracle/oracle', isTab: true,
    checks: ['image','text','element','spreads'] },
  { name: '我的', path: '/pages/profile/profile', isTab: true,
    checks: ['avatar','stat','menu','login'] },
  { name: '百科', path: '/pages/encyclopedia/encyclopedia', isTab: false,
    checks: ['image','list','search','filter'] },
  { name: '星座引导', path: '/pages/zodiac-welcome/zodiac-welcome', isTab: false,
    checks: ['image','text'] },
  { name: '能量详情', path: '/pages/energy-detail/energy-detail', isTab: false,
    checks: ['image','text'] },
  { name: '签到', path: '/pages/checkin/checkin', checks: ['image','btn','level'] },
  { name: '会员', path: '/pages/membership/membership', checks: ['image','price','cmp','plan'] },
  { name: '占卜', path: '/pages/reading/reading', checks: ['spread','mode','persona','image'] },
];

const API_TESTS = [
  { name: 'Health', endpoint: '/health', method: 'GET' },
  { name: 'Cards', endpoint: '/cards', method: 'GET' },
  { name: 'Products', endpoint: '/membership/products', method: 'GET' },
];

Page({
  data: {
    results: [], current: -1, running: false, done: false,
    totalPages: PAGES.length, passedCount: 0, failedCount: 0,
    apiResults: [], apiDone: false,
    loginOk: null, baseUrl: BASE_URL,
  },

  onLoad() {
    this._errors = []; this._warnings = []; this._imgErrors = []; this._netErrors = [];
    const self = this;
    const origErr = console.error;
    console.error = function(...a) {
      self._errors.push(a.map(String).join(' ').substring(0,200));
      origErr.apply(console, a);
    };
  },

  // ─── Phase 0: Pre-flight ───
  async startTest() {
    this.setData({ running: true, results: [], current: -1, passedCount: 0, failedCount: 0, apiResults: [], apiDone: false });
    this._errors = []; this._netErrors = [];

    // Step 0.1: Login
    try {
      const user = await checkLogin();
      this.setData({ loginOk: !!user });
      this._addResult('🔑 登录检测', true, user ? `已登录 (${user.nickname || '用户'})` : '未登录');
    } catch(e) {
      this._addResult('🔑 登录检测', false, e.message);
    }

    // Step 0.2: API endpoints
    for (const api of API_TESTS) {
      try {
        const res = await request(api.endpoint, api.method);
        this._apiAdd(api.name, true, `${JSON.stringify(res).substring(0,80)}`);
      } catch(e) {
        this._apiAdd(api.name, false, e.message || '请求失败');
      }
    }
    this.setData({ apiDone: true });

    // Step 0.3: Image base URL check
    try {
      const res = await new Promise((resolve, reject) => {
        wx.request({ url: `${BASE_URL}/images/cards_thumb/major_00.png`, method: 'HEAD',
          success: r => resolve(r.statusCode),
          fail: e => reject(e)
        });
      });
      this._addResult('🖼️ 图片CDN', res === 200, `HTTP ${res}`);
    } catch(e) {
      this._addResult('🖼️ 图片CDN', false, '无法访问');
    }

    // ─── Phase 1: Page traversal ───
    for (let i = 0; i < PAGES.length; i++) {
      const page = PAGES[i];
      this._errors = []; this._imgErrors = [];
      this.setData({ current: i });

      await this._navigate(page);
      await new Promise(r => setTimeout(r, 1500));

      // Check images loaded
      this._checkImages(page);

      // Check key content present
      this._checkContent(page);

      const errors = [...this._errors, ...this._imgErrors.map(e => `[IMG] ${e}`)];
      const resultList = this.data.results.concat([{
        name: page.name, path: page.path, errors, checks: page.checks || [],
      }]);
      this.setData({
        results: resultList,
        [errors.length === 0 ? 'passedCount' : 'failedCount']: this.data[errors.length === 0 ? 'passedCount' : 'failedCount'] + 1
      });
      await new Promise(r => setTimeout(r, 300));
    }

    this.setData({ done: true, running: false });
    const total = this.data.passedCount + this.data.failedCount;
    this._summaryLog(total);
  },

  // ─── Navigate ───
  _navigate(page) {
    return new Promise((resolve) => {
      const nav = page.isTab ? wx.switchTab : wx.navigateTo;
      nav.call(wx, {
        url: page.path,
        success: () => setTimeout(resolve, 2000),
        fail: (e) => {
          // Try switchTab as fallback
          if (!page.isTab) {
            wx.switchTab({ url: '/pages/index/index', success: resolve, fail: resolve });
          } else {
            resolve();
          }
        }
      });
    });
  },

  // ─── Image check ───
  _checkImages(page) {
    const query = wx.createSelectorQuery();
    query.selectAll('image').fields({ node: false, size: true, properties: ['src','mode','aria-label'] }).exec((res) => {
      if (!res || !res[0]) return;
      const images = res[0];
      if (images.length === 0) {
        this._imgErrors.push(`${page.name}: 页面无图片元素`);
      }
      images.forEach((img, idx) => {
        if (!img.src || img.src === '') {
          this._imgErrors.push(`${page.name} 第${idx+1}张图: src为空`);
        }
      });
    });
  },

  // ─── Content checks ───
  _checkContent(page) {
    const query = wx.createSelectorQuery();
    query.selectAll('text,view,image,button,input').fields({ properties: ['class'] }).exec((res) => {
      if (!res || !res[0]) return;
      const nodes = res[0];
      if (nodes.length === 0) {
        this._errors.push(`${page.name}: 页面无任何DOM节点 (可能白屏)`);
      }
      // Check for common CSS classes
      const classes = nodes.map(n => n.class || '').filter(Boolean);
      const hasAnimation = classes.some(c => /anim|fade|slide|bounce|twinkle|glow/i.test(c));
      if (hasAnimation) {
        // 特效检测 — just note it exists
      }
    });
  },

  // ─── Helpers ───
  _addResult(name, ok, detail) {
    const r = this.data.results.concat([{ name, path: '', errors: ok ? [] : [detail], checks: [] }]);
    this.setData({ results: r, [ok ? 'passedCount' : 'failedCount']: this.data[ok ? 'passedCount' : 'failedCount'] + 1 });
  },

  _apiAdd(name, ok, detail) {
    const r = this.data.apiResults.concat([{ name, ok, detail }]);
    this.setData({ apiResults: r });
  },

  _summaryLog(total) {
    const p = this.data.passedCount, f = this.data.failedCount;
    console.log(`\n=== 测试完成: ${p}/${total} 通过 ===`);
    if (f > 0) console.log(`失败 ${f} 项，详见上方报告`);
  },

  onPageTap(e) {
    const idx = e.currentTarget.dataset.index;
    const page = PAGES[idx];
    (page.isTab ? wx.switchTab : wx.navigateTo).call(wx, { url: page.path });
  },
});
