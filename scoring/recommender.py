import sqlite3
from models.preference_model import PreferenceModel
from meal_builder   import parse_components_with_clusters

preference_model = PreferenceModel()
DB_PATH          = "database/meals.db"


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────

def get_todays_meals(dining_hall=None):
    """
    Fetches todays assembled meals from SQLite.
    Optionally filtered by dining hall.
    """
    conn = sqlite3.connect(DB_PATH)
    if dining_hall:
        rows = conn.execute("""
            SELECT meal_name, components, component_clusters,
                   calories, protein, carbs, fats,
                   protein_type, dining_hall
            FROM todays_meals WHERE dining_hall = ?
        """, (dining_hall,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT meal_name, components, component_clusters,
                   calories, protein, carbs, fats,
                   protein_type, dining_hall
            FROM todays_meals
        """).fetchall()
    conn.close()

    keys = [
        "meal_name", "components", "component_clusters",
        "calories", "protein", "carbs", "fats",
        "protein_type", "dining_hall"
    ]
    return [dict(zip(keys, row)) for row in rows]


# ─────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────

def score_meal(meal):
    """
    Scores a meal purely on cluster preference history.

    Calls parse_components_with_clusters() to convert the stored
    comma separated strings into the format preference_model needs:
      [{"name": "Grilled Chicken", "cluster_id": "A"}, ...]

    Passes to preference_model.get_meal_score() which averages
    Thompson Sampling draws across each component's cluster.

    Returns a scored meal dict for the UI.
    """
    components_with_clusters = parse_components_with_clusters(meal)

    return {
        "meal":       meal,
        "score":      round(
                          preference_model.get_meal_score(
                              components_with_clusters), 4),
        "confidence": preference_model.get_confidence(
                          components_with_clusters)
    }


# ─────────────────────────────────────────────────────────────
# RECOMMENDATIONS
# ─────────────────────────────────────────────────────────────

def get_recommendations():
    """
    Returns top 5 meals per dining hall ranked by cluster
    preference score.

    Returns:
      {
        "Runk":    [scored_meal_1, scored_meal_2, ...],
        "O'Hill":  [scored_meal_1, scored_meal_2, ...],
        "Newcomb": [scored_meal_1, scored_meal_2, ...]
      }

    Each scored_meal contains:
      meal        → full meal dict (name, macros, dining hall, components)
      score       → preference score 0-1 from cluster history
      confidence  → "love" / "like" / "neutral" / "dislike" / "unknown"
    """
    ALL_HALLS = ["Runk", "O'Hill", "Newcomb"]
    results   = {}

    for hall in ALL_HALLS:
        meals = get_todays_meals(dining_hall=hall)
        if not meals:
            results[hall] = []
            continue

        scored = [score_meal(meal) for meal in meals]
        scored.sort(key=lambda x: x["score"], reverse=True)
        results[hall] = scored[:5]

    return results


# ─────────────────────────────────────────────────────────────
# FEEDBACK
# ─────────────────────────────────────────────────────────────

def on_feedback(meal, liked):
    """
    Called by the UI on every 👍 or 👎 press.

    Parses component clusters from the meal dict and passes
    to preference_model.update() which:
      👍 → increments alpha on each unique cluster touched
      👎 → increments beta on each unique cluster touched

    Saves to cluster_preferences in SQLite immediately.
    This is the only write that happens on feedback —
    no meal log, no individual food tracking.
    """
    components_with_clusters = parse_components_with_clusters(meal)
    preference_model.update(components_with_clusters, liked)