"""
seed_data.py
------------
Run this once to set up the database and populate it with demo data.
Also acts as the bridge between the scraper's dining.db and the
recommender's meals.db format.

Usage:
    python seed_data.py              # seed with fake demo data
    python seed_data.py --live       # pull from campusdish scraper
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Database", "meals.db")

os.makedirs("Database", exist_ok=True)


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cluster_preferences (
            cluster_id TEXT PRIMARY KEY,
            likes      INT  DEFAULT 0,
            dislikes   INT  DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS todays_meals (
            meal_name          TEXT,
            components         TEXT,
            component_clusters TEXT,
            calories           REAL,
            protein            REAL,
            carbs              REAL,
            fats               REAL,
            protein_type       TEXT,
            dining_hall        TEXT
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            name           TEXT,
            goal           TEXT,
            daily_calories INT,
            meals_per_day  INT,
            meal_calories  INT,
            goal_protein   REAL,
            goal_carbs     REAL,
            goal_fats      REAL,
            dorm           TEXT
        );
    """)
    conn.commit()


def seed_fake(conn):
    """Populate with realistic fake UVA dining data for demo/testing."""

    conn.execute("DELETE FROM todays_meals")
    conn.execute("DELETE FROM cluster_preferences")
    conn.execute("DELETE FROM user_profile")

    # ── user profile ──────────────────────────────────────────
    conn.execute("""
        INSERT INTO user_profile
        (name, goal, daily_calories, meals_per_day, meal_calories,
         goal_protein, goal_carbs, goal_fats, dorm)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, ("Aaron", "Bulk", 3200, 3, 1067, 80, 120, 30, "Gooch-Dillard"))

    # ── cluster preferences (pre-seeded history) ──────────────
    # reflects a user who loves lean proteins and clean starches
    # dislikes heavy starches
    conn.executemany("""
        INSERT INTO cluster_preferences (cluster_id, likes, dislikes)
        VALUES (?, ?, ?)
        ON CONFLICT(cluster_id) DO UPDATE SET
            likes    = excluded.likes,
            dislikes = excluded.dislikes
    """, [
        ("A", 14, 2),   # Lean Protein    — loves
        ("B", 10, 1),   # Clean Starch    — likes
        ("D",  6, 1),   # Green Vegetable — likes
        ("E",  4, 3),   # Red Meat        — mixed
        ("F",  2, 2),   # Plant Protein   — neutral
        ("C",  1, 7),   # Heavy Starch    — dislikes
        ("G",  0, 0),   # Sauce/Topping   — unrated
    ])

    # ── todays meals (5 per hall) ─────────────────────────────
    meals = [
        # FRESH FOOD COMPANY (Runk equivalent)
        ("Grilled Chicken Breast + Brown Rice + Steamed Broccoli",
         "Grilled Chicken Breast,Brown Rice,Steamed Broccoli", "A,B,D",
         455, 43, 53, 6, "chicken", "Fresh Food Company"),

        ("Baked Salmon + Quinoa + Asparagus",
         "Baked Salmon,Quinoa,Asparagus", "A,B,D",
         520, 44, 48, 16, "fish", "Fresh Food Company"),

        ("Turkey Meatballs + Farro + Roasted Zucchini",
         "Turkey Meatballs,Farro,Roasted Zucchini", "A,B,D",
         490, 38, 52, 12, "turkey", "Fresh Food Company"),

        ("Beef Stir Fry + Brown Rice + Bok Choy",
         "Beef Stir Fry,Brown Rice,Bok Choy", "E,B,D",
         610, 40, 58, 22, "beef", "Fresh Food Company"),

        ("Pasta Bolognese + Garlic Bread + Caesar Salad",
         "Pasta,Garlic Bread,Caesar Salad", "C,C,G",
         820, 28, 94, 32, "beef", "Fresh Food Company"),

        # OBSERVATORY HILL
        ("Herb Roasted Chicken + Sweet Potato + Green Beans",
         "Herb Roasted Chicken,Sweet Potato,Green Beans", "A,B,D",
         470, 40, 50, 10, "chicken", "Observatory Hill"),

        ("Tilapia + Couscous + Roasted Asparagus",
         "Tilapia,Couscous,Roasted Asparagus", "A,B,D",
         440, 38, 46, 10, "fish", "Observatory Hill"),

        ("Pulled Pork + Mashed Potatoes + Roasted Corn",
         "Pulled Pork,Mashed Potatoes,Roasted Corn", "E,C,D",
         680, 36, 72, 24, "pork", "Observatory Hill"),

        ("Egg White Omelette + Roasted Potatoes + Spinach Salad",
         "Egg White Omelette,Roasted Potatoes,Spinach Salad", "A,B,D",
         410, 32, 44, 10, "egg", "Observatory Hill"),

        ("Lentil Curry + Basmati Rice + Roasted Cauliflower",
         "Lentil Curry,Basmati Rice,Roasted Cauliflower", "F,B,D",
         530, 24, 78, 10, "vegetarian", "Observatory Hill"),

        # RUNK
        ("Grilled Shrimp + Quinoa + Kale Salad",
         "Grilled Shrimp,Quinoa,Kale Salad", "A,B,D",
         430, 36, 48, 8, "fish", "Runk"),

        ("Rotisserie Chicken + Brown Rice + Roasted Broccoli",
         "Rotisserie Chicken,Brown Rice,Roasted Broccoli", "A,B,D",
         480, 42, 50, 10, "chicken", "Runk"),

        ("Beef Tacos + Rice + Black Beans",
         "Beef Taco Filling,Rice,Black Beans", "E,B,F",
         620, 38, 66, 20, "beef", "Runk"),

        ("Baked Cod + Sweet Potato + Green Beans",
         "Baked Cod,Sweet Potato,Green Beans", "A,B,D",
         400, 36, 46, 6, "fish", "Runk"),

        ("Tofu Stir Fry + Brown Rice + Edamame",
         "Tofu Stir Fry,Brown Rice,Edamame", "F,B,D",
         420, 26, 54, 14, "tofu", "Runk"),
    ]

    conn.executemany("""
        INSERT INTO todays_meals
        (meal_name, components, component_clusters,
         calories, protein, carbs, fats, protein_type, dining_hall)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, meals)

    conn.commit()
    print("✅ Fake seed data loaded.")
    print("   15 meals across Fresh Food Company, Observatory Hill, Runk")
    print("   User: Aaron | Goal: Bulk | Dorm: Gooch-Dillard")


def seed_from_scraper(conn):
    """
    Pulls live data from campusdish scraper, converts DiningItem
    format to todays_meals format, and populates meals.db.

    Only processes item_type='main' — skips toppings and combos
    since meal_builder handles assembly from individual items.
    """
    try:
        from Database.db import Database
        import inspect
        print(inspect.getfile(Database))
        from utils.meal_builder   import build_todays_meals
        from utils.protein_detector import detect_protein
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure campusdish.py has been run first to populate dining.db")
        return

    dining_db = Database()
    main_items = dining_db.get_main_meals()

    if not main_items:
        print("❌ No items in dining.db — run campusdish.py first")
        return

    print(f"   Found {len(main_items)} main items in dining.db")

    # group by dining hall
    by_hall = {}
    for item in main_items:
        hall = item.dining_hall
        if hall not in by_hall:
            by_hall[hall] = []
        by_hall[hall].append({
            "meal_name":    item.name,
            "ingredients":  item.ingredients or "",
            "calories":     item.calories or 0,
            "protein":      item.protein_g or 0,
            "carbs":        item.total_carbs_g or 0,
            "fats":         item.total_fat_g or 0,
            "dining_hall":  item.dining_hall,
        })

    conn.execute("DELETE FROM todays_meals")
    total = 0

    for hall, items in by_hall.items():
        # run through meal_builder pipeline
        assembled = build_todays_meals(items, hall)
        for meal in assembled:
            conn.execute("""
                INSERT INTO todays_meals
                (meal_name, components, component_clusters,
                 calories, protein, carbs, fats, protein_type, dining_hall)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                meal["meal_name"],
                meal["components"],
                meal["component_clusters"],
                meal["calories"],
                meal["protein"],
                meal["carbs"],
                meal["fats"],
                meal.get("protein_type", "unknown"),
                meal["dining_hall"],
            ))
            total += 1

    conn.commit()
    print(f"✅ Live data loaded — {total} assembled meals saved.")


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)

    if "--live" in sys.argv:
        print("Pulling live data from scraper...")
        seed_from_scraper(conn)
    else:
        print("Loading fake demo data...")
        seed_fake(conn)

    conn.close()
    print()
    print("Run the app:")
    print("  streamlit run app/main.py")