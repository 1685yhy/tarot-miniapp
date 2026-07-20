/**
 * 行动建议卡片组件 — Action Cards
 *
 * 解读结果页底部展示 3 条可勾选的行动建议。
 * - 勾选状态自动保存到 wx.Storage，恢复后保持
 * - 全部完成时触发庆祝动画（三颗星依次亮起）
 *
 * Properties:
 *   items     - Array<{id, content, category}> 行动建议列表
 *   readingId - String 解读 ID，用于 Storage 键隔离
 *
 * Events:
 *   allchecked - 全部完成时触发（便于父页面做额外处理）
 */
Component({
  properties: {
    items: {
      type: Array,
      value: [],
      observer: '_onItemsChange',
    },
    readingId: {
      type: String,
      value: '',
    },
  },

  data: {
    checkedItems: {},     // {id: true/false} 勾选状态
    checkedCount: 0,      // 已勾选数量
    allDone: false,       // 是否全部完成
    loading: true,        // 初始加载中
  },

  lifetimes: {
    attached() {
      this._loadState();
    },
  },

  methods: {
    /* ---------------------------------------------------------------
       Initialize: load saved state from Storage
       --------------------------------------------------------------- */
    _loadState() {
      this.setData({ loading: true });

      const items = this.properties.items || [];
      if (items.length === 0) {
        this.setData({ loading: false });
        return;
      }

      const readingId = this.properties.readingId;
      if (!readingId) {
        // No readingId — start fresh
        this.setData({
          checkedItems: {},
          checkedCount: 0,
          allDone: false,
          loading: false,
        });
        return;
      }

      // Load saved state from Storage
      const storageKey = `action_checks_${readingId}`;
      try {
        const saved = wx.getStorageSync(storageKey) || {};
        const checkedItems = {};
        let checkedCount = 0;

        items.forEach((item) => {
          const isChecked = saved[item.id] === true;
          checkedItems[item.id] = isChecked;
          if (isChecked) checkedCount += 1;
        });

        const allDone = checkedCount === items.length && items.length > 0;

        this.setData({
          checkedItems,
          checkedCount,
          allDone,
          loading: false,
        });
      } catch (err) {
        console.warn('[action-cards] Failed to load state from Storage:', err);
        this.setData({
          checkedItems: {},
          checkedCount: 0,
          allDone: false,
          loading: false,
        });
      }
    },

    /* ---------------------------------------------------------------
       Re-initialize when items change
       --------------------------------------------------------------- */
    _onItemsChange(newItems) {
      // If we already have state loaded and items changed, recalc
      if (!this.data.loading && newItems && newItems.length > 0) {
        this._loadState();
      }
    },

    /* ---------------------------------------------------------------
       Toggle check state on tap
       --------------------------------------------------------------- */
    onToggle(e) {
      const id = e.currentTarget.dataset.id;
      if (!id) return;

      const checkedItems = { ...this.data.checkedItems };
      const items = this.properties.items;

      // Toggle
      const newState = !checkedItems[id];
      checkedItems[id] = newState;

      // Recalculate counts
      let checkedCount = 0;
      items.forEach((item) => {
        if (checkedItems[item.id]) checkedCount += 1;
      });

      const allDone = checkedCount === items.length && items.length > 0;

      this.setData({ checkedItems, checkedCount, allDone });

      // Persist to Storage
      this._saveState(checkedItems);

      // Fire event if all done
      if (allDone) {
        this.triggerEvent('allchecked', { readingId: this.properties.readingId });
      }
    },

    /* ---------------------------------------------------------------
       Save current state to wx.Storage
       --------------------------------------------------------------- */
    _saveState(checkedItems) {
      const readingId = this.properties.readingId;
      if (!readingId) return;

      const storageKey = `action_checks_${readingId}`;
      try {
        wx.setStorageSync(storageKey, checkedItems);
      } catch (err) {
        console.warn('[action-cards] Failed to save state to Storage:', err);
      }
    },

    /* ---------------------------------------------------------------
       Share — trigger parent to handle share
       --------------------------------------------------------------- */
    onShare() {
      const items = this.properties.items || [];
      const checkedItems = this.data.checkedItems;

      // Build action text for sharing
      const completedText = items
        .filter((item) => checkedItems[item.id])
        .map((item) => `✓ ${item.content}`)
        .join('\n');

      this.triggerEvent('share', {
        readingId: this.properties.readingId,
        completedText,
        completedCount: this.data.checkedCount,
        totalCount: items.length,
      });
    },
  },
});
