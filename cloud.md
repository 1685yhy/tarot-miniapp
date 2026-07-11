# Cloud Art Asset Policy

## 美术资产生成规则

**适用范围：本项目及所有 Claude Code 项目**

本项目涉及以下类型的美术资产时，必须遵守此规则：

- 2D 人物立绘
- 场景图 / 背景图
- 3D 模型
- 特效（粒子、光效等）
- 图标 / UI 装饰元素
- 卡牌面 / 插画

### 强制规则

1. **必须通过已配置的 MCP 工具调用外部美术服务生成原始资产。**
   可用服务包括但不限于：
   - Ludo.ai MCP — 一站式游戏资产生成
   - NanoBanana MCP — 2D 原画 / 插画生成
   - Unity MCP — 3D 模型与场景资产（Unity Editor 内）
   - Blender MCP — 3D 建模与渲染（需本地 Blender 运行）
   - ComfyUI MCP — AI 图像生成工作流（需本地 ComfyUI 运行）

2. **代码层只负责把资产接入引擎。**
   - 代码负责：加载图片、挂载模型、绑定材质、播放特效
   - 代码禁止：用纯 CSS 模拟画面、用 HTML Canvas 2D 手绘视觉、用代码生成几何体替代模型

3. **任何视觉画面必须有对应的原始资产文件。**
   - 图片：PNG / JPG / WebP / SVG（由 AI 服务生成）
   - 3D：FBX / GLB / OBJ / Blend（由 3D 工具生成）
   - 特效：贴图序列帧 / Shader Graph 材质（由对应工具生成）

4. **遇到美术需求自动走此规则，不需人工提醒。**

### MCP 连通性要求

| MCP 服务 | 类型 | 所需凭证 | 状态检查方式 |
|----------|------|----------|-------------|
| Unity MCP | Unity Editor 内建 | 无（Unity 6 AI Assistant） | `mcp__unity-mcp__debug_request_context` |
| ComfyUI MCP | 本地 npx | 无（本地 ComfyUI URL） | 调用 ComfyUI API |
| Ludo.ai MCP | HTTP API | `LUDO_API_KEY` | 调用 Ludo.ai API |
| NanoBanana MCP | HTTP API | `GEMINI_API_KEY` | 调用 Gemini API |
| Blender MCP | 本地进程 | 无（本地 Blender） | 检查 Blender 进程 |

### 违规处理

如果 Agent 尝试用 CSS / Canvas / 纯代码模拟视觉画面：
1. 立即停止
2. 检查可用的 MCP 美术服务
3. 通过 MCP 工具生成真正的资产文件
4. 将资产文件放入项目 assets/ 目录
5. 在代码中加载资产文件

---

> 此规则写入全局 memory 和项目 cloud.md，对所有 Claude Code 项目生效。
