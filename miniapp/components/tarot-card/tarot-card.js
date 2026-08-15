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

const { CARD_REGISTRY, findCard, MAJOR_TYPES, pngFallbackPath } = require('../../utils/cards');

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
    // 结果页等首屏牌面不懒加载（lazy-load 在动画容器内有概率不触发导致空白）
    lazy: { type: Boolean, value: true },
  },

  data: {
    // cardType is defined in properties — do NOT duplicate here to avoid conflict
    cardNumberDisplay: '',
    displayNameEn: '',
    isMajor: true,
    cardImgError: false,
  },

  // 回归修复: observer 只能监听「输入」属性(nameZh/nameEn/cardNumber)。
  // 原实现同时监听了 cardType/imagePath —— 而 resolveCard 内部会 setData 这两个字段,
  // 导致 observer→resolveCard→setData→observer 无限递归, 在真机/模拟器上都会
  // 卡死页面(灰屏+JS线程冻结)。
  observers: {
    'nameZh, nameEn, cardNumber': function (nzh, ne, cn) {
      this.resolveCard(nzh, this.properties.cardType, ne, cn, this.properties.imagePath);
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
    detached() {
      if (this._flipTimer) {
        clearTimeout(this._flipTimer);
        this._flipTimer = null;
      }
    },
  },

  methods: {
    resolveCard(nameZh, cardType, nameEn, cardNumber, imagePath) {
      const hasExternalImage = !!imagePath;

      // Reset card image error state when resolving a new card
      this.setData({ cardImgError: false, webpFallbackTried: false });

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

    /** Handle card image load error — retry once with PNG fallback, then show CSS fallback */
    onCardImgError() {
      const current = this.data.imagePath || '';
      if (current.endsWith('.webp') && !this.data.webpFallbackTried) {
        this.setData({ webpFallbackTried: true, imagePath: pngFallbackPath(current) });
        return;
      }
      this.setData({ cardImgError: true });
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
      this._flipTimer = setTimeout(() => {
        this.setData({ flipping: false });
        this._flipTimer = null;
      }, 800);
    },
  },
});
