#!/usr/bin/env python3
"""Classify posts with cuisine and category tags using keyword matching."""

import json
import re
from pathlib import Path

DATA_FILE = Path("data/posts.json")

# tag -> regex patterns (matched case-insensitively against combined title + text)
RULES: dict[str, list[str]] = {
    # --- Category ---
    "cafe": [
        r"caf[eé]", r"specialty coffee", r"speciality coffee",
        r"espresso", r"flat white", r"cold brew", r"pour over",
        r"cappuccino", r"cortado", r"latte art", r"coffee roast",
        r"cha[- ]?chaan[- ]?teng",    # HK-style café
        r"high tea", r"afternoon tea", # tea service
        r"coffee (?:chain|roaster(?:y)?|bar)",  # coffee establishments
        r"\bcoffee\b",  # general coffee mentions (coffee shops, coffee brands)
    ],
    "hawker": [
        r"hawker cent(?:re|er)", r"hawker stall", r"food cent(?:re|er)",
        r"kopitiam", r"coffee shop", r"coffeeshop", r"food court",
        r"stall unit", r"hawker food",
        r"\bhawker\b",  # standalone "hawker" adjective (e.g. "hawker bakery")
        r"\bstall\b",   # generic stall references in SG food context
    ],
    "restaurant": [
        r"\brestaurant(?!-)", r"bistro", r"brasserie", r"eatery",
        r"dining room", r"dine-?in", r"fine dining",
        r"\bbuffet\b",   # buffet = restaurant setting
        r"\bizakaya\b",  # Japanese bar-restaurant (also in japanese)
        r"\bomakase\b",  # omakase dining (also in japanese)
        r"\breopens?\b", # venue reopening (almost always a food venue in this context)
        r"\bpop-?up\b",  # pop-up restaurant/food event
    ],
    "bakery": [
        r"bakerr?y", r"bakehouse", r"boulangerie", r"patisserie",
        r"sourdough (?:bread|loaf)",  # bare "sourdough" caused pizza FP
        r"croissant", r"loaf", r"bread shop",
        r"doughnut|donut",   # donut shops
        r"\bpau\b", r"\bbao\b",  # steamed bun shops
        r"egg tart",         # egg tart bakeries
        r"confectionery",    # confectionery / sweet shops
        r"\bpastries?\b",    # pastry / pastries
    ],
    "dessert": [
        r"ice cream", r"gelato", r"sorbet", r"dessert",
        r"creme brulee", r"tiramisu", r"panna cotta",
        r"pudding", r"lava cake", r"cheesecake",
        r"doughnut|donut",  # donuts as dessert
        r"egg tart",        # egg tarts as dessert
        r"tang yuan",       # glutinous rice balls
        r"\bcrepe",         # crepes
        r"confectionery",   # sweet treats
    ],
    "drinks": [
        r"bubble tea", r"boba", r"teh tarik", r"cocktail",
        r"mocktail", r"juice bar", r"smoothie", r"drinking chocolate",
        r"chai latte", r"milkshake",  # was \bchai(?: latte)? — fixed "chain"/"chai tow kway" FP
        r"\bmatcha\b",  # matcha drinks
        r"\bcoffee\b",  # coffee shops / coffee establishments
        r"\bfrappe\b",  # blended/iced coffee drinks
        r"green tea",   # green tea drinks
    ],
    # --- Cuisine ---
    "chinese": [
        r"wanto?n", r"char kway teow", r"ban mian", r"bak kut teh",
        r"dim sum", r"yum cha", r"char siu", r"chili crab",
        r"fish soup", r"lor mee", r"prawn (?:noodle|mee)",
        r"hokkien mee", r"chicken rice", r"claypot", r"zi char",
        r"tze char", r"wok hei", r"roast duck", r"roast pork",
        r"braised pork", r"steamed fish", r"congee", r"porridge",
        r"hor fun", r"kway chap", r"bak chor mee",
        r"cantonese", r"\bcanton\b",          # Cantonese cuisine
        r"\bhunan\b",                          # Hunan cuisine
        r"roast(?:ed)? meat",                  # Chinese roast meats (siu mei)
        r"rice dumpling", r"bak zhang", r"zongzi",  # rice dumplings
        r"tang yuan", r"ah balling", r"glutinous rice ball",  # tang yuan
        r"chai tow kway",                      # SG carrot cake = Chinese hawker dish
        r"cha[- ]?chaan[- ]?teng",            # HK-style diner (also in cafe)
    ],
    "japanese": [
        r"ramen", r"sushi", r"sashimi", r"omakase", r"izakaya",
        r"tonkatsu", r"udon", r"tempura", r"yakitori", r"kaiseki",
        r"wagyu", r"katsu", r"donburi", r"gyoza", r"onigiri",
        r"bento", r"japanese", r"teppanyaki", r"shabu", r"sukiyaki",
        r"chirashi", r"unagi",
    ],
    "korean": [
        r"korean", r"kimchi", r"bibimbap", r"bulgogi", r"galbi",
        r"tteokbokki", r"sundubu", r"samgyeopsal",
        r"japchae", r"k-?bbq", r"korean bbq", r"jjigae", r"jiggae",
        r"samgyetang",  # Korean chicken soup
        r"banchan",     # Korean side dishes
        r"\bseoul\b",   # Seoul = Korean food context
    ],
    "thai": [
        r"thai", r"pad thai", r"tom yum", r"green curry",
        r"massaman", r"som tam", r"mango (?:sticky )?rice",
        r"thai basil", r"larb", r"pad kra pao",
        r"mookata",  # Thai BBQ hotpot
    ],
    "western": [
        r"burger", r"smash burger", r"steak", r"pasta",
        r"pizza", r"brunch", r"eggs benedict", r"french toast",
        r"truffle (?:pasta|risotto|oil|cream|fries|sauce)",  # bare "truffle" caused Japanese dish FP
        r"risotto", r"western", r"sandwich", r"club sandwich",
        r"grill(?:ed)? meat", r"pork chop", r"lamb chop",
        r"\bitalian\b",    # Italian food = western
        r"\btacos?\b",     # tacos = western / Mexican
        r"baby back ribs", # American BBQ
    ],
    "indian": [
        r"indian", r"biryani", r"naan", r"roti prata", r"\bprata\b",
        r"masala", r"tandoori", r"dosa", r"\bdal\b", r"korma",
        r"butter chicken", r"tikka", r"curry leaf",
    ],
    "malay": [
        r"\bmalay\b",  # bare "malay" matched "Malaysia" in URLs — word boundary fix
        r"nasi lemak", r"rendang", r"\bsatay\b",
        r"\blaksa\b", r"mee rebus", r"mee siam", r"nasi padang",
        r"sup tulang", r"ikan bakar", r"sambal", r"asam pedas",
        r"nasi goreng",  # common Malay fried rice dish
    ],
    "vietnamese": [
        r"vietnamese", r"\bpho\b", r"banh mi", r"b[uú]n b[oò]",
        r"b[áa]nh", r"\bviet\b",
    ],
}

_COMPILED: dict[str, re.Pattern] = {
    tag: re.compile("|".join(patterns), re.IGNORECASE)
    for tag, patterns in RULES.items()
}


def classify(text: str) -> list[str]:
    return [tag for tag, rx in _COMPILED.items() if rx.search(text)]


def main() -> None:
    db = json.loads(DATA_FILE.read_text())
    posts = db.get("posts", [])
    changed = 0
    for post in posts:
        combined = " ".join(filter(None, [
            post.get("restaurant_name", ""),
            post.get("source_title", ""),
            post.get("text", ""),
        ]))
        tags = classify(combined)
        if post.get("tags") != tags:
            post["tags"] = tags
            changed += 1
    db["posts"] = posts
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2))
    print(f"Classified {len(posts)} posts ({changed} updated) — tags written to {DATA_FILE}")


if __name__ == "__main__":
    main()
