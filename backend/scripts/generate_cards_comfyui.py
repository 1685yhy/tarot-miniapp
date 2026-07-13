#!/usr/bin/env python3
"""
ComfyUI Batch Tarot Card Generator
通过 ComfyUI REST API 批量生成 78 张塔罗牌面
"""

import json
import uuid
import time
import os
import sys
import urllib.request
import urllib.parse

COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/mnt/e/tarot-miniapp/miniapp/images/cards"
CHECKPOINT = "illustrious-xl-v2\\Illustrious-XL-v2.0.safetensors"

# ── 78张塔罗牌数据 ──────────────────────────────────
MAJOR_ARCANA = [
    (0, "愚者", "The Fool", "新的开始、天真、冒险"),
    (1, "魔术师", "The Magician", "创造力、意志力、技巧"),
    (2, "女祭司", "The High Priestess", "直觉、神秘、潜意识"),
    (3, "皇后", "The Empress", "丰饶、母性、自然"),
    (4, "皇帝", "The Emperor", "权威、秩序、掌控"),
    (5, "教皇", "The Hierophant", "传统、信仰、教导"),
    (6, "恋人", "The Lovers", "爱情、选择、和谐"),
    (7, "战车", "The Chariot", "胜利、意志、前进"),
    (8, "力量", "Strength", "勇气、耐心、内在力量"),
    (9, "隐士", "The Hermit", "内省、智慧、孤独"),
    (10, "命运之轮", "Wheel of Fortune", "命运、转折、循环"),
    (11, "正义", "Justice", "公平、真相、因果"),
    (12, "倒吊人", "The Hanged Man", "牺牲、换个角度、等待"),
    (13, "死神", "Death", "结束、转变、新生"),
    (14, "节制", "Temperance", "平衡、调和、中庸"),
    (15, "恶魔", "The Devil", "欲望、束缚、物质主义"),
    (16, "高塔", "The Tower", "突变、崩塌、启示"),
    (17, "星星", "The Star", "希望、灵感、治愈"),
    (18, "月亮", "The Moon", "幻觉、恐惧、潜意识"),
    (19, "太阳", "The Sun", "快乐、成功、活力"),
    (20, "审判", "Judgement", "觉醒、重生、召唤"),
    (21, "世界", "The World", "完成、圆满、旅程终点"),
]

MINOR_SUITS = {
    "wands": {"zh": "权杖", "element": "火", "style": "warm amber flames, energetic"},
    "cups": {"zh": "圣杯", "element": "水", "style": "flowing blue water, emotional"},
    "swords": {"zh": "宝剑", "element": "风", "style": "sharp silver crystalline, intellectual"},
    "pentacles": {"zh": "星币", "element": "土", "style": "rich green gold earth, grounded"},
}

RANKS = [
    "Ace", "Two", "Three", "Four", "Five", "Six", "Seven",
    "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"
]
RANKS_ZH = [
    "首牌", "二", "三", "四", "五", "六", "七",
    "八", "九", "十", "侍从", "骑士", "皇后", "国王"
]


def queue_prompt(prompt_workflow):
    """提交工作流到 ComfyUI 队列"""
    data = json.dumps({"prompt": prompt_workflow}).encode("utf-8")
    req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    """获取生成历史"""
    with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}") as resp:
        return json.loads(resp.read())


def wait_for_completion(prompt_id, timeout=300):
    """等待图片生成完成"""
    start = time.time()
    while time.time() - start < timeout:
        history = get_history(prompt_id)
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"Generation timed out after {timeout}s")


def get_image(filename, subfolder="", folder_type="output"):
    """下载生成的图片"""
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type,
    })
    url = f"{COMFYUI_URL}/view?{params}"
    return urllib.request.urlopen(url).read()


def build_workflow(positive_prompt, negative_prompt, seed, width=512, height=768):
    """构建标准 txt2img 工作流"""
    return {
        "3": {
            "inputs": {"ckpt_name": CHECKPOINT},
            "class_type": "CheckpointLoaderSimple",
        },
        "4": {
            "inputs": {"text": positive_prompt, "clip": ["3", 1]},
            "class_type": "CLIPTextEncode",
        },
        "5": {
            "inputs": {"text": negative_prompt, "clip": ["3", 1]},
            "class_type": "CLIPTextEncode",
        },
        "6": {
            "inputs": {"seed": seed, "steps": 25, "cfg": 7.0,
                       "sampler_name": "euler_ancestral",
                       "scheduler": "normal",
                       "denoise": 1.0,
                       "model": ["3", 0],
                       "positive": ["4", 0],
                       "negative": ["5", 0],
                       "latent_image": ["7", 0]},
            "class_type": "KSampler",
        },
        "7": {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage",
        },
        "8": {
            "inputs": {"samples": ["6", 0], "vae": ["3", 2]},
            "class_type": "VAEDecode",
        },
        "9": {
            "inputs": {"images": ["8", 0], "filename_prefix": "tarot"},
            "class_type": "SaveImage",
        },
    }


def generate_card(prompt_data):
    """生成单张卡牌"""
    i, total, filename, positive, negative = prompt_data
    seed = hash(filename) % (2**32)
    workflow = build_workflow(positive, negative, seed)

    print(f"[{i+1}/{total}] {filename}...", end=" ", flush=True)
    try:
        result = queue_prompt(workflow)
        prompt_id = result["prompt_id"]
        history = wait_for_completion(prompt_id)

        # 找到输出文件名
        outputs = history["outputs"]
        for node_id, output in outputs.items():
            for img in output.get("images", []):
                img_data = get_image(img["filename"], img.get("subfolder", ""))
                out_path = os.path.join(OUTPUT_DIR, filename)
                with open(out_path, "wb") as f:
                    f.write(img_data)
                print(f"OK ({len(img_data)//1024}KB)")
                return True

        print("FAIL (no output)")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def generate_all():
    """生成所有 78 张牌"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    negative_common = "low quality, blurry, distorted, ugly, bad anatomy, watermark, text, signature"

    prompts = []
    # Major Arcana
    for num, zh, en, kw in MAJOR_ARCANA:
        filename = f"major_{num:02d}_{en.lower().replace(' ','_')}.png"
        positive = (
            f"masterpiece, best quality, tarot card illustration, "
            f"mystical fantasy art, {zh}({en}), "
            f"golden ornate border, dark mystical background, "
            f"detailed symbolism, elegant composition, "
            f"Rider-Waite tarot style, divine, sacred geometry, "
            f"rich colors, dramatic lighting, "
            f"tarot card on ornate table, "
            f"关键词:{kw}"
        )
        prompts.append((len(prompts), 78, filename, positive, negative_common))

    # Minor Arcana
    for suit_key, suit_info in MINOR_SUITS.items():
        for rank_idx, (rank, rank_zh) in enumerate(zip(RANKS, RANKS_ZH)):
            filename = f"{suit_key}_{rank_idx:02d}_{rank.lower()}_of_{suit_key}.png"
            positive = (
                f"masterpiece, best quality, tarot card illustration, "
                f"{suit_info['style']} style, "
                f"{suit_info['zh']}{rank_zh}, {rank} of {suit_key.title()}, "
                f"element of {suit_info['element']}, "
                f"golden ornate border, dark mystical background, "
                f"detailed symbolism, elegant composition, "
                f"Rider-Waite tarot style, divine, sacred geometry, "
                f"rich colors, dramatic lighting, "
                f"tarot card on ornate table"
            )
            prompts.append((len(prompts), 78, filename, positive, negative_common))

    # 按顺序生成
    print(f"Starting generation of {len(prompts)} cards using {CHECKPOINT}...")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Estimated time: {len(prompts) * 15} seconds (avg 15s/card)\n")

    success = 0
    for p in prompts:
        if generate_card(p):
            success += 1
        time.sleep(2)  # 避免过载

    print(f"\nDone: {success}/{len(prompts)} cards generated")


if __name__ == "__main__":
    generate_all()
