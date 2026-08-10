#!/usr/bin/env python3
"""生成 9 张虚拟支付道具图标（CogView-3-Flash，统一奶油疗愈风）"""
import base64, json, os, time, urllib.request, io
from PIL import Image

API_KEY = "6cefc41b0ab44d7ea8b5bfc5e0f125e0.UZNSPW2Zrism7y2L"
URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"
OUT = os.path.dirname(os.path.abspath(__file__))

STYLE = ("奶油米白治愈系背景,柔和光晕,高级简约,扁平插画风格,暖金色点缀,"
         "塔罗神秘氛围,中心单一主体,无文字无水印,正方形构图,高质量")

ITEMS = [
    ("single_reading", "单次深度占卜", "一张正在翻开的金色塔罗牌,牌面发出温柔星光"),
    ("membership_monthly", "月度会员", "金色王冠与新月组合,会员质感"),
    ("membership_yearly", "年度会员", "金色王冠与满月星空,闪耀星光"),
    ("membership_lifetime", "永久会员", "华丽金色王冠,永恒星光环绕"),
    ("membership_student", "特惠会员", "金色王冠与书本,青春简约"),
    ("annual_report", "年度运势报告", "金色卷轴与星图,年度报告质感"),
    ("birthchart_report", "本命星盘深度报告", "金色圆形星盘,星座连线,神秘深邃"),
    ("reading_pack_3", "3次深度解读包", "三张扇形展开的塔罗牌"),
    ("reading_pack_10", "10次深度解读包", "十张扇形展开的塔罗牌,更多星光"),
]

def gen_one(prompt: str, retries: int = 3) -> Image.Image:
    body = json.dumps({
        "model": "cogview-3-flash",
        "prompt": f"{prompt},{STYLE}",
        "size": "1024x1024",
    }).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, data=body, headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            })
            resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
            data = resp["data"][0]
            if data.get("url"):
                raw = urllib.request.urlopen(data["url"], timeout=60).read()
            else:
                raw = base64.b64decode(data["b64_json"])
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            w, h = img.size
            img = img.crop((0, 0, w, int(h * 0.92)))  # 裁掉水印
            return img
        except Exception as e:
            print(f"  重试 {i+1}: {e}")
            time.sleep(5)
    raise RuntimeError("生成失败")

for key, name, prompt in ITEMS:
    try:
        img = gen_one(prompt)
        img = img.resize((200, 200), Image.LANCZOS)
        path = os.path.join(OUT, f"{key}.png")
        img.save(path, "PNG")
        size = os.path.getsize(path)
        print(f"OK {key} ({name}): {size}B {'⚠️>200KB' if size > 200*1024 else '✅'}")
    except Exception as e:
        print(f"FAIL {key}: {e}")
