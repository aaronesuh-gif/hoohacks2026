import requests
import urllib3
import os
import sys
from datetime import date

# Suppress SSL warnings since we're using verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Add the project root to the path so we can import from Database/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Database.db import Database

# ---------------------------------------------------------------------------
# API Configuration
# ---------------------------------------------------------------------------

API_URL = "https://api.elevate-dxp.com/api/mesh/c087f756-cc72-4649-a36f-3a41b700c519/graphql"

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "accept": "application/graphql-response+json,application/json;q=0.9",
    "store": "ch_virginia_en",
    "magento-store-code": "ch_virginia",
    "magento-store-view-code": "ch_virginia_en",
    "magento-website-code": "ch_virginia",
    "magento-customer-group": "b6589fc6ab0dc82cf12099d1c2d40ab994e8410c",
    "x-api-key": "ElevateAPIProd",
    "aem-elevate-clientpath": "ch/virginia/en",
    "origin": "https://virginia.mydininghub.com",
    "referer": "https://virginia.mydininghub.com/",
}

# ---------------------------------------------------------------------------
# Dining Hall Configuration
# ---------------------------------------------------------------------------

DINING_HALLS = {
    "fresh-food-company": {
        "name": "Fresh Food Company",
        "meal_periods": {"Breakfast": 10, "Lunch": 25, "Dinner": 16},
        "stations": {
            218023: "Entree",
            218029: "Grill",
            218041: "Halal Street Eats",
            218044: "Pizza",
            218047: "Pasta Bar",
            218050: "Deli",
            218026: "Salad Bar",
            218035: "Simply Vegan",
            218038: "True Balance",
            218032: "Bake Shop",
        }
    },
    "observatory-hill-dining-room": {
        "name": "Observatory Hill",
        "meal_periods": {"Breakfast": 10, "Lunch": 25, "Dinner": 16},
        "stations": {
            227481: "Omelets at Green Fork",
            227493: "Hearth",
            227499: "Meze",
            227484: "Under the Hood",
            227487: "Trattoria Pizza",
            227505: "Savory Stacks",
            227490: "Hoo's Your Deli",
            227478: "Greens and Grains",
            227496: "Green Fork",
            227475: "True Balance",
            227502: "Patisserie",
        }
    },
    "runk": {
        "name": "Runk",
        "meal_periods": {"Brunch": 13, "Dinner": 16},
        "stations": {
            218062: "Chef's Table",
            218053: "1819 Grill",
            218056: "Deli Works",
            218059: "Cilantro & Lime",
            218065: "Crisp",
            218068: "Halal Oven",
            218071: "True Balance",
            218074: "Veganomics",
            218077: "Cafe Parfait",
            218083: "Bakery",
        }
    },
}

# ---------------------------------------------------------------------------
# Hardcoded Base Meals
#
# These are the only stations where combo logic applies.
# The API only returns toppings for these stations — no base meal.
# We hardcode the base and combine it with high-cal ingredients (>=50 cal).
# ---------------------------------------------------------------------------

HARDCODED_BASE_MEALS = {
    "Omelets at Green Fork": {
        "name": "Omelet",
        "serving_size": "1 omelet",
        "calories": 140,
        "protein_g": 12.0,
        "total_fat_g": 10.0,
        "saturated_fat_g": 3.0,
        "trans_fat_g": 0.0,
        "cholesterol_mg": 370.0,
        "sodium_mg": 140.0,
        "total_carbs_g": 1.0,
        "dietary_fiber_g": 0.0,
        "total_sugars_g": 0.0,
        "is_vegan": False,
        "is_vegetarian": True,
        "is_gluten_free": True,
        "is_halal": False,
        "is_kosher": False,
        "contains_nuts": False,
        "contains_dairy": False,
        "contains_eggs": True,
        "contains_soy": False,
        "contains_shellfish": False,
    },
    "Grill": {
        "name": "Hamburger",
        "serving_size": "1 patty",
        "calories": 250,
        "protein_g": 20.0,
        "total_fat_g": 18.0,
        "saturated_fat_g": 7.0,
        "trans_fat_g": 0.5,
        "cholesterol_mg": 80.0,
        "sodium_mg": 350.0,
        "total_carbs_g": 0.0,
        "dietary_fiber_g": 0.0,
        "total_sugars_g": 0.0,
        "is_vegan": False,
        "is_vegetarian": False,
        "is_gluten_free": True,
        "is_halal": False,
        "is_kosher": False,
        "contains_nuts": False,
        "contains_dairy": False,
        "contains_eggs": False,
        "contains_soy": False,
        "contains_shellfish": False,
    },
    "Salad Bar": {
        "name": "House Salad",
        "serving_size": "1 bowl",
        "calories": 15,
        "protein_g": 1.0,
        "total_fat_g": 0.0,
        "saturated_fat_g": 0.0,
        "trans_fat_g": 0.0,
        "cholesterol_mg": 0.0,
        "sodium_mg": 10.0,
        "total_carbs_g": 2.0,
        "dietary_fiber_g": 1.0,
        "total_sugars_g": 0.0,
        "is_vegan": True,
        "is_vegetarian": True,
        "is_gluten_free": True,
        "is_halal": True,
        "is_kosher": False,
        "contains_nuts": False,
        "contains_dairy": False,
        "contains_eggs": False,
        "contains_soy": False,
        "contains_shellfish": False,
    },
}

# At hardcoded-base stations, ingredient_item=yes items at or above this
# calorie count get comboed with the base meal.
# Below this they are true toppings — stored as-is, never comboed.
TOPPING_CAL_THRESHOLD = 50

# Items to skip entirely
SKIP_ITEMS = {
    "GRAVY, SAUSAGE, MIX wr",
}

# ---------------------------------------------------------------------------
# Lookup Tables
# ---------------------------------------------------------------------------

ALLERGEN_MAP = {
    "39": "Eggs",
    "42": "Fish",
    "45": "Milk",
    "48": "Peanuts",
    "51": "Sesame",
    "54": "Shellfish",
    "57": "Soy",
    "60": "Tree Nuts",
    "63": "Wheat",
}

ATTRIBUTE_MAP = {
    "96": "Vegan",
    "99": "Vegetarian",
    "609": "Coolfood Meal",
    "90": "Plant Forward",
    "78": "Made Without Gluten",
    "75": "Eat Well",
    "84": "Made with Whole Grains",
    "133": "Halal",
    "72": "Colors",
    "606": "Carbs",
    "612": "Protein",
}

# ---------------------------------------------------------------------------
# GraphQL Query
# ---------------------------------------------------------------------------

QUERY = """
query getLocationRecipes($campusUrlKey: String!, $locationUrlKey: String!, $date: String!, $mealPeriod: Int, $viewType: Commerce_MenuViewType!) {
  getLocationRecipes(campusUrlKey: $campusUrlKey, locationUrlKey: $locationUrlKey, date: $date, mealPeriod: $mealPeriod, viewType: $viewType) {
    locationRecipesMap {
      dateSkuMap {
        date
        stations {
          id
          skus { simple }
        }
      }
    }
    products {
      items {
        name
        sku
        attributes { name value }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def get_attr(attributes, name):
    for attr in attributes:
        if attr["name"] == name:
            return attr["value"]
    return None

def decode_list(id_list, mapping):
    if not id_list:
        return []
    if isinstance(id_list, list):
        return [mapping.get(str(i), str(i)) for i in id_list]
    return []

def safe_float(val):
    try:
        return float(val) if val else None
    except:
        return None

def safe_int(val):
    try:
        return int(float(val)) if val else None
    except:
        return None

# ---------------------------------------------------------------------------
# Combo Generation (only used for hardcoded-base stations)
# ---------------------------------------------------------------------------

def combine_macros(base, other):
    def add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)
    return {
        "calories":        add(base.get("calories"),        other.get("calories")),
        "protein_g":       add(base.get("protein_g"),       other.get("protein_g")),
        "total_fat_g":     add(base.get("total_fat_g"),     other.get("total_fat_g")),
        "saturated_fat_g": add(base.get("saturated_fat_g"), other.get("saturated_fat_g")),
        "trans_fat_g":     add(base.get("trans_fat_g"),     other.get("trans_fat_g")),
        "cholesterol_mg":  add(base.get("cholesterol_mg"),  other.get("cholesterol_mg")),
        "sodium_mg":       add(base.get("sodium_mg"),       other.get("sodium_mg")),
        "total_carbs_g":   add(base.get("total_carbs_g"),   other.get("total_carbs_g")),
        "dietary_fiber_g": add(base.get("dietary_fiber_g"), other.get("dietary_fiber_g")),
        "total_sugars_g":  add(base.get("total_sugars_g"),  other.get("total_sugars_g")),
    }

def generate_combos(base_db, partners_db, shared_fields, has_low_cal_toppings):
    combos = []
    for partner in partners_db:
        combined = combine_macros(base_db, partner)
        combo = {
            **shared_fields,
            "name":            f"{base_db['name']} + {partner['name']}",
            "item_type":       "combo",
            "base_meal_name":  base_db["name"],
            "topping_name":    partner["name"],
            "serving_size":    None,
            **combined,
            "is_vegan":        base_db.get("is_vegan", False)       and partner.get("is_vegan", False),
            "is_vegetarian":   base_db.get("is_vegetarian", False)  and partner.get("is_vegetarian", False),
            "is_gluten_free":  base_db.get("is_gluten_free", False) and partner.get("is_gluten_free", False),
            "is_halal":        base_db.get("is_halal", False)       and partner.get("is_halal", False),
            "is_kosher":       False,
            "contains_nuts":      base_db.get("contains_nuts", False)      or partner.get("contains_nuts", False),
            "contains_dairy":     base_db.get("contains_dairy", False)     or partner.get("contains_dairy", False),
            "contains_eggs":      base_db.get("contains_eggs", False)      or partner.get("contains_eggs", False),
            "contains_soy":       base_db.get("contains_soy", False)       or partner.get("contains_soy", False),
            "contains_shellfish": base_db.get("contains_shellfish", False) or partner.get("contains_shellfish", False),
            "has_low_cal_toppings": has_low_cal_toppings,
        }
        combos.append(combo)
    return combos

# ---------------------------------------------------------------------------
# Convert scraped item to database format
# ---------------------------------------------------------------------------

def item_to_db_format(item, shared_fields, item_type="main", has_low_cal_toppings=False):
    tags      = item.get("dietary_tags", [])
    allergens = item.get("allergens", [])
    return {
        **shared_fields,
        "name":                  item["name"],
        "item_type":             item_type,
        "base_meal_name":        None,
        "topping_name":          None,
        "has_low_cal_toppings":  has_low_cal_toppings,
        "serving_size":          item.get("serving_size"),
        "calories":              safe_int(item.get("calories")),
        "protein_g":             safe_float(item.get("protein")),
        "total_fat_g":           safe_float(item.get("total_fat")),
        "saturated_fat_g":       safe_float(item.get("saturated_fat")),
        "trans_fat_g":           safe_float(item.get("trans_fat")),
        "cholesterol_mg":        safe_float(item.get("cholesterol")),
        "sodium_mg":             safe_float(item.get("sodium")),
        "total_carbs_g":         safe_float(item.get("total_carbohydrates")),
        "dietary_fiber_g":       safe_float(item.get("dietary_fiber")),
        "total_sugars_g":        safe_float(item.get("sugars")),
        "is_vegan":              "Vegan" in tags,
        "is_vegetarian":         "Vegetarian" in tags,
        "is_gluten_free":        "Made Without Gluten" in tags,
        "is_halal":              "Halal" in tags,
        "is_kosher":             False,
        "contains_nuts":         "Tree Nuts" in allergens,
        "contains_dairy":        "Milk" in allergens,
        "contains_eggs":         "Eggs" in allergens,
        "contains_soy":          "Soy" in allergens,
        "contains_shellfish":    "Shellfish" in allergens,
    }

def hardcoded_base_to_db_format(base, shared_fields, has_low_cal_toppings=False):
    return {
        **shared_fields,
        **base,
        "item_type":            "main",
        "base_meal_name":       None,
        "topping_name":         None,
        "has_low_cal_toppings": has_low_cal_toppings,
    }

# ---------------------------------------------------------------------------
# Process a single station
#
# RULES:
#
# Hardcoded-base stations (Omelets at Green Fork, Grill, Salad Bar):
#   - ingredient_item=yes, cal >= 50  -> stored as main + comboed with hardcoded base
#   - ingredient_item=yes, cal < 50   -> stored as topping, no combo
#   - ingredient_item=no              -> stored as main, no combo
#   - hardcoded base always inserted as main
#
# All other stations:
#   - ingredient_item=no              -> stored as main
#   - ingredient_item=yes (any cal)   -> stored as topping, no combo, no special logic
# ---------------------------------------------------------------------------

def process_station(station_name, items, dining_hall, meal_period):
    db_rows = []

    shared_fields = {
        "dining_hall": dining_hall,
        "meal_period": meal_period,
        "category":    station_name,
    }

    if station_name in HARDCODED_BASE_MEALS:
        # Split into: true toppings (<50 cal), high-cal ingredients (>=50 cal), regular mains
        true_toppings = []
        high_cal      = []
        mains         = []

        for item in items:
            if item.get("ingredient_item") == "yes":
                cal = safe_int(item.get("calories"))
                if cal is not None and cal >= TOPPING_CAL_THRESHOLD:
                    high_cal.append(item)
                else:
                    true_toppings.append(item)
            else:
                mains.append(item)

        # Salad Bar only gets a base if there's something to go with it
        if station_name == "Salad Bar" and not true_toppings and not high_cal and not mains:
            return []

        has_low_cal_toppings = len(true_toppings) > 0

        # Insert hardcoded base meal
        base_db = hardcoded_base_to_db_format(
            HARDCODED_BASE_MEALS[station_name], shared_fields,
            has_low_cal_toppings=has_low_cal_toppings
        )
        db_rows.append(base_db)

        # Regular mains (ingredient_item=no) -> stored as mains
        for item in mains:
            db_rows.append(item_to_db_format(
                item, shared_fields, item_type="main",
                has_low_cal_toppings=has_low_cal_toppings
            ))

        # True toppings (ingredient_item=yes, cal < 50) -> stored as toppings, no combo
        for item in true_toppings:
            db_rows.append(item_to_db_format(
                item, shared_fields, item_type="topping"
            ))

        # High-cal ingredients (ingredient_item=yes, cal >= 50) -> stored as toppings
        # AND generate a combo with the hardcoded base (e.g. Hamburger + Bacon)
        high_cal_dbs = []
        for item in high_cal:
            item_db = item_to_db_format(
                item, shared_fields, item_type="topping"
            )
            db_rows.append(item_db)
            high_cal_dbs.append(item_db)

        if high_cal_dbs:
            combos = generate_combos(base_db, high_cal_dbs, shared_fields, has_low_cal_toppings)
            db_rows.extend(combos)

    else:
        # Standard station — no combo logic at all
        # ingredient_item=yes -> topping regardless of calories
        # ingredient_item=no  -> main
        for item in items:
            if item.get("ingredient_item") == "yes":
                db_rows.append(item_to_db_format(
                    item, shared_fields, item_type="topping"
                ))
            else:
                db_rows.append(item_to_db_format(
                    item, shared_fields, item_type="main"
                ))

    return db_rows

# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

def scrape_menu(location_slug, meal_period_name, meal_period_id):
    hall = DINING_HALLS[location_slug]
    try:
        response = requests.get(API_URL, headers=HEADERS, params={
            "query": QUERY,
            "operationName": "getLocationRecipes",
            "variables": '{"campusUrlKey":"campus","locationUrlKey":"' + location_slug + '","date":"' + str(date.today()) + '","mealPeriod":' + str(meal_period_id) + ',"viewType":"DAILY"}',
            "extensions": '{"clientLibrary":{"name":"@apollo/client","version":"4.1.6"}}'
        }, verify=False)

        data   = response.json()
        result = data["data"]["getLocationRecipes"]

        if not result or not result.get("locationRecipesMap") or not result["locationRecipesMap"].get("dateSkuMap"):
            print(f"  No menu available for this period")
            return {}

    except Exception as e:
        print(f"  Error scraping {location_slug} {meal_period_name}: {e}")
        return {}

    # Build SKU -> station name map
    sku_to_station = {}
    for day in result["locationRecipesMap"]["dateSkuMap"]:
        for station in day["stations"]:
            station_name = hall["stations"].get(station["id"], f"Station {station['id']}")
            for sku in station["skus"]["simple"]:
                sku_to_station[sku] = station_name

    # Group items by station
    stations = {}
    for item in result["products"]["items"]:
        if item["name"] in SKIP_ITEMS:
            continue

        attrs          = item["attributes"]
        station_name   = sku_to_station.get(item["sku"], "Unknown")
        raw_allergens  = get_attr(attrs, "allergens_intolerances")
        raw_attributes = get_attr(attrs, "recipe_attributes")

        parsed_item = {
            "name":                item["name"],
            "ingredient_item":     get_attr(attrs, "ingredient_item"),
            "serving_size":        get_attr(attrs, "serving_combined"),
            "calories":            get_attr(attrs, "calories"),
            "protein":             get_attr(attrs, "protein"),
            "total_fat":           get_attr(attrs, "total_fat"),
            "saturated_fat":       get_attr(attrs, "saturated_fat"),
            "trans_fat":           get_attr(attrs, "trans_fat"),
            "cholesterol":         get_attr(attrs, "cholesterol"),
            "sodium":              get_attr(attrs, "sodium"),
            "total_carbohydrates": get_attr(attrs, "total_carbohydrates"),
            "dietary_fiber":       get_attr(attrs, "dietary_fiber"),
            "sugars":              get_attr(attrs, "sugars"),
            "ingredients":         get_attr(attrs, "recipe_ingredients"),
            "allergens":           decode_list(raw_allergens, ALLERGEN_MAP),
            "dietary_tags":        decode_list(raw_attributes, ATTRIBUTE_MAP),
        }

        if station_name not in stations:
            stations[station_name] = []
        stations[station_name].append(parsed_item)

    return stations

def scrape_all():
    all_db_rows = []

    for slug, hall in DINING_HALLS.items():
        for period_name, period_id in hall["meal_periods"].items():
            print(f"Scraping {hall['name']} - {period_name}...")

            stations = scrape_menu(slug, period_name, period_id)

            if not stations:
                print(f"  Found 0 items")
                continue

            period_rows = []
            for station_name, items in stations.items():
                rows = process_station(station_name, items, hall["name"], period_name)
                period_rows.extend(rows)

            print(f"  Found {len(period_rows)} rows (including combos)")
            all_db_rows.extend(period_rows)

    return all_db_rows

# ---------------------------------------------------------------------------
# Save to Database
# ---------------------------------------------------------------------------

def save_to_database(rows):
    db = Database()
    db.clear_all()
    count = db.add_items(rows)
    print(f"\nSaved {count} rows to database")

# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rows = scrape_all()
    print(f"\nTotal rows generated: {len(rows)}")
    save_to_database(rows)