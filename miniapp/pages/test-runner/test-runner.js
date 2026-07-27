// pages/test-runner/test-runner.js
// 自动化页面遍历测试 — 在 IDE 中编译后访问此页面即可运行

const PAGES = [
  { name: '首页 (Tab)', path: '/pages/index/index', isTab: true },
  { name: '百科 (Tab)', path: '/pages/encyclopedia/encyclopedia', isTab: true },
  { name: '我的 (Tab)', path: '/pages/profile/profile', isTab: true },
  { name: '签到', path: '/pages/checkin/checkin' },
  { name: '日记', path: '/pages/diary/diary' },
  { name: '会员', path: '/pages/membership/membership' },
  { name: '分享中心', path: '/pages/share-center/share-center' },
  { name: '占卜', path: '/pages/reading/reading' },
  { name: '每日一牌', path: '/pages/daily-card/daily-card' },
  { name: '年度报告', path: '/pages/annual-report/annual-report' },
];

Page({
  data: {
    PAGES,
    results: [],
    current: -1,
    running: false,
    done: false,
    totalPages: PAGES.length,
    passedCount: 0,
    failedCount: 0,
  },

  onLoad() {
    this._errors = [];
    // Intercept console.error
    this._origError = console.error;
    const self = this;
    console.error = function (...args) {
      self._errors.push(args.map(String).join(' ').substring(0, 200));
      self._origError.apply(console, args);
    };
  },

  onUnload() {
    console.error = this._origError;
  },

  async startTest() {
    this.setData({ running: true, results: [], current: 0, passedCount: 0, failedCount: 0 });

    for (let i = 0; i < PAGES.length; i++) {
      const page = PAGES[i];
      this._errors = [];
      this.setData({ current: i });

      await new Promise((resolve) => {
        const nav = page.isTab ? wx.switchTab : wx.navigateTo;
        nav.call(wx, {
          url: page.path,
          success: () => setTimeout(resolve, 2000),
          fail: (e) => {
            this._errors.push('导航失败: ' + (e.errMsg || JSON.stringify(e)));
            resolve();
          }
        });
      });

      const errors = [...this._errors];
      const pageResult = {
        name: page.name,
        path: page.path,
        errors,
      };

      const resultList = this.data.results.concat(pageResult);
      if (errors.length === 0) {
        this.setData({
          results: resultList,
          passedCount: this.data.passedCount + 1
        });
      } else {
        this.setData({
          results: resultList,
          failedCount: this.data.failedCount + 1
        });
      }

      await new Promise(r => setTimeout(r, 500));
    }

    this.setData({ done: true, running: false });
    console.error = this._origError;
  },

  onPageTap(e) {
    const idx = e.currentTarget.dataset.index;
    const page = PAGES[idx];
    const nav = page.isTab ? wx.switchTab : wx.navigateTo;
    nav.call(wx, { url: page.path });
  },
});
