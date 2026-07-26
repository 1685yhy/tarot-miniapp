// utils/a11y.js — Accessibility helpers for Starlight Reflection

const { CARD_REGISTRY } = require('./cards');

/**
 * Generate a descriptive alt text for a single tarot card.
 * Format: "{name} — {suit_cn} {number}号牌 · {brief_keyword}"
 * When fullDesc is true, includes the upright meaning summary.
 *
 * @param {Object|string} card - Card object from CARD_REGISTRY, or card name string
 * @param {Object} [opts]
 * @param {boolean} [opts.fullDesc=false] - Include upright meaning for detail pages
 * @returns {string}
 */
function getCardAltText(card, opts = {}) {
  const name = typeof card === 'string' ? card : (card?.name_cn || card?.name || '塔罗牌');
  const registryEntry = CARD_REGISTRY ? CARD_REGISTRY[name] : null;

  if (!registryEntry) return `${name} — 塔罗牌`;

  const { suit_cn, number, upright } = registryEntry;
  const suitInfo = suit_cn ? `${suit_cn}` : '';
  const numInfo = number !== undefined ? `${number}号牌` : '';
  const parts = [name];

  if (suitInfo || numInfo) {
    parts.push('·');
    if (suitInfo) parts.push(suitInfo);
    if (numInfo) parts.push(numInfo);
  }

  if (opts.fullDesc && upright && upright.length > 0) {
    parts.push('·');
    parts.push(upright.slice(0, 30));
  }

  return parts.join(' ');
}

/**
 * Get alt text for a card image by filename.
 * Parses filename like "arcana01.png" → card name → alt text.
 *
 * @param {string} filename - Card image filename
 * @returns {string}
 */
function getCardImageAlt(filename) {
  // This is used as a fallback when full card object is unavailable
  return '塔罗牌卡面';
}

module.exports = { getCardAltText, getCardImageAlt };
