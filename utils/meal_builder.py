from models.cluster_model      import ClusterModel
from utils.protein_detector import detect_protein

cluster_model = ClusterModel()

# ─────────────────────────────────────────────────────────────
# ROLE CLASSIFICATION
# ─────────────────────────────────────────────────────────────

PROTEIN_KEYWORDS = [
    "chicken", "beef", "salmon", "tuna", "turkey", "tofu",
    "shrimp", "pork", "lamb", "egg", "tilapia", "cod", "fish",
    "steak", "brisket", "meatball", "sausage", "tempeh"
]

STARCH_KEYWORDS = [
    "rice", "pasta", "potato", "noodle", "quinoa", "bread",
    "couscous", "farro", "tortilla", "roll", "mac", "fries",
    "cornbread", "polenta", "grits", "pita", "flatbread"
]

VEGETABLE_KEYWORDS = [
    "broccoli", "spinach", "salad", "kale", "carrot", "pepper",
    "zucchini", "asparagus", "corn", "peas", "greens", "cabbage",
    "bok choy", "edamame", "squash", "tomato", "cucumber",
    "lettuce", "arugula", "beet", "green bean", "brussels"
]

COMBO_KEYWORDS = [
    "bowl", "wrap", "sandwich", "burger", "pizza", "burrito",
    "stew", "soup", "casserole", "plate", "sub"
]


def classify_role(item):
    """
    Classifies a scraped food item into a meal assembly role.

    Searches ingredients first (more reliable), then item name,
    then falls back to macro ratios.

    Roles:
      protein_main  → primary protein source
      starch        → carbohydrate base
      vegetable     → non-starchy vegetable side
      combo         → standalone complete meal, skips assembly
      other         → desserts, drinks, condiments — excluded
    """
    search_text = f"{item.get('ingredients', '')} {item['meal_name']}".lower()
    cal         = item.get("calories", 0)

    # combo check first — substantial standalone meals skip assembly
    if any(kw in search_text for kw in COMBO_KEYWORDS) and cal >= 350:
        return "combo"

    if any(kw in search_text for kw in PROTEIN_KEYWORDS):
        return "protein_main"
    if any(kw in search_text for kw in STARCH_KEYWORDS):
        return "starch"
    if any(kw in search_text for kw in VEGETABLE_KEYWORDS):
        return "vegetable"

    # macro ratio fallback
    if cal > 0:
        protein_pct = (item.get("protein", 0) * 4) / cal
        carb_pct    = (item.get("carbs",   0) * 4) / cal
        if protein_pct >= 0.35:
            return "protein_main"
        elif carb_pct >= 0.55:
            return "starch"
        elif cal < 120:
            return "vegetable"

    return "other"


# ─────────────────────────────────────────────────────────────
# MEAL ASSEMBLY
# ─────────────────────────────────────────────────────────────

def build_meal(items, structure, dining_hall):
    """
    Combines a list of individual food items into one assembled meal.

    Sums all macros, joins component names and cluster ids.
    component_clusters stores each component's cluster as a
    comma separated string so recommender can reconstruct
    components_with_clusters for the preference model.

    Example:
      components         = "Grilled Chicken,Brown Rice,Broccoli"
      component_clusters = "A,B,D"
    """
    # protein_type taken from whichever component is the protein_main
    protein_type = "unknown"
    for item in items:
        if item.get("role") == "protein_main":
            protein_type = item.get("protein_type", "unknown")
            break

    return {
        "meal_name":          " + ".join(i["meal_name"] for i in items),
        "components":         ",".join(i["meal_name"] for i in items),
        "component_clusters": ",".join(i.get("cluster_id", "G") for i in items),
        "calories":           sum(i.get("calories", 0) for i in items),
        "protein":            sum(i.get("protein",  0) for i in items),
        "carbs":              sum(i.get("carbs",    0) for i in items),
        "fats":               sum(i.get("fats",     0) for i in items),
        "protein_type":       protein_type,
        "dining_hall":        dining_hall,
        "structure":          structure
    }


def generate_combinations(items, dining_hall):
    """
    Generates all valid meal combinations from individual items
    at one dining hall.

    Assembly structures:
      protein + starch + vegetable  → most complete meal
      protein + vegetable           → low carb option
      combo                         → standalone, no assembly needed
      protein + starch              → fallback if no vegetables

    Items must already have role and cluster_id attached.
    """
    proteins   = [i for i in items if i.get("role") == "protein_main"]
    starches   = [i for i in items if i.get("role") == "starch"]
    vegetables = [i for i in items if i.get("role") == "vegetable"]
    combos     = [i for i in items if i.get("role") == "combo"]

    meals = []

    # standalone combos — no assembly
    for c in combos:
        meals.append(build_meal([c], "combo", dining_hall))

    # protein + starch + vegetable
    for p in proteins:
        for s in starches:
            for v in vegetables:
                meals.append(
                    build_meal([p, s, v], "protein_starch_veg", dining_hall)
                )

    # protein + vegetable (low carb option)
    for p in proteins:
        for v in vegetables:
            meals.append(
                build_meal([p, v], "protein_veg", dining_hall)
            )

    # protein + starch fallback when no vegetables available
    if not vegetables:
        for p in proteins:
            for s in starches:
                meals.append(
                    build_meal([p, s], "protein_starch", dining_hall)
                )

    return meals


def is_balanced(meal):
    """
    Basic nutritional sanity check.
    Filters out combinations that are nutritionally invalid
    before they reach the recommender.

    Requirements:
      at least 15% of calories from protein
      fat under 55% of calories
      total calories between 200 and 1200
    """
    cal = meal.get("calories", 0)
    if cal <= 0:
        return False

    protein_pct = (meal["protein"] * 4) / cal
    fat_pct     = (meal["fats"]    * 9) / cal

    return (
        protein_pct >= 0.15 and
        fat_pct     <= 0.55 and
        200 <= cal  <= 1200
    )


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def build_todays_meals(scraped_items, dining_hall):
    """
    Full pipeline from raw scraped items to valid assembled meals.
    Called once per dining hall after each midnight scrape.

    Steps:
      1. detect protein_type from ingredients + name
      2. classify role of each item
      3. assign cluster to each item (A through G)
      4. generate all valid combinations
      5. filter by nutritional balance
      6. return up to 20 meals per hall for db to store

    scraped_items = list of item dicts from nutrislice.py, each with:
      meal_name, ingredients, calories, protein, carbs, fats, dining_hall
    """

    for item in scraped_items:
        # step 1 — detect protein type from ingredients and name
        item["protein_type"] = detect_protein(
            item["meal_name"],
            item.get("ingredients", "")
        )

        # step 2 — classify role
        item["role"] = classify_role(item)

    # exclude items with no clear role
    usable = [i for i in scraped_items if i["role"] != "other"]

    # step 3 — assign clusters (pure rule logic, no db)
    cluster_model.assign_clusters_to_items(usable)

    # step 4 — generate all valid combinations
    all_meals = generate_combinations(usable, dining_hall)

    # step 5 — filter by nutritional balance
    valid = [m for m in all_meals if is_balanced(m)]

    # step 6 — return up to 20 per hall
    return valid[:20]


# ─────────────────────────────────────────────────────────────
# HELPER — USED BY RECOMMENDER
# ─────────────────────────────────────────────────────────────

def parse_components_with_clusters(meal):
    """
    Converts stored comma-separated strings back into the
    format preference_model.get_meal_score() expects.

    meal["components"]         = "Grilled Chicken,Brown Rice,Broccoli"
    meal["component_clusters"] = "A,B,D"

    returns:
      [
        {"name": "Grilled Chicken", "cluster_id": "A"},
        {"name": "Brown Rice",      "cluster_id": "B"},
        {"name": "Broccoli",        "cluster_id": "D"}
      ]

    Called by recommender.score_meal() and recommender.on_feedback()
    before passing to preference_model.
    """
    components = meal["components"].split(",")
    clusters   = meal["component_clusters"].split(",")

    return [
        {"name": name.strip(), "cluster_id": cid.strip()}
        for name, cid in zip(components, clusters)
    ]