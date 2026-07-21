// 音效管理器 — 抽牌沉浸感
// 全部使用程序化合成 (Web Audio API)，无需外部音频文件
// 低端设备自动降级为振动反馈

let sfxEnabled = true;

// 从 wx.Storage 读取偏好
try {
  sfxEnabled = wx.getStorageSync('sfx_enabled') !== false;
} catch(e) {}

/**
 * 安全获取 Web Audio 上下文，不支持时返回 null
 */
function _getAudioCtx() {
  try {
    return wx.createWebAudioContext();
  } catch(e) {
    return null;
  }
}

/**
 * 生成纯音音调
 */
function generateTone(frequency, duration, type = 'sine', volume = 0.3) {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = frequency;
    gain.gain.value = volume;
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch(e) {}
}

/**
 * 降级振动反馈
 */
function _fallbackVibrate(type = 'light') {
  try { wx.vibrateShort({ type }); } catch(e) {}
}

/**
 * 洗牌音 — 短促白噪声
 */
function playCardDrawSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) { _fallbackVibrate('light'); return; }
    const bufferSize = ctx.sampleRate * 0.12;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / bufferSize, 2);
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const gain = ctx.createGain();
    gain.gain.value = 0.06;
    source.connect(gain);
    gain.connect(ctx.destination);
    source.start();
  } catch(e) { _fallbackVibrate('light'); }
}

/**
 * 揭示音 — 上升双音 (C5→E6)
 */
function playCardRevealSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) { _fallbackVibrate('medium'); return; }
    generateTone(523, 0.4, 'sine', 0.15);
    setTimeout(() => generateTone(659, 0.6, 'sine', 0.12), 120);
  } catch(e) { _fallbackVibrate('medium'); }
}

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  try { wx.setStorageSync('sfx_enabled', sfxEnabled); } catch(e) {}
  return sfxEnabled;
}

module.exports = {
  playCardDrawSound,
  playCardRevealSound,
  toggleSfx,
  get sfxEnabled() { return sfxEnabled; },
};
