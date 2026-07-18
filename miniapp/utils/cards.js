/**
 * 塔罗卡牌数据注册表 & 工具函数
 * 全78张卡牌 + 统一图片路径计算 + 卡牌查找
 */

// ===== 全78张卡牌数据映射 =====
const CARD_REGISTRY = {
  // ---- 大阿尔卡纳 22张 ----
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

  // ---- 权杖 Wands ----
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

  // ---- 圣杯 Cups ----
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

  // ---- 宝剑 Swords ----
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

  // ---- 星币 Pentacles ----
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

// ===== 图像路径映射：计算78张卡牌的真实ComfyUI PNG路径 =====
const IMAGE_BASE = (() => {
  try {
    const env = wx.getAccountInfoSync().miniProgram.envVersion;
    return env === 'develop' ? 'http://localhost:8000/images/cards' : 'https://xingxiang.chat/images/cards_thumb';
  } catch(e) {
    return 'https://xingxiang.chat/images/cards_thumb';
  }
})();

const ROMAN_MAP = {
  '0': 0, 'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
  'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10,
  'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15,
  'XVI': 16, 'XVII': 17, 'XVIII': 18, 'XIX': 19, 'XX': 20, 'XXI': 21
};

// 预计算每张卡牌的图像路径，写入card.image字段
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

// 从CARD_REGISTRY自动构建大阿尔卡纳类型列表
const MAJOR_TYPES = Object.values(CARD_REGISTRY).filter(c => c.arcana === "major").map(c => c.type);

// 用于API返回数据的排名映射
const RANK_MAP = {
  ace: 0, two: 1, three: 2, four: 3, five: 4,
  six: 5, seven: 6, eight: 7, nine: 8, ten: 9,
  page: 10, knight: 11, queen: 12, king: 13,
};

/**
 * 统一图片路径计算
 * 兼容两种数据格式：
 *   1. API返回的卡牌数据（card.card_number, card.name_en）
 *   2. CARD_REGISTRY条目（card.number, card.en）
 * @param {Object} cardData - 卡牌数据对象
 * @param {string} [imageBase] - 可选，覆盖默认图片基础URL
 * @returns {string} 卡牌图片路径
 */
function computeImagePath(cardData, imageBase) {
  if (!cardData) return '';
  const base = imageBase || IMAGE_BASE;
  const enSnake = (cardData.name_en || cardData.en || '').toLowerCase().replace(/\s+/g, '_');
  if (!enSnake) return '';

  if (cardData.arcana === 'major') {
    let idx;
    if (cardData.card_number !== undefined && cardData.card_number !== null) {
      idx = String(cardData.card_number).padStart(2, '0');
    } else if (cardData.number !== undefined) {
      const romanIdx = ROMAN_MAP[cardData.number];
      idx = String(romanIdx !== undefined ? romanIdx : 0).padStart(2, '0');
    } else {
      return '';
    }
    return `${base}/major_${idx}_${enSnake}.png`;
  }

  if (cardData.suit) {
    const firstWord = enSnake.split('_')[0];
    const rankIdx = RANK_MAP[firstWord] !== undefined ? RANK_MAP[firstWord] : 0;
    return `${base}/${cardData.suit}_${String(rankIdx).padStart(2, '0')}_${enSnake}.png`;
  }

  return '';
}

/**
 * 查找卡牌（近似匹配，兼容"圣杯·王牌"这类带分隔符的）
 * @param {string} nameZh - 中文名称
 * @param {string} [nameEn] - 英文名称（预留，暂未使用）
 * @param {string} [cardNumber] - 卡牌编号（预留，暂未使用）
 * @returns {Object|null} 卡牌数据对象或null
 */
function findCard(nameZh, nameEn, cardNumber) {
  if (!nameZh) return null;
  const clean = nameZh.replace(/[·\s　]/g, '').trim();
  // 精确匹配
  if (CARD_REGISTRY[clean]) return CARD_REGISTRY[clean];
  if (CARD_REGISTRY[nameZh.trim()]) return CARD_REGISTRY[nameZh.trim()];
  // 模糊匹配：检查nameZh是否包含某键
  for (const [key, val] of Object.entries(CARD_REGISTRY)) {
    if (clean.includes(key) || key.includes(clean)) return val;
  }
  // 检查是否包含花色关键字
  const suitMap = {
    '权杖': 'wands', '圣杯': 'cups', '宝剑': 'swords', '星币': 'pentacles',
  };
  for (const [sk, sv] of Object.entries(suitMap)) {
    if (nameZh.includes(sk)) {
      return { type: sv, number: '', en: nameZh, arcana: 'minor', suit: sv };
    }
  }
  return null;
}

module.exports = { CARD_REGISTRY, computeImagePath, findCard, MAJOR_TYPES };
