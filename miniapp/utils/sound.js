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

/**
 * 按钮点击音 — 短促清脆的 click/pop
 * 非常短 (<0.1s)，几乎无感的反馈
 */
function playButtonClickSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) { _fallbackVibrate('light'); return; }
    // 极短的白噪声扫描作为 click
    const bufferSize = Math.floor(ctx.sampleRate * 0.06);
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / bufferSize, 3);
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const gain = ctx.createGain();
    gain.gain.value = 0.04;
    source.connect(gain);
    gain.connect(ctx.destination);
    source.start();
  } catch(e) { _fallbackVibrate('light'); }
}

/**
 * 页面进入音 — 柔和的环境 chime (C5 短促衰减)
 */
function playPageEnterSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) return;
    generateTone(523, 0.25, 'sine', 0.06);
  } catch(e) { /* 静默降级 */ }
}

/**
 * 里程碑音 — 庆祝性上行音阶 (C5→E5→G5)
 * 非常短促，总长 <0.3s
 */
function playMilestoneSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) { _fallbackVibrate('medium'); return; }
    generateTone(523, 0.12, 'sine', 0.08);
    setTimeout(() => generateTone(659, 0.12, 'sine', 0.07), 70);
    setTimeout(() => generateTone(784, 0.16, 'sine', 0.06), 140);
  } catch(e) { _fallbackVibrate('medium'); }
}

/**
 * 翻牌音 — 与抽牌不同的短促 swoosh
 * 扫频噪声 + 轻微冲击
 */
function playCardFlipSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getAudioCtx();
    if (!ctx) { _fallbackVibrate('light'); return; }
    // 频率扫描 (200→800Hz 快速上升)，模拟纸张翻动
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(200, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.04, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.12);
  } catch(e) { _fallbackVibrate('light'); }
}

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  try { wx.setStorageSync('sfx_enabled', sfxEnabled); } catch(e) {}
  return sfxEnabled;
}

module.exports = {
  playCardDrawSound,
  playCardRevealSound,
  playButtonClickSound,
  playPageEnterSound,
  playMilestoneSound,
  playCardFlipSound,
  toggleSfx,
  get sfxEnabled() { return sfxEnabled; },
};
