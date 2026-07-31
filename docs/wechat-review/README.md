# 微信审核材料包

本目录为星光映照小程序的微信审核材料包。提交审核前请逐项核对：

## 文档清单

| 材料 | 文件 | 状态 |
|------|------|------|
| 类目说明（含"占卜"字样答疑） | `category-explanation.md` | ✅ 已更新 2026-07-31 |
| 无迷信内容承诺书（非算命/非预测/仅供娱乐参考） | `no-superstition-statement.md` | ✅ 已更新 2026-07-31 |
| 隐私政策（按实际收集项重核） | `privacy-policy.md` | ✅ 已更新 2026-07-31 |
| 用户服务协议 | `user-agreement.md` | ✅ 已更新 2026-07-31 |
| 测试账号说明（含优惠码 REVIEW2026） | `test-account.md` | ✅ 已更新 2026-07-31 |
| 注册与配置指南 | `REGISTRATION-GUIDE.md` | ✅ 已更新 2026-07-31 |
| 关键页面截图 6 张 | `screenshots/` | ❌ **缺失，提交前必须补截** |
| 联系方式（隐私政策/用户协议/承诺书内【提交前填写】） | — | ⚠️ 提交前填写 |

## 提交前自检清单

- [ ] 类目说明文档 (`category-explanation.md`)
- [ ] 无迷信承诺书 (`no-superstition-statement.md`)
- [ ] 关键页面截图 6 张 (`screenshots/`)
- [ ] 测试账号信息 (`test-account.md`)
- [ ] 优惠码 REVIEW2026 后端已部署（backend/app/api/membership.py ✅ 已确认）
- [ ] 用户协议含"娱乐与自我探索工具"声明
- [ ] AI 解读均标注"仅供参考"
- [ ] 隐私政策 / 用户协议 / 承诺书中的联系方式已填写
- [ ] AppSecret 与 APIv3 密钥已重置（曾写入 git 历史，视为泄露）
- [ ] 小程序无 console 报错
- [ ] 所有页面可正常加载
- [ ] 健康检查全绿: `curl https://xingxiang.chat/health`
