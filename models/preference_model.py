import sqlite3
import numpy as np
from scipy.stats import beta as beta_dist


class PreferenceModel:
    """
    Scores meals based purely on cluster preference history
    using Thompson Sampling.

    This is the ML algorithm in the project.

    The entire model state is cluster_stats — at most 7 values,
    one per cluster A through G. Each value is a beta distribution
    shaped by how many times the user has liked or disliked meals
    containing items from that cluster.

    HOW IT WORKS:

      Scoring:
        each component in a meal has a cluster_id from cluster_model
        the preference score for each component = draw from that
        cluster's beta distribution via Thompson Sampling
        meal score = average across all components

      Learning:
        when user presses 👍 or 👎 on a meal
        each unique cluster touched by that meal gets updated:
          👍 → cluster alpha += 1  (numerator of beta dist goes up)
          👎 → cluster beta  += 1  (denominator of beta dist goes up)
        saved to SQLite immediately after every update

      Why Thompson Sampling:
        instead of just computing likes / total as a score,
        we draw a random sample from the beta distribution
        this creates exploration behavior — clusters with little
        history occasionally score high and get recommended
        so the model gathers data on food types it hasnt seen much
        this is the explore/exploit tradeoff

    WHAT IS STORED:
      only cluster_preferences table — 7 rows max
      cluster_id | likes | dislikes
      nothing else
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
        self.cluster_stats = {}
        # { "A": {"alpha": int, "beta": int}, "B": {...}, ... }
        # loaded from SQLite on startup
        # updated in memory and saved to SQLite on every 👍👎
        self.load_from_db()

    # ─────────────────────────────────────────────────────
    # STARTUP
    # ─────────────────────────────────────────────────────

    def load_from_db(self):
        """
        Loads cluster like/dislike counts from SQLite into memory.
        Called automatically on startup.

        This is how the model remembers preferences between
        app sessions — without this every restart forgets everything.

        alpha = likes + 1
        beta  = dislikes + 1
        +1 offset so beta(0,0) is never undefined in scipy.
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT cluster_id, likes, dislikes FROM cluster_preferences"
        ).fetchall()
        conn.close()

        for cluster_id, likes, dislikes in rows:
            self.cluster_stats[cluster_id] = {
                "alpha": likes    + 1,
                "beta":  dislikes + 1
            }

    # ─────────────────────────────────────────────────────
    # SAVING
    # ─────────────────────────────────────────────────────

    def save_cluster_to_db(self, cluster_id):
        """
        Persists one cluster's updated counts to SQLite immediately.
        Called after every alpha or beta update so no data is lost
        if the app closes unexpectedly.
        """
        s    = self.cluster_stats[cluster_id]
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO cluster_preferences (cluster_id, likes, dislikes)
            VALUES (?, ?, ?)
            ON CONFLICT(cluster_id) DO UPDATE SET
                likes    = excluded.likes,
                dislikes = excluded.dislikes
        """, (cluster_id, s["alpha"] - 1, s["beta"] - 1))
        conn.commit()
        conn.close()

    # ─────────────────────────────────────────────────────
    # SCORING — THE ML ALGORITHM
    # ─────────────────────────────────────────────────────

    def get_cluster_score(self, cluster_id):
        """
        Scores one cluster using Thompson Sampling.

        Draws a random sample from a beta distribution
        shaped by that cluster's like/dislike history:

          beta(alpha, beta) where:
            alpha = likes + 1
            beta  = dislikes + 1

          cluster A: 14 likes, 2 dislikes
            alpha=15, beta=3
            distribution skewed heavily toward 1.0
            draw almost always returns high ~0.82
            → lean protein meals score high consistently

          cluster C: 2 likes, 8 dislikes
            alpha=3, beta=9
            distribution skewed toward 0.0
            draw almost always returns low ~0.22
            → heavy starch meals score low consistently

          cluster never rated: alpha=1, beta=1
            completely flat distribution
            draw is random 0 to 1
            → exploration: model occasionally surfaces
              unrated food types to gather data

        Returns float between 0 and 1.
        """
        if cluster_id not in self.cluster_stats:
            self.cluster_stats[cluster_id] = {"alpha": 1, "beta": 1}

        s = self.cluster_stats[cluster_id]
        return float(np.clip(beta_dist.rvs(s["alpha"], s["beta"]), 0.0, 1.0))

    def get_meal_score(self, components_with_clusters):
        """
        Scores a full assembled meal by averaging the cluster
        score of each component.

        components_with_clusters = [
            {"name": "Grilled Chicken", "cluster_id": "A"},
            {"name": "Brown Rice",      "cluster_id": "B"},
            {"name": "Broccoli",        "cluster_id": "D"}
        ]

        score = mean([cluster_A_score, cluster_B_score, cluster_D_score])

        Each cluster is scored independently:
          disliking pasta (C) does NOT affect lean protein (A)
          or clean starch (B) scores — fully isolated signals.

        Returns float between 0 and 1.
        """
        if not components_with_clusters:
            return 0.5

        scores = [
            self.get_cluster_score(c["cluster_id"])
            for c in components_with_clusters
        ]
        return float(np.mean(scores))

    def get_confidence(self, components_with_clusters):
        """
        Returns a human readable label for the UI card.

        Finds the cluster with the most interaction history
        among this meal's components — that is the most
        reliable signal for how the user feels about this meal.

        Uses the mean of beta distribution (not a random draw)
        for a stable deterministic display label.

          "love"    ❤️   ratio >= 0.8
          "like"    ⭐   ratio >= 0.6
          "neutral" 😐   ratio >= 0.4
          "dislike" 👎   ratio <  0.4
          "unknown" 🆕   fewer than 2 total interactions
        """
        best_cluster = None
        best_total   = 0

        for c in components_with_clusters:
            cid = c["cluster_id"]
            if cid in self.cluster_stats:
                s     = self.cluster_stats[cid]
                total = s["alpha"] + s["beta"] - 2
                if total > best_total:
                    best_total   = total
                    best_cluster = cid

        if best_cluster is None or best_total < 2:
            return "unknown"

        s     = self.cluster_stats[best_cluster]
        total = s["alpha"] + s["beta"] - 2
        ratio = (s["alpha"] - 1) / max(total, 1)

        if   ratio >= 0.8: return "love"
        elif ratio >= 0.6: return "like"
        elif ratio >= 0.4: return "neutral"
        else:              return "dislike"

    # ─────────────────────────────────────────────────────
    # LEARNING — UPDATE FROM FEEDBACK
    # ─────────────────────────────────────────────────────

    def update(self, components_with_clusters, liked: bool):
        """
        Called on every 👍 or 👎 press.

        Updates each unique cluster touched by this meal once.
        Deduplicates so if two components share a cluster
        (e.g. pasta and garlic bread both in C) it only
        counts once per rating.

        👍 on "Chicken + Brown Rice + Broccoli":
          cluster A alpha += 1   (lean protein liked)
          cluster B alpha += 1   (clean starch liked)
          cluster D alpha += 1   (green vegetable liked)

        👎 on "Pasta + Garlic Bread + Caesar Dressing":
          cluster C beta += 1    (pasta and bread both C — once)
          cluster G beta += 1    (caesar dressing)

        Clusters are fully independent — these updates never
        affect each other.
        """
        updated = set()

        for c in components_with_clusters:
            cid = c["cluster_id"]

            if cid in updated:
                continue
            updated.add(cid)

            if cid not in self.cluster_stats:
                self.cluster_stats[cid] = {"alpha": 1, "beta": 1}

            if liked:
                self.cluster_stats[cid]["alpha"] += 1
            else:
                self.cluster_stats[cid]["beta"]  += 1

            self.save_cluster_to_db(cid)

    # ─────────────────────────────────────────────────────
    # STATS — FOR THE STATS PAGE
    # ─────────────────────────────────────────────────────

    def get_cluster_summary(self):
        """
        Returns all rated clusters sorted by mean preference score.
        Used on the stats page to show which food categories
        the user generally prefers.

        Uses the mean of beta distribution for stable display:
          mean = (alpha - 1) / (alpha + beta - 2)
        rather than a random draw — display needs to be stable.

        Example output:
          A (Lean Protein)    14 likes  2 dislikes  score 0.88
          B (Clean Starch)    10 likes  1 dislike   score 0.91
          C (Heavy Starch)     2 likes  8 dislikes  score 0.20
          D (Green Vegetable)  6 likes  1 dislike   score 0.86
        """
        summary = []
        for cid, s in self.cluster_stats.items():
            total = s["alpha"] + s["beta"] - 2
            if total < 1:
                continue
            mean = (s["alpha"] - 1) / max(total, 1)
            summary.append({
                "cluster_id": cid,
                "label":      self.CLUSTER_LABELS.get(cid, "Unknown"),
                "likes":      int(s["alpha"] - 1),
                "dislikes":   int(s["beta"]  - 1),
                "score":      round(mean, 2)
            })
        return sorted(summary, key=lambda x: x["score"], reverse=True)