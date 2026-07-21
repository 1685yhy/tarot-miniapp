// 音效管理器 — 抽牌沉浸感
let bgmAudio = null;
let sfxAudio = null;
let bgmEnabled = true;
let sfxEnabled = true;

// 从 wx.Storage 读取偏好
try {
  bgmEnabled = wx.getStorageSync('bgm_enabled') !== false;
  sfxEnabled = wx.getStorageSync('sfx_enabled') !== false;
} catch(e) {}

const SOUNDS = {
  shuffle: '/assets/audio/shuffle.mp3',    // 洗牌音
  cardFlip: '/assets/audio/card_flip.mp3', // 翻牌音
  reveal: '/assets/audio/reveal.mp3',       // 解读揭示音
  chime: '/assets/audio/chime.mp3',         // 完成提示音
  ambient: '/assets/audio/ambient.mp3',     // 背景氛围音乐
};

function playSfx(name) {
  if (!sfxEnabled) return;
  if (sfxAudio) { sfxAudio.destroy(); }
  sfxAudio = wx.createInnerAudioContext({ useWebAudioImplement: true });
  sfxAudio.src = SOUNDS[name];
  sfxAudio.volume = 0.3;
  sfxAudio.play();
  sfxAudio.onEnded(() => { sfxAudio.destroy(); sfxAudio = null; });
  sfxAudio.onError(() => { sfxAudio.destroy(); sfxAudio = null; });
}

function playBgm(name) {
  if (!bgmEnabled) return;
  if (bgmAudio) { bgmAudio.stop(); bgmAudio.destroy(); }
  bgmAudio = wx.createInnerAudioContext({ useWebAudioImplement: true });
  bgmAudio.src = SOUNDS[name];
  bgmAudio.volume = 0.15;
  bgmAudio.loop = true;
  bgmAudio.play();
}

function stopBgm() {
  if (bgmAudio) { bgmAudio.stop(); bgmAudio.destroy(); bgmAudio = null; }
}

function toggleBgm() {
  bgmEnabled = !bgmEnabled;
  wx.setStorageSync('bgm_enabled', bgmEnabled);
  if (!bgmEnabled) stopBgm();
  return bgmEnabled;
}

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  wx.setStorageSync('sfx_enabled', sfxEnabled);
  return sfxEnabled;
}

// 程序化音效 — 无需音频文件，用 Web Audio 合成
function generateTone(frequency, duration, type = 'sine', volume = 0.3) {
  if (!sfxEnabled) return;
  try {
    const ctx = wx.createWebAudioContext();
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

// 预设音效
function playCardDrawSound() {
  // 洗牌：短促白噪声
  if (!sfxEnabled) return;
  try {
    const ctx = wx.createWebAudioContext();
    const bufferSize = ctx.sampleRate * 0.15;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
    }
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const gain = ctx.createGain();
    gain.gain.value = 0.08;
    source.connect(gain);
    gain.connect(ctx.destination);
    source.start();
  } catch(e) {
    // Web Audio 兼容性差时降级为 vibrateShort
    try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
  }
}

function playCardRevealSound() {
  // 揭示：上升钟声
  if (!sfxEnabled) return;
  generateTone(880, 0.5, 'sine', 0.2);
  setTimeout(() => generateTone(1100, 0.8, 'sine', 0.15), 150);
  // 回退振动
  try { wx.vibrateShort({ type: 'light' }); } catch(e) {}
}

module.exports = { playSfx, playBgm, stopBgm, toggleBgm, toggleSfx, get bgmEnabled() { return bgmEnabled; }, get sfxEnabled() { return sfxEnabled; }, generateTone, playCardDrawSound, playCardRevealSound };
