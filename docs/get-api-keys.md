# API Key 获取指南

## 1. Ludo.ai（游戏资产生成）

**步骤：**
1. 浏览器打开 https://ludo.ai
2. 点右上角 "Sign Up" 注册账号（用邮箱即可）
3. 登录后进入 Dashboard → API Keys
4. 创建一个新 Key，复制下来

**配置：**
```bash
# 在终端执行（或加到 ~/.bashrc）
export LUDO_API_KEY="你的Key"
```

## 2. NanoBanana / Gemini（2D原画生成）

**步骤：**
1. 浏览器打开 https://aistudio.google.com/apikey
2. 登录 Google 账号
3. 点 "Create API Key"
4. 选择 "Create API key in new project"
5. 复制生成的 Key（格式：AIza...）

**配置：**
```bash
export GEMINI_API_KEY="AIza..."
```

## 3. ComfyUI（本地AI图像生成，可选）

如果不想用云服务，可以在本地装 ComfyUI：
```bash
# 安装 ComfyUI（需要 NVIDIA GPU）
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI && pip install -r requirements.txt
python main.py  # 启动在 http://127.0.0.1:8188
```

---

> 拿到 LUDO_API_KEY 和 GEMINI_API_KEY 后告诉我，我帮你验证连通性。
