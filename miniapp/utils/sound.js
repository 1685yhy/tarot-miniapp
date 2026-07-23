/**
 * 音效管理器 — 抽牌沉浸感 + 星空环境音
 * =============================================
 * 全部使用程序化合成 (Web Audio API)，无需外部音频文件
 * 使用单个共享 AudioContext（懒初始化）
 * 低端设备自动降级为振动反馈
 */

let sfxEnabled = true;
let ambientEnabled = false;
let _ambientNodes = null;   // { source, lfo, gain, noiseGain, noiseSource }
let _ambientFadeTimer = null;
let _ambientVolume = 50;    // 0-100

// 共享 AudioContext（懒初始化，模块级变量）
let _sharedCtx = null;

// 从 wx.Storage 读取偏好
try {
  sfxEnabled = wx.getStorageSync('sfx_enabled') !== false;
  ambientEnabled = wx.getStorageSync('ambient_enabled') === true;
} catch(e) {}


// ============================================================
// 懒初始化共享 AudioContext
// ============================================================

function _getCtx() {
  if (!_sharedCtx) {
    try {
      _sharedCtx = wx.createWebAudioContext();
    } catch(e) {
      return null;
    }
  }
  return _sharedCtx;
}

// 重置（当 context 状态变化时重新获取）
function _resetCtx() {
  _sharedCtx = null;
  return _getCtx();
}


// ============================================================
// StereoPannerNode 辅助（支持老版本降级）
// ============================================================

function _createStereoPanner(ctx) {
  try {
    return new StereoPannerNode(ctx, { pan: 0 });
  } catch(e) {
    try {
      return ctx.createStereoPanner();
    } catch(e2) {
      return null;
    }
  }
}


// ============================================================
// 混响效果器 — 使用 createConvolver 模拟空间感
// ============================================================

function createReverb(ctx, decayMs = 1500) {
  try {
    const sampleRate = ctx.sampleRate;
    const length = sampleRate * decayMs / 1000;
    const impulse = ctx.createBuffer(2, length, sampleRate);
    // 使用指数衰减白噪声模拟房间脉冲响应
    for (let ch = 0; ch < 2; ch++) {
      const data = impulse.getChannelData(ch);
      for (let i = 0; i < length; i++) {
        const t = i / length;
        // 早期反射 + 混响尾音
        const envelope = Math.exp(-t * 6) * (1 - t * 0.3);
        data[i] = (Math.random() * 2 - 1) * envelope;
      }
    }
    const convolver = ctx.createConvolver();
    convolver.buffer = impulse;
    return convolver;
  } catch(e) {
    return null;
  }
}


// ============================================================
// 基础音调生成
// ============================================================

function generateTone(frequency, duration, type = 'sine', volume = 0.3, pan = 0) {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = frequency;
    gain.gain.value = volume;
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);

    let destination = gain;
    // 空间音效：StereoPanner 路由
    if (pan !== 0) {
      const panner = _createStereoPanner(ctx);
      if (panner) {
        panner.pan.value = pan;
        gain.connect(panner);
        destination = panner;
      }
    }

    osc.connect(gain);
    destination.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch(e) {}
}

/**
 * 带混响的音调生成
 */
function generateToneWithReverb(frequency, duration, type = 'sine', volume = 0.3, pan = 0, reverbMix = 0.3) {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) return;

    const osc = ctx.createOscillator();
    const dryGain = ctx.createGain();
    const wetGain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = frequency;
    dryGain.gain.value = volume * (1 - reverbMix);
    wetGain.gain.value = volume * reverbMix;
    dryGain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);
    wetGain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + duration);

    osc.connect(dryGain);
    let dryDest = dryGain;

    // 混响链路
    const reverb = createReverb(ctx, 2000);
    if (reverb) {
      osc.connect(wetGain);
      wetGain.connect(reverb);
      reverb.connect(ctx.destination);
    }

    // 空间音效
    if (pan !== 0) {
      const panner = _createStereoPanner(ctx);
      if (panner) {
        panner.pan.value = pan;
        dryGain.connect(panner);
        dryDest = panner;
      }
    }

    dryDest.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + duration);
  } catch(e) {}
}


// ============================================================
// 降级振动反馈
// ============================================================

function _fallbackVibrate(type = 'light') {
  try { wx.vibrateShort({ type }); } catch(e) {}
}


// ============================================================
// 洗牌音 — 短促白噪声
// ============================================================

function playCardDrawSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
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


// ============================================================
// 揭示音 — 指数正弦扫频 + 混响（模拟水晶颂钵）
// 改进：从 C5 到 E6 的指数扫频，叠加混响产生颂钵般的泛音
// ============================================================

function playCardRevealSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) { _fallbackVibrate('medium'); return; }

    // 主音：C5 → E6 指数扫频（模拟水晶颂钵）
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(523.25, ctx.currentTime);         // C5
    osc.frequency.exponentialRampToValueAtTime(1318.5, ctx.currentTime + 0.3); // E6
    gain.gain.setValueAtTime(0.12, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);

    // 混响
    const reverb = createReverb(ctx, 2500);
    if (reverb) {
      osc.connect(gain);
      gain.connect(reverb);
      reverb.connect(ctx.destination);
    } else {
      osc.connect(gain);
      gain.connect(ctx.destination);
    }

    osc.start();
    osc.stop(ctx.currentTime + 0.9);

    // 泛音层：G5 轻柔叠加
    setTimeout(() => {
      try {
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.type = 'sine';
        osc2.frequency.value = 784;
        gain2.gain.setValueAtTime(0.04, ctx.currentTime);
        gain2.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.start();
        osc2.stop(ctx.currentTime + 0.6);
      } catch(e) {}
    }, 80);

  } catch(e) { _fallbackVibrate('medium'); }
}


// ============================================================
// 按钮点击音 — 短促清脆的 click/pop
// ============================================================

function playButtonClickSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) { _fallbackVibrate('light'); return; }
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


// ============================================================
// 页面进入音 — 柔和的环境 chime (C5 短促衰减)
// ============================================================

function playPageEnterSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) return;
    generateTone(523, 0.25, 'sine', 0.06, 0.3);
  } catch(e) { /* 静默降级 */ }
}


// ============================================================
// 里程碑音 — 改进版：C-E-G-C 和弦进行（30天里程碑完整和弦）
// 普通里程碑用上行音阶，30天用完整大三和弦
// ============================================================

function playMilestoneSound(isMilestone) {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) { _fallbackVibrate('medium'); return; }

    if (isMilestone) {
      // 完整 C-E-G-C 和弦（30天等重大里程碑）
      const chordNotes = [
        { freq: 523.25, vol: 0.10, delay: 0 },    // C4
        { freq: 659.25, vol: 0.08, delay: 0 },    // E4
        { freq: 783.99, vol: 0.07, delay: 0 },    // G4
        { freq: 1046.5, vol: 0.06, delay: 120 },  // C5
      ];
      chordNotes.forEach(n => {
        setTimeout(() => {
          generateToneWithReverb(n.freq, 0.6, 'sine', n.vol, 0, 0.4);
        }, n.delay);
      });
    } else {
      // 普通里程碑/每日任务：上行音阶 (C5→E5→G5)
      setTimeout(() => generateTone(523, 0.12, 'sine', 0.08, -0.3), 0);
      setTimeout(() => generateTone(659, 0.12, 'sine', 0.07, 0), 70);
      setTimeout(() => generateTone(784, 0.16, 'sine', 0.06, 0.3), 140);
    }
  } catch(e) { _fallbackVibrate('medium'); }
}


// ============================================================
// 翻牌音 — 与抽牌不同的短促 swoosh
// ============================================================

function playCardFlipSound() {
  if (!sfxEnabled) return;
  try {
    const ctx = _getCtx();
    if (!ctx) { _fallbackVibrate('light'); return; }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(200, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.04, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);

    // Stereo pan: 从左到右
    const panner = _createStereoPanner(ctx);
    if (panner) {
      panner.pan.setValueAtTime(-0.5, ctx.currentTime);
      panner.pan.linearRampToValueAtTime(0.5, ctx.currentTime + 0.1);
      osc.connect(gain);
      gain.connect(panner);
      panner.connect(ctx.destination);
    } else {
      osc.connect(gain);
      gain.connect(ctx.destination);
    }

    osc.start();
    osc.stop(ctx.currentTime + 0.12);
  } catch(e) { _fallbackVibrate('light'); }
}


// ============================================================
// 音效开关
// ============================================================

function toggleSfx() {
  sfxEnabled = !sfxEnabled;
  try { wx.setStorageSync('sfx_enabled', sfxEnabled); } catch(e) {}
  return sfxEnabled;
}


// ============================================================
// 环境背景音 — 星空氛围
// ============================================================

/**
 * 启动星空环境音
 * - C2 正弦波 @ ~20% 音量（深沉低频衬底）
 * - 滤波白噪声 @ ~5% 音量（模拟宇宙背景辐射）
 * - 低频振荡器调制噪声音量（呼吸感）
 * 循环播放直到 stopAmbientSound() 被调用
 */
function startAmbientSound() {
  if (!sfxEnabled && !ambientEnabled) return;
  if (_ambientNodes) return; // 已在播放

  try {
    const ctx = _getCtx();
    if (!ctx) return;

    // ---- 1. 低频衬底 (C2 sine) ----
    const source = ctx.createOscillator();
    const gain = ctx.createGain();
    source.type = 'sine';
    source.frequency.value = 65.41; // C2
    gain.gain.value = 0.20 * (_ambientVolume / 100); // 基础音量 ~20%

    // ---- 2. 滤波白噪声 ----
    const bufferSize = ctx.sampleRate * 2;
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      data[i] = (Math.random() * 2 - 1) * 2; // 白噪声
    }
    const noiseSource = ctx.createBufferSource();
    noiseSource.buffer = buffer;
    noiseSource.loop = true;

    // 低通滤波器 — 只保留超低频
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 200;
    filter.Q.value = 1;

    const noiseGain = ctx.createGain();
    noiseGain.gain.value = 0.05 * (_ambientVolume / 100); // 基础音量 ~5%

    // 低频振荡器（LFO）调制噪声音量 — 模拟呼吸感
    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();
    lfo.type = 'sine';
    lfo.frequency.value = 0.08; // 约 12 秒一个周期
    lfoGain.gain.value = 0.03 * (_ambientVolume / 100); // 调制深度

    noiseSource.connect(filter);
    filter.connect(noiseGain);

    // LFO → noiseGain.gain 调制
    lfo.connect(lfoGain);
    lfoGain.connect(noiseGain.gain);

    // 汇聚到输出
    source.connect(gain);
    gain.connect(ctx.destination);
    noiseGain.connect(ctx.destination);

    source.start();
    noiseSource.start();
    lfo.start();

    _ambientNodes = { source, gain, lfo, lfoGain, noiseSource, noiseGain, filter, ctx };

  } catch(e) {
    _ambientNodes = null;
  }
}


/**
 * 停止环境音（淡出 1 秒）
 */
function stopAmbientSound() {
  if (!_ambientNodes) return;
  if (_ambientFadeTimer) {
    clearTimeout(_ambientFadeTimer);
    _ambientFadeTimer = null;
  }

  try {
    const { source, gain, noiseSource, noiseGain, lfo, lfoGain, ctx } = _ambientNodes;
    const fadeStart = ctx.currentTime;

    // 淡出 1 秒
    gain.gain.setValueAtTime(gain.gain.value, fadeStart);
    gain.gain.linearRampToValueAtTime(0.001, fadeStart + 1);

    noiseGain.gain.setValueAtTime(noiseGain.gain.value, fadeStart);
    noiseGain.gain.linearRampToValueAtTime(0.001, fadeStart + 1);
    lfoGain.gain.linearRampToValueAtTime(0.001, fadeStart + 1);

    _ambientFadeTimer = setTimeout(() => {
      try {
        source.stop();
        noiseSource.stop();
        lfo.stop();
      } catch(e) {}
      _ambientNodes = null;
      _ambientFadeTimer = null;
    }, 1100);
  } catch(e) {
    _ambientNodes = null;
  }
}


/**
 * 设置环境音音量
 * @param {number} level 0-100
 */
function setAmbientVolume(level) {
  _ambientVolume = Math.max(0, Math.min(100, level));
  if (_ambientNodes) {
    const { gain, noiseGain, lfoGain } = _ambientNodes;
    const factor = _ambientVolume / 100;
    gain.gain.value = 0.20 * factor;
    noiseGain.gain.value = 0.05 * factor;
    lfoGain.gain.value = 0.03 * factor;
  }
  try { wx.setStorageSync('ambient_volume', _ambientVolume); } catch(e) {}
}


/**
 * 获取环境音状态
 */
function isAmbientPlaying() {
  return _ambientNodes !== null;
}


/**
 * 切换环境音开关
 */
function toggleAmbient() {
  ambientEnabled = !ambientEnabled;
  try { wx.setStorageSync('ambient_enabled', ambientEnabled); } catch(e) {}

  if (ambientEnabled) {
    // 从存储中恢复音量
    try {
      const saved = wx.getStorageSync('ambient_volume');
      if (saved !== '') _ambientVolume = saved;
    } catch(e) {}
    startAmbientSound();
  } else {
    stopAmbientSound();
  }
  return ambientEnabled;
}


// ============================================================
// 导出
// ============================================================

module.exports = {
  playCardDrawSound,
  playCardRevealSound,
  playButtonClickSound,
  playPageEnterSound,
  playMilestoneSound,
  playCardFlipSound,
  toggleSfx,
  get sfxEnabled() { return sfxEnabled; },

  // Ambient sound
  startAmbientSound,
  stopAmbientSound,
  setAmbientVolume,
  isAmbientPlaying,
  toggleAmbient,
  get ambientEnabled() { return ambientEnabled; },
};
