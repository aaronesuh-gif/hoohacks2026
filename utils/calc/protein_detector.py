"""
Detects the primary protein type of a scraped food item
by searching its ingredients string and name for keywords.

Called by meal_builder on every scraped item before cluster
assignment. The protein_type it returns feeds directly into
cluster_model.assign_cluster() which uses it to decide
between clusters A (lean protein), E (red meat), and F (plant protein).

Without this, all three protein clusters fire as "unknown"
and every protein item falls through to the macro-only rules
or defaults to G.
"""

PROTEIN_KEYWORDS = {
    "chicken":    ["chicken", "poultry", "chkn", "rotisserie"],
    "fish":       ["salmon", "tilapia", "tuna", "cod", "fish",
                   "shrimp", "seafood", "mahi", "trout", "bass",
                   "halibut", "crab", "lobster", "scallop"],
    "turkey":     ["turkey"],
    "egg":        ["egg", "eggs", "omelette", "frittata"],
    "beef":       ["beef", "ground beef", "steak", "brisket",
                   "burger patty", "meatball", "bolognese"],
    "pork":       ["pork", "ham", "bacon", "sausage",
                   "carnitas", "pulled pork"],
    "lamb":       ["lamb", "gyro", "shawarma"],
    "tofu":       ["tofu", "tempeh"],
    "vegetarian": ["lentil", "chickpea", "black bean", "falafel",
                   "beyond meat", "impossible", "plant based",
                   "plant-based", "veggie burger"]
}


def detect_protein(item_name, ingredients=""):
    """
    Searches ingredients string first then item name for
    protein keywords. Ingredients are more reliable because
    dining hall dish names are often vague.

    Returns one of:
      "chicken" "fish" "turkey" "egg"
      "beef" "pork" "lamb"
      "tofu" "vegetarian"
      "unknown"  ← if nothing found, cluster_model uses macro rules

    item_name   = "Herb Roasted Poultry"
    ingredients = "Chicken breast, rosemary, olive oil, garlic, salt"
    → returns "chicken"
    """
    search_text = f"{ingredients} {item_name}".lower()

    for protein, keywords in PROTEIN_KEYWORDS.items():
        if any(keyword in search_text for keyword in keywords):
            return protein

    return "unknown"