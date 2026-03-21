import numpy as np
import sqlite3
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler


class SimilarityEngine:
    """
    Compares new meals against previously liked meals
    using cosine similarity on feature vectors.

    Why this matters:
      The preference model only scores meals it has
      explicit feedback on. The similarity engine fills
      the gap for brand new meals that have never been
      rated — if a new meal closely resembles meals
      you have liked before, it scores high even with
      zero direct history.

    Works alongside preference model:
      preference model  → explicit signal (👍👎 history)
      similarity engine → implicit signal (looks like liked meals)

    Only liked meals are stored in the comparison bank.
    Disliked meals are intentionally excluded — we want
    to surface meals similar to what you enjoy,
    not avoid meals similar to what you dislike
    (that would over-restrict recommendations).
    """

    ALL_PROTEINS = [
        "chicken", "beef", "pork", "fish",
        "turkey", "tofu", "egg", "lamb", "vegetarian"
    ]

    def __init__(self, db_path="database/meals.db"):
        self.db_path     = db_path
        self.liked_meals = []    # list of feature vectors for liked meals
        self.scaler      = StandardScaler()
        self.scaler_fitted = False
        self.load_liked_meals()

    # ─────────────────────────────────────────────────────
    # FEATURE BUILDING
    # ─────────────────────────────────────────────────────

    def build_feature_vector(self, meal):
        """
        Identical structure to ClusterModel.build_feature_vector.
        Consistency is critical — similarity is only meaningful
        if both meals being compared are represented
        the same way.

        13 features total:
          [calories, protein, carbs, fats,
           has_chicken, has_beef, has_pork, has_fish,
           has_turkey, has_tofu, has_egg, has_lamb,
           has_vegetarian]
        """
        macro_features = [
            meal["calories"],
            meal["protein"],
            meal["carbs"],
            meal["fats"]
        ]
        protein_flags = [
            1 if p == meal.get("protein_type", "unknown") else 0
            for p in self.ALL_PROTEINS
        ]
        return np.array(macro_features + protein_flags, dtype=float)

    # ─────────────────────────────────────────────────────
    # STARTUP — LOAD LIKED MEAL HISTORY
    # ─────────────────────────────────────────────────────

    def load_liked_meals(self):
        """
        Loads feature vectors of all previously liked meals
        from meal_log table on startup.

        This rebuilds the comparison bank from scratch
        each session using the persistent meal_log.
        Without this the engine starts cold every restart.

        Only loads liked=1 rows — disliked meals
        are deliberately excluded from the bank.
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT calories, protein, carbs, fats, protein_type
            FROM meal_log
            WHERE liked = 1
        """).fetchall()
        conn.close()

        for row in rows:
            cal, pro, carb, fat, protein_type = row
            meal = {
                "calories":     cal,
                "protein":      pro,
                "carbs":        carb,
                "fats":         fat,
                "protein_type": protein_type
            }
            self.liked_meals.append(self.build_feature_vector(meal))

        # fit scaler if we have history
        if self.liked_meals:
            matrix = np.array(self.liked_meals)
            self.scaler.fit(matrix)
            self.scaler_fitted = True

    # ─────────────────────────────────────────────────────
    # SCORING — CORE LOGIC
    # ─────────────────────────────────────────────────────

    def get_similarity_score(self, meal):
        """
        Compares this meal against every previously liked meal
        using cosine similarity.

        Cosine similarity measures the angle between two vectors:
          1.0 = identical direction  (same macro + protein profile)
          0.0 = completely different (nothing in common)

        We take the MAXIMUM similarity found across all liked meals
        rather than the average — if this meal closely matches
        ANY meal you have liked, that is enough to recommend it.
        Using average would dilute strong matches with weak ones.

        Returns 0.5 neutral if no liked history exists yet.
        This keeps the similarity signal from penalizing
        new users who have no history.
        """
        if not self.liked_meals:
            return 0.5   # no history yet, neutral score

        meal_vector = self.build_feature_vector(meal).reshape(1, -1)

        # scale using the fitted scaler
        if self.scaler_fitted:
            try:
                meal_vector_scaled = self.scaler.transform(meal_vector)
                liked_matrix_scaled = self.scaler.transform(
                    np.array(self.liked_meals)
                )
            except Exception:
                # fallback to unscaled if scaler fails
                meal_vector_scaled  = meal_vector
                liked_matrix_scaled = np.array(self.liked_meals)
        else:
            meal_vector_scaled  = meal_vector
            liked_matrix_scaled = np.array(self.liked_meals)

        # cosine similarity between this meal and all liked meals
        # returns array of shape (1, n_liked_meals)
        similarities = cosine_similarity(
            meal_vector_scaled,
            liked_matrix_scaled
        )[0]

        # take the highest similarity — best match to any liked meal
        return float(np.max(similarities))

    def get_top_similar_meals(self, meal, meals_list, n=3):
        """
        Finds the N most similar meals to a given meal
        from a list of available meals.

        Used to show "Similar meals you might like"
        section on the meal card in the UI.

        meal       = the reference meal
        meals_list = list of todays available meals to compare against
        n          = how many similar meals to return
        """
        if not meals_list:
            return []

        target_vector = self.build_feature_vector(meal).reshape(1, -1)

        scored = []
        for candidate in meals_list:
            # dont compare meal to itself
            if candidate["meal_name"] == meal["meal_name"]:
                continue

            candidate_vector = self.build_feature_vector(candidate).reshape(1, -1)
            similarity = float(
                cosine_similarity(target_vector, candidate_vector)[0][0]
            )
            scored.append((candidate, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [meal for meal, score in scored[:n]]

    # ─────────────────────────────────────────────────────
    # LEARNING — UPDATE FROM FEEDBACK
    # ─────────────────────────────────────────────────────

    def update(self, meal, liked: bool):
        """
        Called on every 👍 press.
        Adds the meal's feature vector to the liked bank
        so future similarity comparisons include it.

        👎 presses are ignored intentionally —
        we only track positive signal here.
        The preference model handles dislike tracking.

        Also refits the scaler when new data is added
        so scaling stays accurate as history grows.
        """
        if not liked:
            return   # only track liked meals

        new_vector = self.build_feature_vector(meal)
        self.liked_meals.append(new_vector)

        # refit scaler with updated liked bank
        matrix = np.array(self.liked_meals)
        self.scaler.fit(matrix)
        self.scaler_fitted = True

    # ─────────────────────────────────────────────────────
    # STATS — FOR DEBUGGING
    # ─────────────────────────────────────────────────────

    def get_liked_count(self):
        """
        Returns how many liked meals are in the comparison bank.
        Used in stats page to show how much data the model has.
        """
        return len(self.liked_meals)