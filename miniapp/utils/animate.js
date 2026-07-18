/**
 * utils/animate.js
 * WeChat native animation helper using wx.createAnimation
 * Supports chaining, sequencing, and parallel animations
 *
 * Benefits over CSS keyframes:
 * - Runs on the native rendering thread (not JS thread)
 * - Smoother easing curves at native level
 * - Better frame timing under load
 * - Programmatic sequencing (not hardcoded delay classes)
 * - Easy to compose and chain
 *
 * Usage:
 *   const { cardEnter, staggeredEntrance } = require('../../utils/animate');
 *   const anim = cardEnter();
 *   this.setData({ animData: anim });
 *   // WXML: <view animation="{{animData}}">
 *
 * Toggle:
 *   Set `useNativeAnim: true/false` in page data to enable/disable
 *   All existing CSS animations remain intact as fallback
 */

/**
 * Create a new wx.createAnimation instance with default options
 * @param {Object} options
 * @param {number}  options.duration - animation duration in ms (default: 400)
 * @param {string}  options.timing  - timing function (default: 'ease-out')
 * @param {number}  options.delay   - delay in ms (default: 0)
 * @param {string}  options.origin  - transform origin (default: '50% 50% 0')
 * @returns {Object} wx.createAnimation instance
 */
function createAnim(options = {}) {
  return wx.createAnimation({
    duration: options.duration || 400,
    timingFunction: options.timing || 'ease-out',
    delay: options.delay || 0,
    transformOrigin: options.origin || '50% 50% 0',
  });
}

module.exports = {
  createAnim,

  /**
   * Card entrance: scale up + fade in
   * Two-step: sets initial invisible state (duration:0), then animates in
   * @param {number} duration - animation duration in ms (default: 400)
   * @param {number} delay    - delay before animation in ms (default: 0)
   * @returns {Object} animation export data for setData
   */
  cardEnter(duration = 400, delay = 0) {
    const anim = createAnim({ duration: 0 });
    anim.scale(0.92).opacity(0).step();
    anim.scale(1).opacity(1).step({ duration, delay });
    return anim.export();
  },

  /**
   * Card reveal: flip-like scaleX bounce
   * Simulates a card flipping over on its vertical axis
   * @param {number} duration - total animation duration in ms (default: 500)
   * @returns {Object} animation export data for setData
   */
  cardReveal(duration = 500) {
    const anim = createAnim({ duration: 0 });
    anim.scaleX(0).opacity(0).step();
    anim.scaleX(1.08).opacity(1).step({ duration: duration * 0.5, timingFunction: 'ease-in' });
    anim.scaleX(1).step({ duration: duration * 0.3 });
    return anim.export();
  },

  /**
   * Fade + slide up
   * Element rises 60px while fading in
   * @param {number} duration - animation duration in ms (default: 400)
   * @param {number} delay    - delay before animation in ms (default: 0)
   * @returns {Object} animation export data for setData
   */
  slideUp(duration = 400, delay = 0) {
    const anim = createAnim({ duration: 0 });
    anim.translateY(60).opacity(0).step();
    anim.translateY(0).opacity(1).step({ duration, delay });
    return anim.export();
  },

  /**
   * Gentle pulse (for buttons, CTAs)
   * Looping scale oscillation: 1 -> 1.05 -> 1
   * @returns {Object} animation export data for setData
   */
  gentlePulse() {
    const anim = createAnim({ duration: 0 });
    anim.scale(1).step();
    anim.scale(1.05).step({ duration: 600, timingFunction: 'ease-in-out' });
    anim.scale(1).step({ duration: 600, timingFunction: 'ease-in-out' });
    return anim.export();
  },

  /**
   * Staggered list entrance (returns array of animations)
   * Each element scales up + fades in with incremental delay
   * Useful for grid items, card lists, step indicators
   * @param {number} count     - number of elements to animate
   * @param {number} baseDelay - delay between each element in ms (default: 80)
   * @returns {Array<Object>} array of animation export data, one per element
   */
  staggeredEntrance(count, baseDelay = 80) {
    const results = [];
    for (let i = 0; i < count; i++) {
      const anim = createAnim({ duration: 0 });
      anim.scale(0.9).opacity(0).step();
      anim.scale(1).opacity(1).step({
        duration: 400,
        delay: i * baseDelay,
        timingFunction: 'ease-out',
      });
      results.push(anim.export());
    }
    return results;
  },
};
