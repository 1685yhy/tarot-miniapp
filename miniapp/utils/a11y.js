// utils/a11y.js — Accessibility helpers for Starlight Reflection

const { CARD_REGISTRY } = require('./cards');

// Build reverse map: English snake_case → Chinese card name
// Used by getCardImageAlt to resolve filenames to card names.
const _EN_SNAKE_TO_CN = {};
(function _buildReverseMap() {
  if (!CARD_REGISTRY) return;
  for (const [cn, card] of Object.entries(CARD_REGISTRY)) {
    if (card.en) {
      const enSnake = card.en.toLowerCase().replace(/\s+/g, '_');
      _EN_SNAKE_TO_CN[enSnake] = cn;
    }
  }
})();

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
 * Parses filename like "major_00_the_fool.png" or "wands_00_ace_of_wands.png"
 * → extracts the English snake_case name → looks up Chinese name.
 *
 * @param {string} filename - Card image filename
 * @returns {string}
 */
function getCardImageAlt(filename) {
  if (!filename) return '塔罗牌卡面';

  // Try extracting the English snake_case name from:
  //   major_00_the_fool.png  →  the_fool
  //   wands_00_ace_of_wands.png  →  ace_of_wands
  const match = filename.match(/^(?:\w+)_\d+_(.+)\.\w+$/);
  if (match) {
    const enSnake = match[1];
    const cnName = _EN_SNAKE_TO_CN[enSnake];
    if (cnName) return `${cnName} — 塔罗牌`;
  }

  // Fallback: return the generic description
  return '塔罗牌卡面';
}

module.exports = { getCardAltText, getCardImageAlt };
