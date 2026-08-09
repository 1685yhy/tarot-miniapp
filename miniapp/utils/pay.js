/**
 * utils/pay.js —— 统一支付入口（JSAPI → 虚拟支付 xpay 双通道）
 * =================================================================
 * 后端契约（POST /orders）：
 *   { order_id, order_no, amount, product_name,
 *     xpay_params: { mode, signData, paySig, signature }   // 新·虚拟支付（PAY_CHANNEL=xpay）
 *     | payment_params                                    // 旧·JSAPI（迁移期兼容） }
 *   GET /orders/{order_no}/status → { status: pending|paid|refunded|cancelled }
 *
 * 使用方式：
 *   const { startPay, isComingSoonError, showComingSoonModal } = require('../../utils/pay');
 *   startPay(order, {
 *     product,                       // 商品信息（透传，不做业务处理）
 *     success: () => { ... },        // 页面原有成功逻辑
 *     fail: (err) => { ... },        // err.message 已是友好文案; err.reason: user_cancel|payment_failed|coming_soon
 *   });
 */
const { request } = require('./api');

const STATUS_POLL_INTERVAL = 1500; // 轮询间隔 ms
const STATUS_POLL_MAX = 4;         // 最多轮询次数（等回调发货）

const GENERIC_FAIL_MESSAGE = '支付失败，请重试';

/**
 * 解析 xpay 错误码：优先取 err.errCode，兼容仅 errMsg 带码的情况。
 * 虚拟支付错误码参考（官方码表）：
 *   -2        用户取消 → user_cancel
 *   -15002    outTradeNo 重复（订单可能已支付）→ 查单兜底
 *   -15005    支付签名错误（登录态/签名异常）→ 支付异常提示
 *   -15006    支付签名校验失败 → 支付异常提示
 *   -15007    支付签名数据错误 → 支付异常提示
 *   -15009    代币未发布 → 支付异常提示
 *   -15010    道具未发布 → 商品即将上线（coming_soon）
 */
function parseXpayErrCode(err) {
  if (!err) return null;
  if (typeof err.errCode === 'number') return err.errCode;
  if (typeof err.errCode === 'string' && err.errCode !== '') {
    const n = Number(err.errCode);
    if (!Number.isNaN(n)) return n;
  }
  const m = String(err.errMsg || '').match(/(-?\d{4,6})/);
  return m ? Number(m[1]) : null;
}

/** 构造给页面 fail 回调的归一化错误对象 */
function callFail(fail, message, reason, errCode) {
  if (typeof fail === 'function') {
    fail({
      message: message || GENERIC_FAIL_MESSAGE,
      reason: reason || 'payment_failed',
      errCode: typeof errCode === 'number' ? errCode : undefined,
    });
  }
}

/**
 * 轮询订单状态：立即查一次，之后 1.5s 间隔，最多 STATUS_POLL_MAX 次。
 * 任一时刻查到 paid → onPaid()；全部轮询结束仍未 paid（或查询失败）→ onTimeout()。
 * 查询失败按未确认处理（不抛错），由页面既有 402 重试兜底。
 */
function pollOrderPaid(orderNo, { onPaid, onTimeout }) {
  if (!orderNo) {
    onTimeout();
    return;
  }
  let tries = 0;
  const check = () => {
    tries += 1;
    request(`/orders/${orderNo}/status`)
      .then((res) => {
        if (res && res.status === 'paid') {
          onPaid();
        } else if (tries >= STATUS_POLL_MAX) {
          onTimeout();
        } else {
          setTimeout(check, STATUS_POLL_INTERVAL);
        }
      })
      .catch(() => {
        if (tries >= STATUS_POLL_MAX) {
          onTimeout();
        } else {
          setTimeout(check, STATUS_POLL_INTERVAL);
        }
      });
  };
  check();
}

/**
 * 统一支付入口。
 * @param {object} order POST /orders 返回的订单对象
 * @param {object} opts
 *   product  商品信息（透传，页面用于 analytics 等）
 *   success  支付成功回调（含轮询兜底：确认到账/超时后触发一次）
 *   fail     支付失败回调，参数 { message, reason, errCode }
 */
function startPay(order, { product, success, fail } = {}) {
  if (!order || typeof order !== 'object' || !order.order_no) {
    callFail(fail, GENERIC_FAIL_MESSAGE, 'payment_failed');
    return;
  }

  const xpay = order.xpay_params;
  const legacy = order.payment_params;

  // ── 通道一：虚拟支付（xpay）──
  if (xpay && typeof xpay === 'object') {
    if (!wx.canIUse('requestVirtualPayment')) {
      wx.showModal({
        title: '请升级微信',
        content: '当前微信版本暂不支持虚拟支付，请升级微信至最新版本后重试。',
        showCancel: false,
      });
      return; // 能力缺失，不回调 fail（页面无失败提示可显示）
    }

    // signData/paySig/signature 全部透传，前端不拼字段
    wx.requestVirtualPayment({
      mode: xpay.mode,
      signData: xpay.signData,
      paySig: xpay.paySig,
      signature: xpay.signature,
      success: () => {
        // 成功回调后轮询兜底：等回调发货；超时交给页面既有 402 重试
        pollOrderPaid(order.order_no, {
          onPaid: () => success && success(),
          onTimeout: () => success && success(),
        });
      },
      fail: (err) => {
        const code = parseXpayErrCode(err);
        if (code === -15002) {
          // outTradeNo 重复：订单可能已支付 → 查单兜底，paid 直接走成功路径
          pollOrderPaid(order.order_no, {
            onPaid: () => success && success(),
            onTimeout: () => callFail(fail, GENERIC_FAIL_MESSAGE, 'payment_failed', code),
          });
          return;
        }
        if (code === -2) {
          // 用户取消支付
          callFail(fail, '支付已取消', 'user_cancel', code);
        } else if (code === -15010) {
          // 道具未发布 → 商品即将上线（降级弹窗，不进失败漏斗）
          callFail(fail, '商品即将上线，敬请期待', 'coming_soon', code);
        } else if (code === -15005 || code === -15006 || code === -15007 || code === -15009) {
          // 签名/登录态/代币异常 → 引导重新登录或稍后重试
          callFail(fail, '支付出现异常，请重新登录后再试', 'payment_failed', code);
        } else {
          callFail(fail, GENERIC_FAIL_MESSAGE, 'payment_failed', code);
        }
      },
    });
    return;
  }

  // ── 通道二：旧版 JSAPI 微信支付（迁移期兼容）──
  if (legacy && typeof legacy === 'object') {
    wx.requestPayment({
      timeStamp: legacy.timeStamp,
      nonceStr: legacy.nonceStr,
      package: legacy.package,
      signType: legacy.signType || 'HMAC-SHA256',
      paySign: legacy.paySign,
      success: () => {
        // 与 xpay 通道一致：轮询兜底等回调发货，超时交给页面 402 重试
        pollOrderPaid(order.order_no, {
          onPaid: () => success && success(),
          onTimeout: () => success && success(),
        });
      },
      fail: (err) => {
        if (err && err.errMsg && err.errMsg.includes('cancel')) {
          callFail(fail, '支付已取消', 'user_cancel');
        } else {
          callFail(fail, GENERIC_FAIL_MESSAGE, 'payment_failed');
        }
      },
    });
    return;
  }

  // ── 两个通道都未配置（页面已前置拦截，这里兜底）──
  callFail(fail, '支付方式暂未开通，请稍后再试', 'payment_failed');
}

/**
 * 判断下单错误是否为「商品即将上线」降级提示（HTTP 400, message/detail 含"即将上线"）。
 */
function isComingSoonError(err) {
  return !!(err && err.statusCode === 400 && typeof err.message === 'string' && err.message.includes('即将上线'));
}

/** 商品即将上线降级弹窗（不进失败 analytics 漏斗） */
function showComingSoonModal() {
  wx.showModal({
    title: '商品即将上线',
    content: '敬请期待',
    showCancel: false,
  });
}

module.exports = { startPay, isComingSoonError, showComingSoonModal };
