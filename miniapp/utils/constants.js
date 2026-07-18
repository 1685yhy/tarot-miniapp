/**
 * 塔罗小程序全局常量
 * 统一管理花色名称、主题标签、大阿尔卡纳类型等
 */

const { CARD_REGISTRY } = require('./cards');

/** 花色英文 → 中文映射 */
const SUIT_ZH = { wands: '权杖', cups: '圣杯', swords: '宝剑', pentacles: '星币' };

/** 占卜主题 → 中文标签 */
const THEME_LABELS = {
  love: '爱情',
  career: '事业',
  finance: '财运',
  general: '综合',
};

/** 大阿尔卡纳类型列表（从CARD_REGISTRY自动派生） */
const MAJOR_TYPES = Object.values(CARD_REGISTRY).filter(c => c.arcana === "major").map(c => c.type);

module.exports = { SUIT_ZH, THEME_LABELS, MAJOR_TYPES };
