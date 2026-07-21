/**
 * 塔罗卡牌组件 v2.0
 * 全78张CSS艺术卡牌系统
 * 属性：
 *   nameZh       - 中文名称
 *   nameEn       - 英文名称
 *   positionName - 牌阵位置名称
 *   isReversed   - 是否逆位
 *   cardNumber   - 卡牌编号（如 VI, Ace）
 *   cardType     - 卡牌类型标识（可选，自动从nameZh映射）
 */

const { CARD_REGISTRY, findCard, MAJOR_TYPES } = require('../../utils/cards');

Component({
  properties: {
    nameZh: { type: String, value: '命运之轮' },
    nameEn: { type: String, value: '' },
    positionName: { type: String, value: '现在' },
    isReversed: { type: Boolean, value: false },
    cardNumber: { type: String, value: '' },
    cardType: { type: String, value: '' },
    imagePath: { type: String, value: '' },
    flipping: { type: Boolean, value: false },
  },

  data: {
    // cardType is defined in properties — do NOT duplicate here to avoid conflict
    cardNumberDisplay: '',
    displayNameEn: '',
    isMajor: true,
  },

  observers: {
    'nameZh, cardType, nameEn, cardNumber, imagePath': function (nzh, ct, ne, cn, ip) {
      this.resolveCard(nzh, ct, ne, cn, ip);
    },
  },

  lifetimes: {
    attached() {
      this.resolveCard(
        this.properties.nameZh,
        this.properties.cardType,
        this.properties.nameEn,
        this.properties.cardNumber,
        this.properties.imagePath
      );
    },
  },

  methods: {
    resolveCard(nameZh, cardType, nameEn, cardNumber, imagePath) {
      const hasExternalImage = !!imagePath;

      // 如果显式传了cardType，优先使用
      if (cardType) {
        const cardEntry = Object.values(CARD_REGISTRY).find(c => c.type === cardType);
        this.setData({
          cardType,
          cardNumberDisplay: cardNumber || '',
          displayNameEn: nameEn || '',
          isMajor: MAJOR_TYPES.includes(cardType),
          imagePath: hasExternalImage ? imagePath : (cardEntry ? cardEntry.image : ''),
        });
        return;
      }

      // 从nameZh自动映射
      const found = findCard(nameZh);
      if (found) {
        this.setData({
          cardType: found.type,
          cardNumberDisplay: cardNumber || found.number || '',
          displayNameEn: nameEn || found.en || '',
          isMajor: found.arcana === 'major',
          imagePath: hasExternalImage ? imagePath : (found.image || ''),
        });
      } else {
        // 兜底：根据花色生成
        const suitCss = this._guessSuit(nameZh);
        this.setData({
          cardType: suitCss,
          cardNumberDisplay: cardNumber || '',
          displayNameEn: nameEn || '',
          isMajor: false,
          imagePath: hasExternalImage ? imagePath : '',
        });
      }
    },

    _guessSuit(nameZh) {
      if (!nameZh) return 'wands';
      if (nameZh.includes('权杖')) return 'wands';
      if (nameZh.includes('圣杯') || nameZh.includes('杯')) return 'cups';
      if (nameZh.includes('宝剑') || nameZh.includes('剑')) return 'swords';
      if (nameZh.includes('星币') || nameZh.includes('币')) return 'pentacles';
      return 'wands';
    },

    getOrientationText() {
      return this.properties.isReversed ? '逆位' : '正位';
    },

    triggerFlip() {
      this.setData({ flipping: true });
      setTimeout(() => {
        this.setData({ flipping: false });
      }, 800);
    },
  },
});
