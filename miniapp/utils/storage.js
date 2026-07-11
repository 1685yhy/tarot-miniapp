const STORAGE_KEYS = {
  TOKEN: 'token',
  USER: 'user',
  DAILY_CARD: 'dailyCard',
  READING_HISTORY: 'readingHistory',
  SETTINGS: 'settings',
};

const set = (key, value) => {
  try {
    wx.setStorageSync(key, JSON.stringify(value));
    return true;
  } catch (e) {
    console.error('Storage set error:', e);
    return false;
  }
};

const get = (key) => {
  try {
    const value = wx.getStorageSync(key);
    if (value === '') return null;
    return JSON.parse(value);
  } catch (e) {
    console.error('Storage get error:', e);
    return null;
  }
};

const remove = (key) => {
  try {
    wx.removeStorageSync(key);
    return true;
  } catch (e) {
    console.error('Storage remove error:', e);
    return false;
  }
};

const clear = () => {
  try {
    wx.clearStorageSync();
    return true;
  } catch (e) {
    console.error('Storage clear error:', e);
    return false;
  }
};

module.exports = {
  STORAGE_KEYS,
  set,
  get,
  remove,
  clear,
};
