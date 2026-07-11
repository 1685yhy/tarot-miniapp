/**
 * 塔罗卡牌组件
 * 神秘风格可复用的卡牌展示组件
 *
 * 属性：
 *   nameZh       - 中文名称
 *   nameEn       - 英文名称
 *   positionName - 牌阵位置名称（如"过去""现在""未来"）
 *   isReversed   - 是否逆位
 *   cardNumber   - 卡牌编号（罗马数字）
 */
Component({
  /**
   * 组件属性列表
   */
  properties: {
    nameZh: {
      type: String,
      value: '命运之轮',
    },
    nameEn: {
      type: String,
      value: 'The Wheel',
    },
    positionName: {
      type: String,
      value: '现在',
    },
    isReversed: {
      type: Boolean,
      value: false,
    },
    cardNumber: {
      type: String,
      value: 'X',
    },
  },

  /**
   * 组件的初始数据
   */
  data: {
    appeared: false,
  },

  /**
   * 组件生命周期
   */
  lifetimes: {
    attached() {
      // 延迟触发入场动画
      const timer = setTimeout(() => {
        this.setData({ appeared: true });
      }, 100);
      this._timer = timer;
    },

    detached() {
      if (this._timer) {
        clearTimeout(this._timer);
      }
    },
  },

  /**
   * 组件的方法列表
   */
  methods: {
    /**
     * 获取卡牌状态描述
     * @returns {string} 正位/逆位描述
     */
    getOrientationText() {
      return this.properties.isReversed ? '逆位' : '正位';
    },
  },
});
