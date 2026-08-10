/**
 * 小程序全局配置
 * =====================
 * 集中管理业务配置项，避免散落各处。此文件会随小程序包发布，
 * 请勿存放真正的服务端密钥（前端代码无法真正保密）。
 */

// 开发模式登录保护密钥（与后端 .env 中 DEV_LOGIN_KEY 一致）。
// 仅用于非 release 环境的 dev-login 兜底登录请求头 X-Dev-Key。
const DEV_LOGIN_KEY = 'DevKey-REDACTED';

// 客服联系方式（微信 / 邮箱）。
// 为空时，「用户协议/隐私政策」页的联系我们章节显示
// “可通过小程序内反馈渠道联系我们”；后续有真实联系方式只改这里。
const CONTACT_WEIXIN = '';
const CONTACT_EMAIL = '1685070007@qq.com';

// 星光晨讯订阅模板 ID（微信公众平台「订阅消息」→ 模板库中申请，形如 "xxxx_xxxx_xxxx"）。
// 为空字符串 = 未配置：抽牌结果页 / 许愿成功页 / 每日一牌翻转后均不弹订阅引导。
// 配置后：用户同意 → wx.requestSubscribeMessage → POST /notify/subscribe-grant（额度+1），
// 每天 7:37 发送「今日星光」推送（一次性订阅，每次授权对应 1 条发送额度）。
const WX_SUBSCRIBE_TEMPLATE_DAILY = '';

module.exports = {
  DEV_LOGIN_KEY,
  CONTACT_WEIXIN,
  CONTACT_EMAIL,
  WX_SUBSCRIBE_TEMPLATE_DAILY,
};
