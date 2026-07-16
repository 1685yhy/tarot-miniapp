#!/usr/bin/env python3
"""
Tarot Card Wallpaper-Quality Generator
Generates 78 tarot cards via ComfyUI API using illustrious-xl-v2 at 1024x1536.
"""

import requests
import json
import time
import os
import sys
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"
OUTPUT_DIR = "/mnt/e/tarot-miniapp/miniapp/images/cards_v3"
PREVIEW_HTML = "/mnt/e/tarot-miniapp/miniapp/images/preview_v3.html"

MODEL_NAME = "illustrious-xl-v2\\Illustrious-XL-v2.0.safetensors"
WIDTH = 1024
HEIGHT = 1536
STEPS = 25
CFG = 7.5
SAMPLER = "euler_ancestral"
SCHEDULER = "karras"

os.makedirs(OUTPUT_DIR, exist_ok=True)

NEGATIVE_PROMPT = (
    "anime, cartoon, manga, low quality, blurry, distorted, "
    "text, signature, watermark, simple, flat, ugly, deformed, messy, "
    "worst quality, bad anatomy, error, extra digit, fewer digits, "
    "cropped, jpeg artifacts, signature, username, artist name"
)

# ─── Card Definitions ───────────────────────────────────────────────────

CARDS = [
    # Major Arcana
    {"file": "major_00_the_fool", "name": "The Fool",
     "prompt": "a young man standing at cliff edge with small white dog, carrying knapsack on stick over shoulder, rising sun behind him, innocent expression, colorful tunic, small bag of possessions"},
    {"file": "major_01_the_magician", "name": "The Magician",
     "prompt": "a figure standing at table with four suit symbols (wand, cup, sword, pentacle), one hand raised to sky holding wand, other hand pointing to earth, infinity symbol above head, red robe white tunic, blooming garden"},
    {"file": "major_02_the_high_priestess", "name": "The High Priestess",
     "prompt": "a serene woman seated between two pillars (black and white) with temple veil behind her, wearing blue robe and crescent moon crown, holding scroll, cross on chest, pomegranates and palms on pillars"},
    {"file": "major_03_the_empress", "name": "The Empress",
     "prompt": "a luxurious woman seated on throne in nature, wearing crown of stars, flowing pink gown, surrounded by lush wheat fields and forest, heart-shaped shield near throne, waterfall in background"},
    {"file": "major_04_the_emperor", "name": "The Emperor",
     "prompt": "a stern bearded man seated on stone throne decorated with ram heads, wearing armor and red robe, holding an ankh scepter and orb, barren mountains behind him, authoritative pose"},
    {"file": "major_05_the_hierophant", "name": "The Hierophant",
     "prompt": "a religious figure seated between two pillars, wearing triple crown and red robe, right hand making blessing gesture, left hand holding triple cross scepter, two kneeling followers before him"},
    {"file": "major_06_the_lovers", "name": "The Lovers",
     "prompt": "a man and woman standing beneath a large angel figure with wings outstretched, blessing them, garden of eden setting, tree of life behind woman, tree of knowledge behind man, serpent"},
    {"file": "major_07_the_chariot", "name": "The Chariot",
     "prompt": "a triumphant figure standing in a chariot pulled by two sphinxes (black and white), wearing armor and crown with star, holding wand, city in background, canopy of stars overhead"},
    {"file": "major_08_strength", "name": "Strength",
     "prompt": "a woman in white gown gently closing the jaws of a lion, wearing flower garland, infinity symbol above her head, lush green landscape, peaceful expression, mastery and courage"},
    {"file": "major_09_the_hermit", "name": "The Hermit",
     "prompt": "an old bearded man standing on snowy mountain peak, wearing grey robe and hood, holding a lantern with glowing star inside, leaning on staff, solitude and wisdom"},
    {"file": "major_10_wheel_of_fortune", "name": "Wheel of Fortune",
     "prompt": "a large golden wheel with eight-spokes, four figures at corners (angel, eagle, bull, lion reading books), snake coiled on left, jackal figure on right ascending, winged creatures, clouds"},
    {"file": "major_11_justice", "name": "Justice",
     "prompt": "a figure seated on throne holding golden scales in left hand and upright sword in right, wearing crown, red robe and green mantle, between two pillars, impartial judgment"},
    {"file": "major_12_the_hanged_man", "name": "The Hanged Man",
     "prompt": "a figure hanging upside down from a T-shaped wooden cross by one foot, right foot crossed behind left, hands tied behind back, serene expression, golden halo around head"},
    {"file": "major_13_death", "name": "Death",
     "prompt": "a skeletal figure on a white horse wearing armor, trampling a king and a maiden, bishop praying, rising sun between two towers in background, white rose banner on spear"},
    {"file": "major_14_temperance", "name": "Temperance",
     "prompt": "a winged angel figure with glowing sun crown, pouring liquid between two cups (gold and silver), one foot in water one on land, iris flowers, path to distant mountains"},
    {"file": "major_15_the_devil", "name": "The Devil",
     "prompt": "a large horned demon figure with bat wings standing on pedestal, chained naked figures (man and woman) below, inverted pentagram on forehead, torch in hand, dark cavern setting"},
    {"file": "major_16_the_tower", "name": "The Tower",
     "prompt": "a tall stone tower on rocky mountain peak struck by lightning with flames bursting from windows, two figures falling headfirst, crown falling, dark stormy sky"},
    {"file": "major_17_the_star", "name": "The Star",
     "prompt": "a kneeling nude woman at pool of water pouring two vessels, one into water one onto land, large central eight-pointed star surrounded by seven smaller stars, tree and bird in background"},
    {"file": "major_18_the_moon", "name": "The Moon",
     "prompt": "a full moon with face, two towering pillars, wolf and dog howling at moon, crayfish emerging from water, path winding into distant mountains, twin towers, mysterious night"},
    {"file": "major_19_the_sun", "name": "The Sun",
     "prompt": "a large radiant smiling sun shining down on a naked child riding a white horse, red banner waving, sunflowers growing behind stone wall, joyful garden setting"},
    {"file": "major_20_judgement", "name": "Judgement",
     "prompt": "a winged angel Gabriel blowing trumpet with banner, dead rising from tombs below, people standing with arms raised in awe, mountains and ocean in background, resurrection scene"},
    {"file": "major_21_the_world", "name": "The World",
     "prompt": "a dancing nude woman wrapped in purple scarf, holding two wands, oval wreath of flowers surrounding her, four figures at corners (angel, eagle, bull, lion), completion and wholeness"},
]

# Suit card templates
SUIT_TEMPLATES = {
    "wands": {
        "theme": "fire, creativity, energy, passion, dynamic action, warm golden light, bold courageous spirit",
        "suit_symbol": "flaming wooden wands, fire element, salamanders",
        "color_scheme": "rich orange and crimson warm tones, golden amber light"
    },
    "cups": {
        "theme": "water, emotions, love, intuition, relationships, dreamy atmosphere, gentle flowing energy",
        "suit_symbol": "golden chalices and cups, water element, lotus flowers",
        "color_scheme": "deep blues and aquamarine, soft pearl white, iridescent tones"
    },
    "swords": {
        "theme": "air, intellect, truth, challenges, justice, sharp rationality, winds of change",
        "suit_symbol": "crossed swords, air element, clouds and wind",
        "color_scheme": "cool steel blues and stormy greys, crisp icy silver"
    },
    "pentacles": {
        "theme": "earth, material wealth, work, prosperity, nature, abundance, grounded stability",
        "suit_symbol": "golden pentacle coins, earth element, lush vineyards and gardens",
        "color_scheme": "earthy greens and rich browns, golden harvest tones"
    }
}

SUIT_CARDS = {
    "wands": [
        ("ace_of_wands", "a hand emerging from cloud holding a flowering wand, white blossoms blooming, castle in distance, purple drapes, fiery passion and new creative spark"),
        ("two_of_wands", "a figure standing on battlements holding globe in right hand and wand in left, looking outward, shoreline and ships, planning and future vision"),
        ("three_of_wands", "a figure standing on cliff overlooking ships at sea, three planted wands, wide horizon, trade and expansion, looking outward"),
        ("four_of_wands", "four tall wands decorated with flower garlands forming a canopy, two women dancing with bouquets, castle in background, celebration and homecoming"),
        ("five_of_wands", "five figures each holding wands in a chaotic struggle, fighting upward, dynamic energy, conflict and competition, aggressive but no injury"),
        ("six_of_wands", "a triumphant figure on horseback wearing laurel crown, followers holding wands, cheering crowd, victory and public recognition"),
        ("seven_of_wands", "a figure on rocky ground fighting six wands from below, standing firm on higher ground, defense against opposition, holding the line"),
        ("eight_of_wands", "eight flying wands arcing through sky toward ground, river and distant village, rapid movement, swift action, things falling into place"),
        ("nine_of_wands", "a bandaged weary figure leaning on wand, eight wands planted behind like fence, guarded and resilient, perseverance through hardship"),
        ("ten_of_wands", "a figure struggling under heavy burden of ten bundled wands, plowed field ahead, overwhelming responsibility, hard labor"),
        ("page_of_wands", "a young figure in bright tunic holding a flowering wand, pyramids in background, desert landscape, enthusiastic messenger, adventurous spirit"),
        ("knight_of_wands", "a knight in armor on rearing red horse, holding a flowering wand, flames around, desert background, bold action, passionate energy"),
        ("queen_of_wands", "a regal queen seated on throne decorated with salamanders and sunflowers, holding sunflower and wand, black cat at feet, warmth and confidence"),
        ("king_of_wands", "a king on throne decorated with salamanders and lions, holding flowering wand, golden crown, fiery ambitious ruler, visionary leadership"),
    ],
    "cups": [
        ("ace_of_cups", "a hand from cloud holding a golden overflowing chalice with a dove descending holding a wafer with cross, lotus flowers in water below, love and new emotions"),
        ("two_of_cups", "a man and woman facing each other holding golden cups, cups above them connected by caduceus with lion head, winged lion, partnership and union"),
        ("three_of_cups", "three maidens dancing in circle holding cups raised high, flowers and gourds around them, harvest celebration, friendship and joy"),
        ("four_of_cups", "a young man seated under tree with arms crossed looking dissatisfied at three cups before him, a hand offering a fourth cup from cloud, apathy and contemplation"),
        ("five_of_cups", "a cloaked figure staring at three spilled cups on ground, two upright cups behind, river and stone bridge, loss and grief but hope remains"),
        ("six_of_cups", "a young boy offering a cup with flower to a smaller girl in a garden of blooming cups, stone walls, protective nostalgia and innocent memories"),
        ("seven_of_cups", "a silhouette figure facing seven cups on rainbow cloud offering visions: castle, jewel, wreath, serpent, cloak, dragon, beautiful face, illusions and choices"),
        ("eight_of_cups", "a cloaked figure walking away from eight stacked cups, walking toward dark mountains under moonlit sky, abandoning what no longer serves, spiritual quest"),
        ("nine_of_cups", "a smug well-dressed figure seated on stool with arms crossed, nine golden cups arranged in rainbow behind him, contentment and wishes fulfilled"),
        ("ten_of_cups", "radiant rainbow spanning sky over happy family embracing, cottage and garden, ten golden cups arranged in rainbow arc, emotional bliss and divine love"),
        ("page_of_cups", "a young figure in blue tunic gazing at a cup with a fish peeking out, ocean waves behind, curious messenger of emotions and creative inspiration"),
        ("knight_of_cups", "a knight in armor riding a white horse, holding out a golden cup, peaceful landscape, flowing river, romantic idealist on a quest"),
        ("queen_of_cups", "a queen on throne on seashore, holding ornate covered cup decorated with angels, gazing at cup, shell throne, mermaid imagery, deep intuition and emotional wisdom"),
        ("king_of_cups", "a king on throne floating on stormy sea, holding cup and cross scepter, fish pendant around neck, one foot on sea, emotionally mature ruler"),
    ],
    "swords": [
        ("ace_of_swords", "a hand from cloud holding upright sword with crown and olive branch, snowy mountain peaks, piercing clarity and breakthrough of truth"),
        ("two_of_swords", "a blindfolded woman in white robe seated on stone bench holding two crossed swords over shoulders, crescent moon and water behind, difficult decision"),
        ("three_of_swords", "a heart pierced by three swords, storm clouds and rain, pierced heart floating in dark sky, heartbreak, sorrow and painful truth"),
        ("four_of_swords", "a reclining figure lying on church tomb with one sword beneath, three swords mounted on wall above, stained glass window showing kneeling figure, rest and recovery"),
        ("five_of_swords", "a figure with three swords looking back at two defeated figures walking away, stormy sky, conflict with hollow victory and shame"),
        ("six_of_swords", "a ferryman poling a boat with woman and child, six swords sticking up from boat floor, calm water ahead, troubled water behind, transition and moving on"),
        ("seven_of_swords", "a figure sneaking away from camp carrying five swords, two remaining swords stuck in ground, enemy tents, deception and strategic retreat"),
        ("eight_of_swords", "a blindfolded woman bound and surrounded by eight standing swords in muddy ground, castle on hill, feeling trapped and restricted by negative thoughts"),
        ("nine_of_swords", "a distraught figure sitting up in bed with face in hands, nine swords hanging on wall above, carved relief of defeat, nightmares and anxiety"),
        ("ten_of_swords", "a figure lying face down with ten swords piercing back, one hand making blessing sign, but dawn rising and still water, painful end but new beginning"),
        ("page_of_swords", "a young figure standing on rocky ground holding a sword aloft with both hands, stormy clouds clearing, swift messenger of truth and ideas"),
        ("knight_of_swords", "a knight on armored white horse charging forward with sword raised, storm clouds, trees blown by wind, birds fleeing, swift action and determination"),
        ("queen_of_swords", "a queen seated on throne holding upright sword, left hand extended, storm clouds behind but clear ahead, butterfly crown, wise and perceptive ruler"),
        ("king_of_swords", "a king seated on simple stone throne holding upright sword, stern expression, distant mountains, clouds, intellectually powerful authority and ethical judgment"),
    ],
    "pentacles": [
        ("ace_of_pentacles", "a hand from cloud holding a large golden pentacle coin, garden of lilies and roses below, green meadow, gateway to abundance and new financial beginnings"),
        ("two_of_pentacles", "a dancing figure juggling two pentacles linked by lemniscate, ships on stormy sea behind, balancing act and adaptability with resources"),
        ("three_of_pentacles", "a young apprentice working on cathedral column, two master craftsmen with plans, monastery, collaboration and skillful craftsmanship"),
        ("four_of_pentacles", "a figure clutching two pentacles, standing on two more, crown on head but miserly expression, city behind, holding onto material wealth, possessiveness"),
        ("five_of_pentacles", "two impoverished figures walking past church in snow, one on crutches, five pentacles on church window, material hardship and spiritual crisis"),
        ("six_of_pentacles", "a merchant in red robe distributing coins to beggars, holding balanced scales, generosity and charity, sharing wealth"),
        ("seven_of_pentacles", "a young man leaning on hoe gazing at abundant pentacle vine growing on trellis, ripe harvest, patience and assessment of long-term investment"),
        ("eight_of_pentacles", "an apprentice craftsman hammering pentacles on coins, workbench, completed pentacles on wall, diligent skill-building and craftsmanship"),
        ("nine_of_pentacles", "a woman in luxurious gown standing in vineyard, pentacle vine, a hooded falcon on her hand, estate and castle, self-sufficient luxury and refinement"),
        ("ten_of_pentacles", "an elderly man with two dogs, a couple and child before archway, ten pentacles arranged in tree of life pattern, inheritance and lasting wealth"),
        ("page_of_pentacles", "a young figure in green tunic holding a golden pentacle floating above cupped hands, fertile field behind, eager student of material world"),
        ("knight_of_pentacles", "a knight on heavy black horse holding a pentacle, plowed field behind, slow steady movement, diligent and methodical worker"),
        ("queen_of_pentacles", "a queen on lush throne in nature, holding golden pentacle, rabbit at feet, flowering meadow, nurturing and practical abundance"),
        ("king_of_pentacles", "a king on throne decorated with bulls and grapes, holding pentacle and scepter, castle and vineyard, prosperous and reliable leader"),
    ],
}

# Build full card list
def build_all_cards():
    all_cards = list(CARDS)  # Major arcana

    # Minor arcana by suit
    for suit in ["wands", "cups", "swords", "pentacles"]:
        for i, (card_suffix, description) in enumerate(SUIT_CARDS[suit]):
            suit_names = {"wands": "Wands", "cups": "Cups", "swords": "Swords", "pentacles": "Pentacles"}
            rank_names = [
                "Ace", "Two", "Three", "Four", "Five", "Six", "Seven",
                "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"
            ]
            card_name = f"{rank_names[i]} of {suit_names[suit]}"

            template = SUIT_TEMPLATES[suit]
            full_desc = (
                f"{description}, "
                f"{template['suit_symbol']}, "
                f"{template['color_scheme']}, "
                f"rich tarot symbolism and meaning"
            )

            all_cards.append({
                "file": f"{suit}_{i:02d}_{card_suffix}",
                "name": card_name,
                "prompt": full_desc
            })

    return all_cards

ALL_CARDS = build_all_cards()


# ─── ComfyUI API ────────────────────────────────────────────────────────

def build_workflow(positive_prompt, seed, filename_prefix):
    """Build a ComfyUI API workflow JSON for SDXL image generation."""
    workflow = {
        "3": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": MODEL_NAME
            }
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": positive_prompt,
                "clip": ["3", 1]
            }
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": NEGATIVE_PROMPT,
                "clip": ["3", 1]
            }
        },
        "6": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": WIDTH,
                "height": HEIGHT,
                "batch_size": 1
            }
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": STEPS,
                "cfg": CFG,
                "sampler_name": SAMPLER,
                "scheduler": SCHEDULER,
                "denoise": 1.0,
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0]
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["3", 2]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": filename_prefix
            }
        }
    }
    return workflow


def queue_prompt(workflow):
    """Submit a workflow to ComfyUI and return the prompt_id."""
    r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow})
    if r.status_code != 200:
        raise RuntimeError(f"Failed to queue prompt: {r.status_code} {r.text}")
    result = r.json()
    if "error" in result:
        raise RuntimeError(f"ComfyUI error: {result['error']}")
    return result["prompt_id"]


def wait_for_completion(prompt_id, timeout=120):
    """Poll until the prompt is done, return the history record."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if prompt_id in data:
                    return data[prompt_id]
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")


def download_image(filename, subfolder="", folder_type="output"):
    """Download a generated image from ComfyUI."""
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    r = requests.get(f"{COMFY_URL}/view", params=params)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download {filename}: {r.status_code}")
    return r.content


def get_files_from_output(node_id, history):
    """Extract filenames from a SaveImage node's output."""
    outputs = history.get("outputs", {})
    node_output = outputs.get(node_id, {})
    images = node_output.get("images", [])
    return images  # list of {filename, subfolder, type}


def generate_card(card, test_mode=False):
    """Generate one tarot card. Returns the card file path on success."""
    if not test_mode:
        # Build an enhanced prompt for wallpaper quality
        enhanced_prompt = (
            f"masterpiece tarot card, professional illustration, {card['name']}, "
            f"{card['prompt']}, "
            f"intricate golden ornamental border, rich mystical symbolism, "
            f"deep indigo and warm gold color scheme, dramatic atmospheric lighting, "
            f"oil painting aesthetic, highly detailed, ornate, divine, "
            f"sacred geometry, celestial background, luminous, magical realism, "
            f"tarot card art on dark velvet, premium card stock texture, "
            f"Rider-Waite-Smith style, ethereal glow, intricate details, "
            f"elaborate frame, medieval manuscript style borders"
        )
    else:
        # For test cards, use simpler prompt for faster generation check
        enhanced_prompt = (
            f"tarot card, {card['name']}, {card['prompt']}, "
            f"intricate golden border, mystical symbolism, "
            f"deep indigo and gold color, dramatic lighting, "
            f"oil painting, highly detailed, ornate"
        )

    seed = card.get("number", 0) * 100

    # Parse card number from the filename for seeding
    parts = card["file"].split("_")
    if parts[0] == "major":
        seed = int(parts[1]) * 100 + 42
    else:
        seed = (hash(parts[0]) % 10000 + int(parts[1])) * 100 + 42
    # Make sure seed is positive
    seed = abs(seed) % 18446744073709551615

    filename_prefix = f"tarot_{card['file']}"

    workflow = build_workflow(enhanced_prompt, seed, filename_prefix)

    print(f"  Queueing {card['file']}... (seed={seed})")
    try:
        prompt_id = queue_prompt(workflow)
        print(f"  Prompt ID: {prompt_id}")

        history = wait_for_completion(prompt_id, timeout=180)

        images = get_files_from_output("9", history)
        if not images:
            raise RuntimeError("No output images found in history")

        img_info = images[0]
        img_data = download_image(img_info["filename"], img_info.get("subfolder", ""), img_info.get("type", "output"))

        output_path = os.path.join(OUTPUT_DIR, f"{card['file']}.png")
        with open(output_path, "wb") as f:
            f.write(img_data)

        file_size_kb = len(img_data) / 1024
        print(f"  Saved to {card['file']}.png ({file_size_kb:.0f} KB)")

        return output_path

    except Exception as e:
        print(f"  ERROR generating {card['file']}: {e}")
        return None


def generate_all_cards(start_from=0, test_count=0):
    """Generate cards from start_from index."""
    total = len(ALL_CARDS)

    if test_count > 0:
        cards_to_generate = ALL_CARDS[:test_count]
        print(f"\n{'='*60}")
        print(f"TEST MODE: Generating first {test_count} cards")
        print(f"{'='*60}\n")
    else:
        cards_to_generate = ALL_CARDS[start_from:]
        print(f"\n{'='*60}")
        print(f"BATCH MODE: Generating {len(cards_to_generate)} cards from index {start_from}")
        print(f"{'='*60}\n")

    results = []
    for i, card in enumerate(cards_to_generate):
        idx = start_from + i
        print(f"\n[{idx+1}/{total}] {card['file']} - {card['name']}")
        path = generate_card(card)
        if path:
            results.append({"index": idx, "card": card, "path": path})
        else:
            print(f"  FAILED: {card['file']}")

        # Small delay between cards
        time.sleep(0.5)

    success = len(results)
    failed = len(cards_to_generate) - success
    print(f"\n{'='*60}")
    print(f"Done: {success} generated, {failed} failed")
    print(f"{'='*60}")

    return results


def create_preview_html(results):
    """Create an HTML preview of all generated cards."""
    cards_html = ""
    for r in results:
        card = r["card"]
        cards_html += f"""
        <div class="card">
            <img src="cards_v3/{card['file']}.png" alt="{card['name']}" loading="lazy">
            <div class="card-name">{card['name']}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tarot Cards v3 - Wallpaper Quality Preview</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0a0a14;
    color: #e0d8c8;
    font-family: 'Georgia', serif;
    padding: 2rem;
}}
h1 {{
    text-align: center;
    color: #c9a84c;
    font-size: 2.2rem;
    margin-bottom: 0.5rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
}}
.subtitle {{
    text-align: center;
    color: #887a5c;
    margin-bottom: 2rem;
    font-style: italic;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1.5rem;
    max-width: 1800px;
    margin: 0 auto;
}}
.card {{
    background: #12121e;
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
}}
.card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.5), 0 0 20px rgba(201,168,76,0.15);
    border-color: #c9a84c44;
}}
.card img {{
    width: 100%;
    height: auto;
    display: block;
    aspect-ratio: 2/3;
    object-fit: cover;
}}
.card-name {{
    padding: 0.8rem;
    text-align: center;
    font-size: 0.9rem;
    color: #c9a84c;
    border-top: 1px solid #1a1a2e;
}}
.stats {{
    text-align: center;
    margin-bottom: 1.5rem;
    color: #887a5c;
    font-size: 0.9rem;
}}
</style>
</head>
<body>
<h1>✦ Tarot Cards v3 ✦</h1>
<p class="subtitle">Wallpaper Quality — 1024 × 1536 — Illustrious XL v2</p>
<p class="stats">{len(results)} cards generated</p>
<div class="grid">
{cards_html}
</div>
</body>
</html>"""

    with open(PREVIEW_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Preview HTML: {PREVIEW_HTML}")


# ─── Main ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate tarot cards via ComfyUI")
    parser.add_argument("--test", action="store_true", help="Generate only 3 test cards")
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based)")
    parser.add_argument("--count", type=int, default=0, help="Number of cards to generate (0 = all)")
    parser.add_argument("--no-preview", action="store_true", help="Skip preview HTML creation")
    args = parser.parse_args()

    print(f"Tarot Card Generator v3 - Wallpaper Quality")
    print(f"Model: {MODEL_NAME}")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Steps: {STEPS}, CFG: {CFG}, Sampler: {SAMPLER}")
    print(f"Total cards defined: {len(ALL_CARDS)}")
    print(f"Output: {OUTPUT_DIR}")

    if args.test:
        results = generate_all_cards(test_count=3)
    elif args.count > 0:
        results = generate_all_cards(start_from=args.start, test_count=args.count)
    else:
        results = generate_all_cards(start_from=args.start)

    if results and not args.no_preview:
        create_preview_html(results)

    print("\nDone!")
