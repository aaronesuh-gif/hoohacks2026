import sqlite3
import numpy as np
from scipy.stats import beta


class PreferenceModel:
    """
    Tracks meal preferences using Thompson Sampling.

    Maintains two levels of preference signal:
      component level  → tracks individual food items
                         "you liked grilled chicken 8 times"
      cluster level    → tracks food categories per component
                         "you liked lean protein items 14 times"

    KEY CHANGE — component clusters instead of meal clusters:
      each component gets its own cluster_id based on what
      type of food it is (lean protein, clean starch, etc.)
      rather than the assembled meal getting one cluster.

      this means:
        "Grilled Chicken" → cluster A (lean protein)
        "Brown Rice"      → cluster B (clean starch)
        "Broccoli"        → cluster D (green vegetable)

      when scoring a meal each component is scored against
      its own specific cluster — much cleaner signal than
      one cluster representing the whole assembled meal.

      liking "Grilled Chicken + Brown Rice + Broccoli":
        cluster A (lean protein) alpha += 1
        cluster B (clean starch) alpha += 1
        cluster D (green veg)    alpha += 1

      next time any lean protein appears, cluster A signal
      carries it — even if the exact item name is new.
    """

    CLUSTER_LABELS = {
        "A": "Lean Protein",
        "B": "Clean Starch",
        "C": "Heavy Starch",
        "D": "Green Vegetable",
        "E": "Red Meat",
        "F": "Plant Protein",
        "G": "Sauce / Topping"
    }

    def __init__(self, db_path="database/meals.db"):
        self.db_path       = db_path
        self.meal_stats    = {}   # { component_name: { alpha: int, beta: int } }
        self.cluster_stats = {}   # { cluster_id:     { alpha: int, beta: int } }
                                  # cluster_id is now a letter: A B C D E F G
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
        # cluster_id is now a letter string: "A", "B", "C" etc
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
        cluster_id is a letter string: "A", "B", "C" etc.
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

        cluster_id is now specific to THIS component —
        not the assembled meal. so "Grilled Chicken" always
        gets scored against cluster A (lean protein) regardless
        of what other items it is assembled with.

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
          cluster history          → general food category preference
        """

        # signal 1 — exact component history
        if component_name in self.meal_stats:
            s           = self.meal_stats[component_name]
            exact_score = float(beta.rvs(s["alpha"], s["beta"]))
            has_history = True
        else:
            exact_score = None
            has_history = False

        # signal 2 — component cluster history
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

    def get_meal_score(self, components_with_clusters):
        """
        Scores a full assembled meal by averaging the preference
        score across all components, each against its own cluster.

        CHANGED from previous version:
          before: get_meal_score(components, cluster_id)
                  one cluster_id for the whole meal
          after:  get_meal_score(components_with_clusters)
                  each component paired with its own cluster_id

        components_with_clusters = [
            {"name": "Grilled Chicken", "cluster_id": "A"},
            {"name": "Brown Rice",      "cluster_id": "B"},
            {"name": "Broccoli",        "cluster_id": "D"}
        ]

        each component scored against its own specific cluster:
          "Grilled Chicken" → scored vs cluster A (lean protein history)
          "Brown Rice"      → scored vs cluster B (clean starch history)
          "Broccoli"        → scored vs cluster D (green veg history)

        this means:
          liking chicken builds cluster A signal
          liking brown rice builds cluster B signal separately
          disliking pasta builds cluster C signal separately
          these never bleed into each other
        """
        if not components_with_clusters:
            return 0.5   # empty meal, return neutral

        scores = [
            self.get_component_score(c["name"], c["cluster_id"])
            for c in components_with_clusters
        ]
        return float(np.mean(scores))

    def get_confidence(self, components_with_clusters):
        """
        Returns a human readable confidence label for the UI.

        Finds the component with the most interaction history
        and uses its like/dislike ratio to determine the label.
        The most interacted component is the most reliable signal.

        CHANGED: now accepts components_with_clusters list
        to stay consistent with get_meal_score signature.

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
        for c in components_with_clusters:
            name = c["name"]
            if name in self.meal_stats:
                s     = self.meal_stats[name]
                total = s["alpha"] + s["beta"] - 2   # subtract offsets
                if total > best_total:
                    best_total     = total
                    best_component = name

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

    def update(self, components_with_clusters, liked: bool):
        """
        Called every time the user presses 👍 or 👎.

        CHANGED from previous version:
          before: update(components, cluster_id, liked)
                  one cluster_id updated for all components
          after:  update(components_with_clusters, liked)
                  each component updates its own cluster separately

        components_with_clusters = [
            {"name": "Grilled Chicken", "cluster_id": "A"},
            {"name": "Brown Rice",      "cluster_id": "B"},
            {"name": "Broccoli",        "cluster_id": "D"}
        ]

        👍 on this meal updates:
          "Grilled Chicken" exact history alpha += 1
          cluster A (lean protein)        alpha += 1

          "Brown Rice" exact history      alpha += 1
          cluster B (clean starch)        alpha += 1

          "Broccoli" exact history        alpha += 1
          cluster D (green vegetable)     alpha += 1

        this is the core advantage of component clusters —
        disliking a meal with pasta builds cluster C signal
        without affecting cluster A or B signal at all.
        the model learns food category preferences independently.

        soft dislike penalty for first time components:
          if a component has never been seen before and appears
          in a disliked meal, it gets a 0.5 penalty instead of 1.0
          because the dislike might be about the combination
          not the ingredient itself.
        """
        for c in components_with_clusters:
            name       = c["name"]
            cluster_id = c["cluster_id"]

            # initialize component if first time seeing it
            if name not in self.meal_stats:
                self.meal_stats[name] = {"alpha": 1, "beta": 1}

            if liked:
                # full credit on likes — explicit positive signal
                self.meal_stats[name]["alpha"] += 1
            else:
                # check if this is first time seeing this component
                total = (self.meal_stats[name]["alpha"] +
                         self.meal_stats[name]["beta"] - 2)
                if total == 0:
                    # never seen before — soft penalty
                    # dislike might be about the combination
                    # not this specific ingredient
                    self.meal_stats[name]["beta"] += 0.5
                else:
                    # seen before — full penalty
                    self.meal_stats[name]["beta"] += 1

            self.save_component_to_db(name)

            # update this component's specific cluster
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
                "confidence": self.get_confidence([{"name": meal_name,
                                                    "cluster_id": "A"}])
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
        Returns like/dislike summary per cluster with readable labels.
        Used on stats page to show which food categories
        the user generally prefers.

        e.g.
          A (Lean Protein)   → 12 likes, 2 dislikes
          C (Heavy Starch)   →  1 like,  8 dislikes
          D (Green Vegetable)→  6 likes, 1 dislike
        """
        summary = []
        for cluster_id, s in self.cluster_stats.items():
            total = s["alpha"] + s["beta"] - 2
            if total < 1:
                continue

            mean_score = (s["alpha"] - 1) / max(total, 1)
            summary.append({
                "cluster_id": cluster_id,
                "label":      self.CLUSTER_LABELS.get(cluster_id, "Unknown"),
                "likes":      s["alpha"] - 1,
                "dislikes":   s["beta"]  - 1,
                "score":      round(mean_score, 2)
            })

        return sorted(
            summary,
            key=lambda x: x["score"],
            reverse=True
        )