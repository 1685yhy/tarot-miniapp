#!/usr/bin/env python3
"""
Tarot Card Image Generator v2
==============================
Improved tarot card generation using best available model (Flux preferred).
Generates 5 test cards with professional prompts to evaluate quality.

Usage:
    python generate_cards_v2.py
"""

import json
import time
import os
import urllib.request
import urllib.parse
import sys

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/mnt/e/tarot-miniapp/miniapp/images/cards_v2"

FLUX_CKPT = "flux2_dev_fp8mixed.safetensors"
SD_CKPT = "illustrious-xl-v2\\Illustrious-XL-v2.0.safetensors"

# 5 test cards — cover major arcana archetypes and one minor suit
TEST_CARDS = [
    {
        "filename": "major_00_the_fool.png",
        "name_zh": "愚者",
        "name_en": "The Fool",
        "kw": "new beginnings, innocence, adventure",
        "scene": "A young traveler stands at the edge of a cliff at sunrise, carrying a small bundle on a stick over one shoulder, a white rose in hand, a small dog at their heels, expansive sky.",
    },
    {
        "filename": "major_10_wheel_of_fortune.png",
        "name_zh": "命运之轮",
        "name_en": "Wheel of Fortune",
        "kw": "destiny, cycles, turning point",
        "scene": "A巨大 golden wheel inscribed with mystical alchemical symbols and letters, four winged creatures (angel, eagle, bull, lion) at the corners, clouds and celestial light.",
    },
    {
        "filename": "major_17_the_star.png",
        "name_zh": "星星",
        "name_en": "The Star",
        "kw": "hope, inspiration, healing",
        "scene": "A nude woman kneels beside a small pool, pouring water from two golden urns, one onto the earth and one into the water, a large brilliant eight-pointed star overhead, smaller stars around it, serene landscape.",
    },
    {
        "filename": "major_13_death.png",
        "name_zh": "死神",
        "name_en": "Death",
        "kw": "transformation, endings, new beginnings",
        "scene": "A skeletal figure in armor riding a pale horse, people of all stations lying before it (king, bishop, child), a rising sun between two towers in the background, dramatic chiaroscuro.",
    },
    {
        "filename": "wands_00_ace_of_wands.png",
        "name_zh": "权杖首牌",
        "name_en": "Ace of Wands",
        "kw": "creation, new opportunity, inspiration",
        "scene": "A hand emerging from a cloud grasping a flowering wooden staff, leaves sprouting from the staff, dramatic golden light, distant mountains and river below.",
    },
]

# ---------------------------------------------------------------------------
# ComfyUI API helpers
# ---------------------------------------------------------------------------

def queue_prompt(prompt_workflow):
    """Submit a workflow to ComfyUI and return the response."""
    data = json.dumps({"prompt": prompt_workflow}).encode("utf-8")
    req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    """Get generation history for a given prompt ID."""
    with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}") as resp:
        return json.loads(resp.read())


def wait_for_completion(prompt_id, timeout=600):
    """Block until the prompt finishes or timeout is reached."""
    start = time.time()
    while time.time() - start < timeout:
        history = get_history(prompt_id)
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(2)
    raise TimeoutError(f"Generation timed out after {timeout}s")


def get_image(filename, subfolder="", folder_type="output"):
    """Download a generated image by filename."""
    params = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": folder_type,
    })
    url = f"{COMFYUI_URL}/view?{params}"
    return urllib.request.urlopen(url).read()


# ---------------------------------------------------------------------------
# Model detection
# ---------------------------------------------------------------------------

def get_available_checkpoints():
    """Return list of checkpoint model names available in ComfyUI."""
    try:
        req = urllib.request.Request(
            f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple"
        )
        data = json.loads(urllib.request.urlopen(req).read())
        raw = (
            data
            .get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [])
        )
        # The first element is the list of names
        if raw and isinstance(raw[0], list):
            return raw[0]
        return []
    except Exception as e:
        print(f"[ERROR] Cannot connect to ComfyUI: {e}")
        sys.exit(1)


def find_model(available, name_fragment):
    """Find a checkpoint whose name contains the given fragment (case-insensitive)."""
    norm = name_fragment.replace("\\", "/").lower()
    for m in available:
        if norm in m.replace("\\", "/").lower():
            return m
    return None


# ---------------------------------------------------------------------------
# Workflow builders
# ---------------------------------------------------------------------------

def build_flux_workflow(prompt, seed, width=768, height=1024, ckpt_name="flux2_dev_fp8mixed.safetensors"):
    """
    Build a txt2img workflow for Flux models.

    Flux uses:
    - CheckpointLoaderSimple (model + clip + vae bundled)
    - CLIPTextEncodeFlux (separate clip_l and t5xxl inputs + guidance)
    - KSampler with cfg=1.0 (Flux handles guidance internally)
    """
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt_name},
        },
        "2": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip": ["1", 1],
                "clip_l": prompt,
                "t5xxl": prompt,
                "guidance": 3.5,
            },
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 28,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0],
            },
        },
        "5": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["4", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "SaveImage",
            "inputs": {"images": ["5", 0], "filename_prefix": "tarot_v2"},
        },
    }


def build_sd_workflow(prompt, negative_prompt, seed, width=512, height=768,
                      ckpt_name="illustrious-xl-v2\\Illustrious-XL-v2.0.safetensors"):
    """Build a txt2img workflow for SDXL / Illustrious models."""
    return {
        "3": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": ckpt_name},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["3", 1]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["3", 1]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": 30,
                "cfg": 7.0,
                "sampler_name": "euler_ancestral",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["7", 0],
            },
        },
        "7": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["3", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "tarot_v2"},
        },
    }


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def make_flux_prompt(card):
    """Build a prompt suited for Flux — natural description, rich detail."""
    return (
        f"Tarot card art, professional mystical illustration, "
        f"\"{card['name_en']}\" ({card['name_zh']}), "
        f"{card['scene']}, "
        f"Rider-Waite tarot style, oil painting, "
        f"intricate details, golden ornate border, "
        f"warm ethereal lighting, dark mystical background, "
        f"rich textures, deep shadows, masterpiece quality"
    )


def make_sd_prompt(card):
    """Build a prompt suited for SDXL/Illustrious — keyword-heavy, weighted."""
    return (
        f"tarot card art, professional oil painting illustration, "
        f"{card['name_zh']} ({card['name_en']}), "
        f"{card['scene']}, "
        f"Rider-Waite style, intricate details, golden ornate border, "
        f"dark mystical background, warm ethereal lighting, "
        f"rich textures, masterpiece, best quality, high detail"
    )


SD_NEGATIVE = (
    "anime, cartoon, manga, flat, simple, low detail, messy, "
    "blurry, watermark, text, signature, bad anatomy, distorted, "
    "amateur, unfinished, rough sketch"
)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_card(card, idx, total, use_flux, use_flux_prompts=True):
    """Generate one tarot card and save it."""
    filename = card["filename"]
    seed = hash(filename) % (2**32)

    if use_flux:
        prompt = make_flux_prompt(card) if use_flux_prompts else card.get("prompt", "")
        workflow = build_flux_workflow(prompt, seed)
    else:
        prompt = make_sd_prompt(card)
        workflow = build_sd_workflow(prompt, SD_NEGATIVE, seed)

    print(f"  [{idx+1}/{total}] {filename}")
    print(f"    Seed: {seed}")
    prompt_preview = prompt[:120] + "..." if len(prompt) > 120 else prompt
    print(f"    Prompt: {prompt_preview}")

    try:
        result = queue_prompt(workflow)
        prompt_id = result["prompt_id"]
        print(f"    Job ID: {prompt_id}")
        history = wait_for_completion(prompt_id)

        # Check for errors
        status = history.get("status", {})
        if status.get("error"):
            print(f"    FAIL: {status['error']}")
            return False

        outputs = history.get("outputs", {})
        saved = False
        for node_id, output in outputs.items():
            for img in output.get("images", []):
                img_data = get_image(img["filename"], img.get("subfolder", ""))
                out_path = os.path.join(OUTPUT_DIR, filename)
                with open(out_path, "wb") as f:
                    f.write(img_data)
                size_kb = len(img_data) // 1024
                print(f"    OK -> {out_path} ({size_kb} KB)")
                saved = True
        if not saved:
            print("    FAIL (no image output)")
            return False
        return True
    except Exception as e:
        print(f"    FAIL: {e}")
        return False


# ---------------------------------------------------------------------------
# Flux smoke test
# ---------------------------------------------------------------------------

def smoke_test_flux(ckpt_name):
    """Submit a tiny Flux job to verify the model actually works."""
    print("\n--- Smoke testing Flux model ---")
    # Minimal workflow: 256x256, 10 steps
    workflow = build_flux_workflow(
        "tarot card, test, golden border, dark background",
        9999, width=256, height=256, ckpt_name=ckpt_name,
    )
    # Override steps to be faster
    workflow["4"]["inputs"]["steps"] = 10
    try:
        result = queue_prompt(workflow)
        pid = result["prompt_id"]
        history = wait_for_completion(pid, timeout=120)
        outputs = history.get("outputs", {})
        for node_id, output in outputs.items():
            if output.get("images"):
                print("  Flux smoke test PASSED")
                return True
        status = history.get("status", {})
        print(f"  Flux smoke test FAILED: {status.get('error', 'no image output')}")
        return False
    except Exception as e:
        print(f"  Flux smoke test FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  Tarot Card Image Generator v2")
    print("  Professional card art with AI generation")
    print("=" * 65)

    # 1. Check available models
    print("\n[1/5] Checking available models...")
    available = get_available_checkpoints()
    print(f"  Found {len(available)} checkpoint(s) in ComfyUI")

    flux_available = find_model(available, "flux2_dev")
    sd_available = find_model(available, "illustrious-xl-v2")

    if flux_available:
        print(f"  Flux model FOUND: {flux_available}")
    else:
        print("  Flux model NOT FOUND")

    if sd_available:
        print(f"  SD model FOUND: {sd_available}")
    else:
        print("  SD model NOT FOUND")

    # 2. Decide which model to use
    print("\n[2/5] Selecting model...")
    use_flux = False
    model_name = ""

    if flux_available:
        print("  Flux is the primary choice — running smoke test...")
        flux_works = smoke_test_flux(flux_available)
        if flux_works:
            use_flux = True
            model_name = flux_available
            print("  => USING Flux model (superior quality)")
        else:
            print("  Flux smoke test failed — falling back...")
            if sd_available:
                use_flux = False
                model_name = sd_available
                print(f"  => USING SD model: {sd_available}")
            else:
                print("  No working model available!")
                sys.exit(1)
    elif sd_available:
        use_flux = False
        model_name = sd_available
        print(f"  => USING SD model: {sd_available}")
    else:
        print("  No supported model found!")
        sys.exit(1)

    # 3. Create output directory
    print("\n[3/5] Preparing output directory...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"  Output: {OUTPUT_DIR}")

    # 4. Generate test cards
    total = len(TEST_CARDS)
    print(f"\n[4/5] Generating {total} test cards...")

    if use_flux:
        print("  Prompt style: natural descriptive (Flux-optimized)")
        print(f"  Image size: 768x1024 (portrait card ratio)")
    else:
        print("  Prompt style: keyword-rich (SD/Illustrious-optimized)")
        print("  Negative prompt applied for quality filtering")
        print(f"  Image size: 512x768 (portrait card ratio)")

    success = 0
    for idx, card in enumerate(TEST_CARDS):
        if generate_card(card, idx, total, use_flux):
            success += 1

    # 5. Report
    print(f"\n[5/5] Results")
    print(f"  Model used: {model_name}")
    print(f"  Successful: {success}/{total}")
    print(f"  Output: {OUTPUT_DIR}")
    print()

    # Show prompts used
    print("=" * 65)
    print("  Sample Prompts")
    print("=" * 65)
    for card in TEST_CARDS:
        if use_flux:
            p = make_flux_prompt(card)
        else:
            p = make_sd_prompt(card)
        print(f"\n  [{card['filename']}]")
        print(f"  {p}")
    print()

    print("Done.")


if __name__ == "__main__":
    main()
