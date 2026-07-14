// pages/profile/profile.js
const { request } = require('../../utils/api');
const { checkLogin } = require('../../utils/auth');

// 牌阵英文键名到中文显示名的映射
const SPREAD_TYPE_NAMES = {
  three_card: '三张牌',
  celtic_cross: '凯尔特十字',
  daily: '每日占卜',
  relationship: '关系分析',
  career_path: '事业路线',
  weekly_outlook: '周运势',
  love_reading: '爱情占卜',
  fortune_telling: '财运占卜',
};

// ===== 卡牌图像路径计算（与 tarot-card.js 同步） =====
const CARD_REGISTRY = {
  '愚者':     { type: 'fool', number: '0', en: 'The Fool', arcana: 'major' },
  '魔术师':   { type: 'magician', number: 'I', en: 'The Magician', arcana: 'major' },
  '女祭司':   { type: 'high-priestess', number: 'II', en: 'The High Priestess', arcana: 'major' },
  '女皇':     { type: 'empress', number: 'III', en: 'The Empress', arcana: 'major' },
  '皇帝':     { type: 'emperor', number: 'IV', en: 'The Emperor', arcana: 'major' },
  '教皇':     { type: 'hierophant', number: 'V', en: 'The Hierophant', arcana: 'major' },
  '恋人':     { type: 'lovers', number: 'VI', en: 'The Lovers', arcana: 'major' },
  '战车':     { type: 'chariot', number: 'VII', en: 'The Chariot', arcana: 'major' },
  '力量':     { type: 'strength', number: 'VIII', en: 'Strength', arcana: 'major' },
  '隐士':     { type: 'hermit', number: 'IX', en: 'The Hermit', arcana: 'major' },
  '命运之轮': { type: 'wheel-of-fortune', number: 'X', en: 'Wheel of Fortune', arcana: 'major' },
  '正义':     { type: 'justice', number: 'XI', en: 'Justice', arcana: 'major' },
  '倒吊人':   { type: 'hanged-man', number: 'XII', en: 'The Hanged Man', arcana: 'major' },
  '死神':     { type: 'death', number: 'XIII', en: 'Death', arcana: 'major' },
  '节制':     { type: 'temperance', number: 'XIV', en: 'Temperance', arcana: 'major' },
  '恶魔':     { type: 'devil', number: 'XV', en: 'The Devil', arcana: 'major' },
  '高塔':     { type: 'tower', number: 'XVI', en: 'The Tower', arcana: 'major' },
  '星星':     { type: 'star', number: 'XVII', en: 'The Star', arcana: 'major' },
  '月亮':     { type: 'moon', number: 'XVIII', en: 'The Moon', arcana: 'major' },
  '太阳':     { type: 'sun', number: 'XIX', en: 'The Sun', arcana: 'major' },
  '审判':     { type: 'judgement', number: 'XX', en: 'Judgement', arcana: 'major' },
  '世界':     { type: 'world', number: 'XXI', en: 'The World', arcana: 'major' },
  '权杖王牌': { type: 'ace-wands', number: 'Ace', en: 'Ace of Wands', arcana: 'minor', suit: 'wands' },
  '权杖二':   { type: '2-wands', number: 'II', en: 'Two of Wands', arcana: 'minor', suit: 'wands' },
  '权杖三':   { type: '3-wands', number: 'III', en: 'Three of Wands', arcana: 'minor', suit: 'wands' },
  '权杖四':   { type: '4-wands', number: 'IV', en: 'Four of Wands', arcana: 'minor', suit: 'wands' },
  '权杖五':   { type: '5-wands', number: 'V', en: 'Five of Wands', arcana: 'minor', suit: 'wands' },
  '权杖六':   { type: '6-wands', number: 'VI', en: 'Six of Wands', arcana: 'minor', suit: 'wands' },
  '权杖七':   { type: '7-wands', number: 'VII', en: 'Seven of Wands', arcana: 'minor', suit: 'wands' },
  '权杖八':   { type: '8-wands', number: 'VIII', en: 'Eight of Wands', arcana: 'minor', suit: 'wands' },
  '权杖九':   { type: '9-wands', number: 'IX', en: 'Nine of Wands', arcana: 'minor', suit: 'wands' },
  '权杖十':   { type: '10-wands', number: 'X', en: 'Ten of Wands', arcana: 'minor', suit: 'wands' },
  '权杖侍卫': { type: 'page-wands', number: 'P', en: 'Page of Wands', arcana: 'minor', suit: 'wands' },
  '权杖骑士': { type: 'knight-wands', number: 'Kt', en: 'Knight of Wands', arcana: 'minor', suit: 'wands' },
  '权杖王后': { type: 'queen-wands', number: 'Q', en: 'Queen of Wands', arcana: 'minor', suit: 'wands' },
  '权杖国王': { type: 'king-wands', number: 'K', en: 'King of Wands', arcana: 'minor', suit: 'wands' },
  '圣杯王牌':  { type: 'ace-cups', number: 'Ace', en: 'Ace of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯二':    { type: '2-cups', number: 'II', en: 'Two of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯三':    { type: '3-cups', number: 'III', en: 'Three of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯四':    { type: '4-cups', number: 'IV', en: 'Four of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯五':    { type: '5-cups', number: 'V', en: 'Five of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯六':    { type: '6-cups', number: 'VI', en: 'Six of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯七':    { type: '7-cups', number: 'VII', en: 'Seven of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯八':    { type: '8-cups', number: 'VIII', en: 'Eight of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯九':    { type: '9-cups', number: 'IX', en: 'Nine of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯十':    { type: '10-cups', number: 'X', en: 'Ten of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯侍卫':  { type: 'page-cups', number: 'P', en: 'Page of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯骑士':  { type: 'knight-cups', number: 'Kt', en: 'Knight of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯王后':  { type: 'queen-cups', number: 'Q', en: 'Queen of Cups', arcana: 'minor', suit: 'cups' },
  '圣杯国王':  { type: 'king-cups', number: 'K', en: 'King of Cups', arcana: 'minor', suit: 'cups' },
  '宝剑王牌':  { type: 'ace-swords', number: 'Ace', en: 'Ace of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑二':    { type: '2-swords', number: 'II', en: 'Two of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑三':    { type: '3-swords', number: 'III', en: 'Three of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑四':    { type: '4-swords', number: 'IV', en: 'Four of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑五':    { type: '5-swords', number: 'V', en: 'Five of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑六':    { type: '6-swords', number: 'VI', en: 'Six of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑七':    { type: '7-swords', number: 'VII', en: 'Seven of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑八':    { type: '8-swords', number: 'VIII', en: 'Eight of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑九':    { type: '9-swords', number: 'IX', en: 'Nine of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑十':    { type: '10-swords', number: 'X', en: 'Ten of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑侍卫':  { type: 'page-swords', number: 'P', en: 'Page of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑骑士':  { type: 'knight-swords', number: 'Kt', en: 'Knight of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑王后':  { type: 'queen-swords', number: 'Q', en: 'Queen of Swords', arcana: 'minor', suit: 'swords' },
  '宝剑国王':  { type: 'king-swords', number: 'K', en: 'King of Swords', arcana: 'minor', suit: 'swords' },
  '星币王牌':  { type: 'ace-pentacles', number: 'Ace', en: 'Ace of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币二':    { type: '2-pentacles', number: 'II', en: 'Two of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币三':    { type: '3-pentacles', number: 'III', en: 'Three of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币四':    { type: '4-pentacles', number: 'IV', en: 'Four of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币五':    { type: '5-pentacles', number: 'V', en: 'Five of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币六':    { type: '6-pentacles', number: 'VI', en: 'Six of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币七':    { type: '7-pentacles', number: 'VII', en: 'Seven of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币八':    { type: '8-pentacles', number: 'VIII', en: 'Eight of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币九':    { type: '9-pentacles', number: 'IX', en: 'Nine of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币十':    { type: '10-pentacles', number: 'X', en: 'Ten of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币侍卫':  { type: 'page-pentacles', number: 'P', en: 'Page of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币骑士':  { type: 'knight-pentacles', number: 'Kt', en: 'Knight of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币王后':  { type: 'queen-pentacles', number: 'Q', en: 'Queen of Pentacles', arcana: 'minor', suit: 'pentacles' },
  '星币国王':  { type: 'king-pentacles', number: 'K', en: 'King of Pentacles', arcana: 'minor', suit: 'pentacles' },
};

const IMAGE_BASE = (() => {
  try {
    const info = wx.getAccountInfoSync();
    const env = info.miniProgram ? info.miniProgram.envVersion : 'release';
    return env === 'develop' ? 'http://xingxiang.chat/images/cards' : 'https://xingxiang.chat/images/cards';
  } catch {
    return 'https://xingxiang.chat/images/cards';
  }
})();
const ROMAN_MAP = {
  '0': 0, 'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
  'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
  'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
  'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20, 'XXI': 21
};

(function computeImagePaths() {
  const suitCounters = { wands: 0, cups: 0, swords: 0, pentacles: 0 };
  Object.values(CARD_REGISTRY).forEach(card => {
    const enSnake = card.en.toLowerCase().replace(/\s+/g, '_');
    if (card.arcana === 'major') {
      const idx = ROMAN_MAP[card.number] !== undefined ? ROMAN_MAP[card.number] : 0;
      card.image = `${IMAGE_BASE}/major_${String(idx).padStart(2, '0')}_${enSnake}.png`;
    } else if (card.suit && suitCounters[card.suit] !== undefined) {
      const idx = suitCounters[card.suit]++;
      card.image = `${IMAGE_BASE}/${card.suit}_${String(idx).padStart(2, '0')}_${enSnake}.png`;
    }
  });
})();

function findCard(nameZh) {
  if (!nameZh) return null;
  const clean = nameZh.replace(/[·\s　]/g, '').trim();
  if (CARD_REGISTRY[clean]) return CARD_REGISTRY[clean];
  if (CARD_REGISTRY[nameZh.trim()]) return CARD_REGISTRY[nameZh.trim()];
  for (const [key, val] of Object.entries(CARD_REGISTRY)) {
    if (clean.includes(key) || key.includes(clean)) return val;
  }
  return null;
}

function computeCardImage(firstCardName) {
  if (!firstCardName) return '';
  const found = findCard(firstCardName);
  return found && found.image ? found.image : '';
}

Page({
  data: {
    user: null,
    memberStatus: null,
    readingHistory: [],
    pageLoading: true,
    pageError: null,
    historyPage: 1,
    hasMore: true,
    loadingMore: false,
    historyTotal: 0,
    spreadTypeNames: SPREAD_TYPE_NAMES,
  },

  async onShow() {
    await this.loadData();
  },

  async loadData() {
    this.setData({ pageLoading: true });
    try {
      const user = await checkLogin();
      const [status, history] = await Promise.all([
        request('/membership/status'),
        request('/readings/history?page=1&page_size=20'),
      ]);
      this.setData({
        user,
        memberStatus: status ? {
          ...status,
          expiresAtFormatted: status.expires_at ? status.expires_at.split('T')[0] : '',
        } : null,
        readingHistory: (history.items || []).map(item => ({
          ...item,
          spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
          firstCardImage: computeCardImage(item.first_card_name),
        })),
        historyTotal: history.total || (history.items ? history.items.length : 0),
        pageLoading: false,
        historyPage: 1,
        hasMore: history.items ? history.items.length >= 20 : false,
      });
    } catch (err) {
      this.setData({ pageLoading: false, pageError: err.message || '加载失败' });
    }
  },

  async onScrollToBottom() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    const nextPage = this.data.historyPage + 1;
    try {
      const history = await request(`/readings/history?page=${nextPage}&page_size=20`);
      this.setData({
        readingHistory: this.data.readingHistory.concat(
          (history.items || []).map(item => ({
            ...item,
            spreadTypeName: SPREAD_TYPE_NAMES[item.spread_type] || item.spread_type,
            firstCardImage: computeCardImage(item.first_card_name),
          }))
        ),
        historyPage: nextPage,
        hasMore: history.items ? history.items.length >= 20 : false,
        loadingMore: false,
      });
    } catch (err) {
      this.setData({ loadingMore: false });
      wx.showToast({ title: '加载更多失败', icon: 'none' });
    }
  },

  onRetry() {
    this.setData({ pageError: null, pageLoading: true });
    this.loadData();
  },

  onGoMembership() {
    wx.navigateTo({ url: '/pages/membership/membership' });
  },

  onViewReading(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/reading-result/reading-result?id=${id}` });
  },

  onGoDiary() {
    wx.navigateTo({ url: '/pages/diary/diary' });
  },

  onGoAnnualReport() {
    wx.navigateTo({ url: '/pages/annual-report/annual-report' });
  },

  onGoAbout() {
    wx.showModal({
      title: '关于我们',
      content: '星光塔罗 — 用星辰的智慧指引你的前行之路。\n\n版本 1.0.0',
      showCancel: false,
    });
  },

  async onClearHistory() {
    const res = await new Promise((resolve) => {
      wx.showModal({
        title: '清除记录',
        content: '确定清除所有占卜历史记录吗？此操作不可恢复。',
        success: resolve,
      });
    });
    if (!res.confirm) return;

    try {
      await request('/readings/history', { method: 'DELETE' });
      this.setData({ readingHistory: [] });
      wx.showToast({ title: '已清除', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: '清除失败', icon: 'none' });
    }
  },
});
