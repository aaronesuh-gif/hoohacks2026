import sqlite3
import numpy as np
from scipy.stats import beta


class PreferenceModel:
    """
    Tracks meal preferences using Thompson Sampling.
    
    Maintains two levels of preference signal:
      component level  → tracks individual food items
                         "you liked grilled chicken 8 times"
      cluster level    → tracks meal types
                         "you liked high protein low carb meals 14 times"
    
    When scoring a new meal:
      seen before  → blends exact component history with cluster history
      never seen   → relies entirely on cluster history
    
    This means even brand new menu items get intelligent scores
    based on what type of meal they are, not just their exact name.
    """

    def __init__(self, db_path="database/meals.db"):
        self.db_path       = db_path
        self.meal_stats    = {}   # { meal_name:  { alpha: int, beta: int } }
        self.cluster_stats = {}   # { cluster_id: { alpha: int, beta: int } }
        self.load_from_db()

    # ─────────────────────────────────────────────────────
    # STARTUP
    # ─────────────────────────────────────────────────────

    def load_from_db(self):
        """
        Loads all saved preference counts into memory on startup.
        Called automatically in __init__.

        This is how the model remembers preferences between
        app sessions — without this every restart forgets everything.
        SQLite is the persistent store, self.meal_stats and
        self.cluster_stats are the in-memory working copies.
        """
        conn = sqlite3.connect(self.db_path)

        # load individual component preferences
        rows = conn.execute("""
            SELECT meal_name, likes, dislikes
            FROM preferences
        """).fetchall()

        for meal_name, likes, dislikes in rows:
            self.meal_stats[meal_name] = {
                "alpha": likes    + 1,   # +1 so distribution is never undefined
                "beta":  dislikes + 1    # beta(0,0) is undefined in scipy
            }

        # load cluster level preferences
        rows = conn.execute("""
            SELECT cluster_id, likes, dislikes
            FROM cluster_preferences
        """).fetchall()

        for cluster_id, likes, dislikes in rows:
            self.cluster_stats[cluster_id] = {
                "alpha": likes    + 1,
                "beta":  dislikes + 1
            }

        conn.close()

    # ─────────────────────────────────────────────────────
    # SAVING
    # ─────────────────────────────────────────────────────

    def save_component_to_db(self, meal_name):
        """
        Persists updated like/dislike counts for a single
        component back to SQLite after every feedback event.

        Uses INSERT OR REPLACE so it handles both
        new components and existing ones without
        needing to check first.
        """
        stats = self.meal_stats[meal_name]
        conn  = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO preferences (meal_name, likes, dislikes, last_updated)
            VALUES (?, ?, ?, DATE('now'))
            ON CONFLICT(meal_name) DO UPDATE SET
                likes        = excluded.likes,
                dislikes     = excluded.dislikes,
                last_updated = excluded.last_updated
        """, (
            meal_name,
            stats["alpha"] - 1,   # subtract offset before saving
            stats["beta"]  - 1
        ))
        conn.commit()
        conn.close()

    def save_cluster_to_db(self, cluster_id):
        """
        Persists updated cluster counts back to SQLite.
        Called alongside save_component_to_db on every
        feedback event so both levels stay in sync.
        """
        stats = self.cluster_stats[cluster_id]
        conn  = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO cluster_preferences (cluster_id, likes, dislikes)
            VALUES (?, ?, ?)
            ON CONFLICT(cluster_id) DO UPDATE SET
                likes    = excluded.likes,
                dislikes = excluded.dislikes
        """, (
            cluster_id,
            stats["alpha"] - 1,
            stats["beta"]  - 1
        ))
        conn.commit()
        conn.close()

    # ─────────────────────────────────────────────────────
    # SCORING — CORE ML LOGIC
    # ─────────────────────────────────────────────────────

    def get_component_score(self, component_name, cluster_id):
        """
        Scores a single food component using Thompson Sampling.

        Thompson Sampling works by drawing a random sample from
        a beta distribution shaped by like/dislike counts:

          beta(alpha, beta) where:
            alpha = likes + 1
            beta  = dislikes + 1

          Many likes, few dislikes   → distribution skewed toward 1.0
                                       → almost always draws high
          Few likes, many dislikes   → distribution skewed toward 0.0
                                       → almost always draws low
          Equal or no history        → flat distribution
                                       → random draw between 0 and 1
                                       → this is the exploration behavior

        The random draw is intentional — it means meals with
        uncertain history occasionally score high and get
        recommended, letting the model gather more data.
        This is the explore/exploit tradeoff.

        Two signals blended:
          exact component history  → specific to this food item
          cluster history          → general meal type preference
        """

        # signal 1 — exact component history
        if component_name in self.meal_stats:
            s           = self.meal_stats[component_name]
            exact_score = float(beta.rvs(s["alpha"], s["beta"]))
            has_history = True
        else:
            exact_score = None
            has_history = False

        # signal 2 — cluster level history
        # initializes neutral if this cluster has never been rated
        if cluster_id not in self.cluster_stats:
            self.cluster_stats[cluster_id] = {"alpha": 1, "beta": 1}

        c             = self.cluster_stats[cluster_id]
        cluster_score = float(beta.rvs(c["alpha"], c["beta"]))

        # blend signals based on available history
        if has_history:
            # exact history available — weight it more heavily
            # cluster still contributes to smooth out noise
            score = (exact_score * 0.6) + (cluster_score * 0.4)
        else:
            # never seen this exact component before
            # cluster signal is the only thing we have
            score = cluster_score

        return float(np.clip(score, 0.0, 1.0))

    def get_meal_score(self, components, cluster_id):
        """
        Scores a full assembled meal by averaging the
        preference score across all of its components.

        components = ["Grilled Chicken", "Brown Rice", "Broccoli"]
        cluster_id = cluster this meal belongs to

        Averaging means:
          if you love chicken but are neutral on rice and broccoli
          the meal still scores reasonably well overall
          no single component dominates the score
        """
        if not components:
            return 0.5   # empty meal, return neutral

        scores = [
            self.get_component_score(component, cluster_id)
            for component in components
        ]
        return float(np.mean(scores))

    def get_confidence(self, components):
        """
        Returns a human readable confidence label for the UI.

        Finds the component with the most interaction history
        and uses its like/dislike ratio to determine the label.
        The most interacted component is the most reliable signal.

        Returns one of:
          "love"    → ❤️  You love this      ratio >= 0.8
          "like"    → ⭐  You like this      ratio >= 0.6
          "neutral" → 😐  Mixed feelings     ratio >= 0.4
          "dislike" → 👎  You tend to avoid  ratio <  0.4
          "unknown" → 🆕  Haven't tried yet  total < 2
        """
        best_component = None
        best_total     = 0

        # find component with most interaction data
        for component in components:
            if component in self.meal_stats:
                s     = self.meal_stats[component]
                total = s["alpha"] + s["beta"] - 2  # subtract offsets
                if total > best_total:
                    best_total     = total
                    best_component = component

        # no meaningful history on any component
        if best_component is None or best_total < 2:
            return "unknown"

        s     = self.meal_stats[best_component]
        total = s["alpha"] + s["beta"] - 2
        ratio = (s["alpha"] - 1) / max(total, 1)

        if   ratio >= 0.8: return "love"
        elif ratio >= 0.6: return "like"
        elif ratio >= 0.4: return "neutral"
        else:              return "dislike"

    # ─────────────────────────────────────────────────────
    # LEARNING — UPDATE FROM USER FEEDBACK
    # ─────────────────────────────────────────────────────

    def update(self, components, cluster_id, liked: bool):
        """
        Called every time the user presses 👍 or 👎.

        Updates BOTH levels simultaneously:
          component level  → each ingredient builds its own history
          cluster level    → the meal type as a whole builds history

        Updating each component separately is critical for
        handling rotating menus — if you like chicken in one
        meal, that history transfers to chicken in any future
        meal even if the full dish name is completely different.

        Example:
          👍 on "Grilled Chicken + Brown Rice + Broccoli"
          updates:
            "Grilled Chicken" alpha += 1
            "Brown Rice"      alpha += 1
            "Broccoli"        alpha += 1
            cluster_2         alpha += 1

          Next time "Herb Roasted Chicken" appears:
            exact score   → 0.5 neutral  (never seen this name)
            cluster score → high         (cluster 2 well liked)
            final score   → pulled up by cluster history
        """

        # update each component individually
        for component in components:

            # initialize if first time seeing this component
            if component not in self.meal_stats:
                self.meal_stats[component] = {"alpha": 1, "beta": 1}

            if liked:
                self.meal_stats[component]["alpha"] += 1
            else:
                self.meal_stats[component]["beta"]  += 1

            # persist immediately — never lose data
            self.save_component_to_db(component)

        # update cluster level
        if cluster_id not in self.cluster_stats:
            self.cluster_stats[cluster_id] = {"alpha": 1, "beta": 1}

        if liked:
            self.cluster_stats[cluster_id]["alpha"] += 1
        else:
            self.cluster_stats[cluster_id]["beta"]  += 1

        self.save_cluster_to_db(cluster_id)

    # ─────────────────────────────────────────────────────
    # STATS — FOR THE STATS PAGE UI
    # ─────────────────────────────────────────────────────

    def get_top_meals(self, n=10):
        """
        Returns top N components sorted by mean preference score.

        Uses the mean of the beta distribution:
          mean = alpha / (alpha + beta)

        Rather than a random draw — this gives a stable
        deterministic ranking for display purposes.
        The random draw is only used during scoring
        to enable exploration of uncertain meals.
        """
        scored = []

        for meal_name, s in self.meal_stats.items():
            total = s["alpha"] + s["beta"] - 2   # subtract offsets
            if total < 1:
                continue   # skip items with no real feedback yet

            mean_score = (s["alpha"] - 1) / max(total, 1)
            scored.append({
                "meal":       meal_name,
                "score":      round(mean_score, 2),
                "likes":      s["alpha"] - 1,
                "dislikes":   s["beta"]  - 1,
                "total":      total,
                "confidence": self.get_confidence([meal_name])
            })

        return sorted(
            scored,
            key=lambda x: x["score"],
            reverse=True
        )[:n]

    def get_all_stats(self):
        """
        Returns full preference history for every component seen.
        Used to render the complete preference table on stats page.
        """
        return self.get_top_meals(n=len(self.meal_stats))

    def get_cluster_summary(self):
        """
        Returns like/dislike summary per cluster.
        Used on stats page to show which meal types
        the user generally prefers.

        e.g.
          cluster 0 → 12 likes, 2 dislikes  (user loves lean protein meals)
          cluster 3 →  1 like,  8 dislikes  (user dislikes vegetarian meals)
        """
        summary = []
        for cluster_id, s in self.cluster_stats.items():
            total = s["alpha"] + s["beta"] - 2
            if total < 1:
                continue

            mean_score = (s["alpha"] - 1) / max(total, 1)
            summary.append({
                "cluster_id": cluster_id,
                "likes":      s["alpha"] - 1,
                "dislikes":   s["beta"]  - 1,
                "score":      round(mean_score, 2)
            })

        return sorted(
            summary,
            key=lambda x: x["score"],
            reverse=True
        )