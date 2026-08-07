// pages/legal/legal.js
// 用户协议 / 隐私政策 页面（E3 奶油风格）
// 通过 query 区分：pages/legal/legal?type=agreement | ?type=privacy
// 文案来源：docs/wechat-review/user-agreement.md / privacy-policy.md（完整转写）

const { CONTACT_WEIXIN, CONTACT_EMAIL } = require('../../utils/config');

/**
 * 联系我们章节的展示项：
 * - 配置了真实联系方式（CONTACT_WEIXIN / CONTACT_EMAIL）时展示对应文案；
 * - 均为空时展示「可通过小程序内反馈渠道联系我们」，不显示占位符。
 * 后续有真实联系方式只改 utils/config.js。
 */
function buildContactItems() {
  const items = [];
  if (CONTACT_WEIXIN) items.push({ type: 'ul', text: `客服微信：${CONTACT_WEIXIN}` });
  if (CONTACT_EMAIL) items.push({ type: 'ul', text: `客服邮箱：${CONTACT_EMAIL}` });
  if (!items.length) items.push({ type: 'ul', text: '可通过小程序内反馈渠道联系我们' });
  return items;
}

const AGREEMENT = {
  navTitle: '用户协议',
  title: '星光映照 · 用户服务协议',
  meta: '更新日期：2026年7月31日',
  intro: '欢迎使用星光映照小程序。请您在使用前仔细阅读本协议。',
  chapters: [
    {
      title: '一、服务说明',
      body: [
        { type: 'p', text: '星光映照是一款基于塔罗牌文化的自我探索与心灵陪伴工具，提供以下服务：' },
        { type: 'ol', text: '1. 塔罗百科：78张塔罗牌的文化、历史与符号学知识' },
        { type: 'ol', text: '2. 每日一牌：随机抽取塔罗牌，提供自我觉察视角' },
        { type: 'ol', text: '3. 牌阵解读：基于用户问题，AI从心理学与符号学角度提供分析' },
        { type: 'ol', text: '4. 塔罗日记：记录每日心情与反思，AI辅助生成周回顾' },
        { type: 'ol', text: '5. 会员服务：提供更多解读次数和高级功能' },
      ],
    },
    {
      title: '二、重要声明',
      body: [
        { type: 'ol', text: '1. 本产品定位为“娱乐与自我探索工具”，不涉及迷信活动' },
        { type: 'ol', text: '2. AI 解读内容仅供自我觉察参考，AI生成内容均标注“仅供参考”' },
        { type: 'ol', text: '3. 本产品不替代心理咨询、医疗诊断、法律咨询或金融建议' },
        { type: 'ol', text: '4. 如需专业帮助，请咨询相关领域的专业人士' },
        { type: 'ol', text: '5. 本产品不提供算命、预测未来、看相、风水等迷信服务，不承诺“转运”“改运”等效果' },
        { type: 'ol', text: '6. 若您为未成年人，请在监护人指导下使用本产品' },
      ],
    },
    {
      title: '三、用户行为规范',
      body: [
        { type: 'p', text: '您在使用本产品时，不得：' },
        { type: 'ul', text: '利用本产品从事任何违法违规活动' },
        { type: 'ul', text: '干扰或破坏本产品的正常运行' },
        { type: 'ul', text: '利用AI解读功能生成违法、暴力、色情等内容' },
        { type: 'ul', text: '以任何方式绕过付费机制' },
      ],
    },
    {
      title: '四、会员与付费',
      body: [
        { type: 'ul', text: '会员价格以购买时页面显示为准（月¥19.9/年¥168/学生¥9.9，另有单次解读及解读包，价格以页面显示为准）' },
        { type: 'ul', text: '依据微信支付虚拟商品交易规则，虚拟商品一经购买并生效，原则上不支持退款；法律法规另有规定的除外（如因我方原因导致服务无法提供）' },
        { type: 'ul', text: '我们保留根据运营需要调整价格和服务的权利，调整将提前在小程序内公示' },
        { type: 'ul', text: '会员到期后，会员专属功能将不可用，已生成的解读记录不会丢失' },
      ],
    },
    {
      title: '五、知识产权',
      body: [
        { type: 'ul', text: '小程序代码、设计、78张AI生成卡牌图像的知识产权归开发者所有' },
        { type: 'ul', text: '用户生成的解读内容和日记内容属于用户本人' },
        { type: 'ul', text: '未经许可，不得复制、传播本小程序的内容' },
      ],
    },
    {
      title: '六、免责条款',
      body: [
        { type: 'ul', text: 'AI解读内容由人工智能模型生成，可能存在不准确之处' },
        { type: 'ul', text: '因网络、服务器等不可抗力导致的服务中断，我们不承担责任' },
        { type: 'ul', text: '用户因使用本产品内容产生的任何决策和后果，由用户自行承担' },
      ],
    },
    {
      title: '七、协议修改',
      body: [
        { type: 'p', text: '我们可能根据需要修改本协议。修改后的协议将在小程序内公布，继续使用即视为同意。' },
      ],
    },
    {
      title: '八、争议解决',
      body: [
        { type: 'p', text: '本协议的订立、执行与解释均适用中华人民共和国法律。如发生争议，双方应友好协商解决；协商不成的，可向开发者所在地有管辖权的人民法院提起诉讼。' },
      ],
    },
    {
      title: '九、联系我们',
      body: [
        { type: 'p', text: '如对本协议有任何疑问，请联系我们：' },
        { type: 'ul', text: '开发者：祁县天天开心商贸行(个体工商户)' },
        ...buildContactItems(),
        { type: 'strong', text: '开发者：祁县天天开心商贸行(个体工商户)' },
        { type: 'strong', text: '统一社会信用代码：92140727MAE8C7WN66' },
      ],
    },
  ],
  footer: '星光映照 v1.1 · 更新日期 2026-08-07',
};

const PRIVACY = {
  navTitle: '隐私政策',
  title: '星光映照 · 隐私政策',
  meta: '更新日期：2026年7月31日',
  intro: '祁县天天开心商贸行(个体工商户)（以下简称“我们”）深知个人信息对您的重要性，我们将按照《中华人民共和国个人信息保护法》等法律法规的规定，保护您的个人信息安全。请在使用本小程序前仔细阅读本政策。',
  chapters: [
    {
      title: '一、我们收集的信息',
      body: [
        {
          type: 'table',
          rows: [
            { name: '微信 OpenID（登录标识）', usage: '识别您的身份，关联您的账号数据（解读记录、日记、会员状态等）', required: '必要' },
            { name: '微信昵称、头像', usage: '在小程序内展示您的身份；您不提供时可使用默认昵称', required: '否' },
            { name: '塔罗解读记录（提问内容、所选牌阵、AI 解读、追问对话）', usage: '生成 AI 解读内容，提供解读历史回顾', required: '必要' },
            { name: '塔罗日记内容（文字及您主动选择上传的图片）', usage: '在应用内保存和展示您的日记', required: '否' },
            { name: '签到与任务记录', usage: '提供打卡、连续签到等成长功能', required: '否' },
            { name: '订阅消息授权记录', usage: '仅在您授权后，向您发送解读提醒等订阅消息', required: '否' },
            { name: '分享与邀请记录', usage: '生成您的专属邀请码，记录邀请奖励', required: '否' },
            { name: '年度报告数据（解读次数、主题偏好等统计）', usage: '生成您的年度回顾报告', required: '否' },
            { name: '订单与支付信息（商品、金额、订单号、支付状态）', usage: '处理会员购买和单次解读购买', required: '必要（由微信支付处理）' },
            { name: '设备信息', usage: '仅在您的设备本地读取屏幕尺寸等信息用于生成分享海报，不会上传至我们的服务器；微信官方数据统计（页面访问、点击）由微信平台采集', required: '否' },
          ],
        },
      ],
    },
    {
      title: '二、我们如何使用信息',
      body: [
        { type: 'ul', text: 'AI解读：您的提问和选择的牌阵会发送到AI服务（DeepSeek）以生成解读内容。AI服务不会将您的个人信息用于其他用途。' },
        { type: 'ul', text: '支付处理：支付由微信支付处理，我们不会收集或存储您的信用卡/银行卡信息，仅保存订单号与支付结果用于核对订单。' },
        { type: 'ul', text: '数据存储：您的解读记录、日记、签到等数据存储在加密的服务器数据库中，仅在为您提供产品功能时被访问。' },
        { type: 'ul', text: '不对外共享：除法律法规要求或经您单独同意外，我们不会向任何第三方出售、共享您的个人信息。' },
        { type: 'ul', text: '不使用个人信息进行定向广告推荐。' },
      ],
    },
    {
      title: '三、信息的存储与保护',
      body: [
        { type: 'ul', text: '所有数据传输使用 HTTPS/TLS 加密' },
        { type: 'ul', text: '服务器位于中国大陆境内' },
        { type: 'ul', text: '我们采取合理的技术和管理措施保护您的数据安全' },
        { type: 'ul', text: '您的个人数据保存期限为账号存续期间；您注销账号或要求删除后，我们将在合理期限内删除或匿名化处理' },
      ],
    },
    {
      title: '四、您的权利',
      body: [
        { type: 'ul', text: '您可以在“我的”页面查看和删除解读记录' },
        { type: 'ul', text: '您可以要求我们删除您的全部数据（联系客服，见下方联系方式）' },
        { type: 'ul', text: '您可以随时撤回授权、取消订阅消息，或停止使用本小程序' },
        { type: 'ul', text: '您对个人信息的处理享有查阅、复制、更正、删除等《个人信息保护法》规定的权利' },
      ],
    },
    {
      title: '五、未成年人保护',
      body: [
        { type: 'p', text: '本产品面向成年人用户。如您是未满14周岁的未成年人，请在监护人指导下使用；我们不会主动收集未成年人的个人信息，如发现误收集，将及时删除。' },
      ],
    },
    {
      title: '六、免责声明',
      body: [
        { type: 'ul', text: '本产品定位为“娱乐与自我探索工具”' },
        { type: 'ul', text: 'AI生成的解读内容仅供自我觉察参考，不构成心理咨询、医疗、法律或金融建议' },
        { type: 'ul', text: '我们不提供算命、预测未来等迷信服务' },
      ],
    },
    {
      title: '七、联系我们',
      body: [
        { type: 'p', text: '如有隐私相关问题，请联系我们：' },
        { type: 'ul', text: '开发者：祁县天天开心商贸行(个体工商户)' },
        ...buildContactItems(),
        { type: 'ul', text: '我们将于15个工作日内回复您的请求。' },
        { type: 'strong', text: '更新日期：2026年7月31日' },
      ],
    },
  ],
  footer: '星光映照 v1.1 · 更新日期 2026-08-07',
};

Page({
  data: {
    doc: null,
  },

  onLoad(options) {
    const type = options.type || 'agreement';
    const doc = type === 'privacy' ? PRIVACY : AGREEMENT;
    this.setData({ doc });
    wx.setNavigationBarTitle({ title: doc.navTitle });
  },
});
