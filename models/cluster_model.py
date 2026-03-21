import numpy as np
import sqlite3
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


class ClusterModel:
    """
    Assigns every individual scraped food item to one of 7
    predefined clusters based on protein type and macro profile.

    WHY THIS EXISTS:
      The preference model needs a cluster_id for every component
      so it can use cluster history as a fallback signal when
      an exact component has never been seen before.

      Without cluster_model:
        "Herb Roasted Chicken" never seen → preference score = 0.5 neutral
        model has no signal at all for new items

      With cluster_model:
        "Herb Roasted Chicken" → assigned cluster A (lean protein)
        cluster A has 14 likes from other chicken/fish/turkey items
        → preference model uses cluster A history as fallback
        → new item scores reasonably well immediately

    WHY RULE BASED OVER PURE KMEANS:
      KMeans cannot reliably separate chicken from fish meals
      because their macros are very similar — only protein type
      separates them. rule based assignment uses protein type
      explicitly and is deterministic — same item always gets
      same cluster regardless of what else is on the menu.

      KMeans is still used as a fallback for items that dont
      fit any rule cleanly.

    THE 7 CLUSTERS:
      A — lean protein      chicken, fish, turkey, egg
                            high protein%, low carb, low fat
      B — clean starch      whole grains, low fat carbs
                            brown rice, quinoa, sweet potato
      C — heavy starch      processed carbs, higher fat
                            pasta, mac and cheese, fries
      D — green vegetable   non-starchy veg, very low cal
                            broccoli, spinach, asparagus
      E — red meat          beef, pork, lamb
                            higher fat protein
      F — plant protein     tofu, lentils, beans, chickpeas
                            higher carb protein
      G — sauce / topping   dressings, sauces, condiments
                            very high fat%, small serving

    RUNS: once per day after midnight scrape
    LEARNS: nothing from user feedback — purely data driven
    OUTPUT: cluster_id letter attached to every food item
            consumed by preference_model.get_component_score()
            and preference_model.update()
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

    # must match similarity_engine.ALL_PROTEINS exactly
    # so both models operate in the same feature space
    ALL_PROTEINS = [
        "chicken", "beef", "pork", "fish",
        "turkey", "tofu", "egg", "lamb", "vegetarian"
    ]

    def __init__(self, db_path="database/meals.db"):
        self.db_path   = db_path
        self.kmeans    = KMeans(
            n_clusters   = 7,
            random_state = 42,   # fixed seed — consistent results
            n_init       = 10    # run 10 times, take best result
        )
        self.scaler    = StandardScaler()
        self.is_fitted = False

    # ─────────────────────────────────────────────────────
    # RULE BASED ASSIGNMENT — PRIMARY METHOD
    # ─────────────────────────────────────────────────────

    def assign_cluster(self, item):
        """
        Assigns a single food item to a cluster using
        predefined rules based on protein type and macro ratios.

        This is called on individual scraped items — not assembled
        meals. each component gets its own cluster_id which the
        preference model then uses independently per component.

        Rules checked in priority order — first match wins.
        Falls back to KMeans if nothing matches cleanly.

        item = {
            "meal_name":    "Grilled Chicken Breast",
            "calories":     180,
            "protein":      35,
            "carbs":        0,
            "fats":         4,
            "protein_type": "chicken"   ← from protein_detector.py
        }

        returns a single letter string: "A", "B", "C", "D", "E", "F", or "G"
        """
        protein = item.get("protein_type", "unknown")
        cal     = item.get("calories", 0)
        pro     = item.get("protein",  0)
        carbs   = item.get("carbs",    0)
        fats    = item.get("fats",     0)

        # avoid division by zero
        if cal <= 0:
            return "G"

        # calculate macro ratios as percentage of total calories
        protein_pct = (pro   * 4) / cal   # protein has 4 cal per gram
        carb_pct    = (carbs * 4) / cal   # carbs have 4 cal per gram
        fat_pct     = (fats  * 9) / cal   # fat has 9 cal per gram

        # ── cluster G — sauce / topping ─────────────────
        # check first to avoid misclassifying condiments
        # as proteins or vegetables
        # very small items or extremely fat dominant
        if cal < 80 or (fat_pct >= 0.70 and cal < 200):
            return "G"

        # ── cluster A — lean protein ─────────────────────
        # animal protein that is high protein%, very low carb
        # chicken, fish, turkey, egg all land here
        # this is the cluster most cut/athletic users will love
        if protein in ["chicken", "fish", "turkey", "egg"]:
            if protein_pct >= 0.40 and carbs <= 8:
                return "A"

        # ── cluster E — red meat protein ─────────────────
        # beef, pork, lamb — meaningfully higher fat than A
        # kept separate because users often have strong
        # preferences between red meat and white meat/fish
        if protein in ["beef", "pork", "lamb"]:
            if protein_pct >= 0.25 and carbs <= 10:
                return "E"

        # ── cluster F — plant protein ────────────────────
        # tofu, lentils, beans, chickpeas
        # higher carb than animal proteins
        # vegetarian users build their preference signal here
        if protein in ["tofu", "vegetarian"]:
            if protein_pct >= 0.15:
                return "F"

        # ── cluster D — green vegetable ──────────────────
        # low calorie, low fat, non-starchy
        # broccoli, asparagus, spinach, salad greens
        # almost universally low impact on macros
        if cal <= 100 and fat_pct <= 0.25 and protein_pct <= 0.35:
            return "D"

        # ── cluster B — clean starch ─────────────────────
        # whole grain carb source, low fat
        # brown rice, quinoa, sweet potato, couscous
        # preferred by bulk and athletic goal users
        if carb_pct >= 0.60 and fat_pct <= 0.20:
            return "B"

        # ── cluster C — heavy starch ─────────────────────
        # processed carb, higher fat than cluster B
        # pasta, mac and cheese, garlic bread, fries
        # important to separate from B because a user who
        # likes brown rice doesnt necessarily like pasta
        if carb_pct >= 0.50 and fat_pct > 0.20:
            return "C"

        # ── fallback — KMeans ────────────────────────────
        # item didnt match any rule cleanly
        # use KMeans if fitted, otherwise default to G
        return self._kmeans_fallback(item)

    def assign_clusters_to_items(self, items):
        """
        Assigns cluster ids to a list of individual food items.
        Called by the scraper after parsing each dining hall menu.

        Checks the cache first — if an item has been seen before
        it reuses the saved cluster assignment rather than
        reclassifying. this keeps cluster assignments stable
        across days for returning menu items.

        Returns the same list with cluster_id attached to each item.

        items = list of individual food item dicts from scraper
        each item gets item["cluster_id"] = "A" / "B" / etc
        """
        for item in items:
            # check if this item has been clustered before
            cached = self.load_cluster(item["meal_name"])
            if cached:
                # reuse saved assignment — same item same cluster
                item["cluster_id"] = cached
            else:
                # new item — run assignment rules
                item["cluster_id"] = self.assign_cluster(item)

            # always save — updates last_seen date
            self.save_cluster(item)

        return items

    # ─────────────────────────────────────────────────────
    # KMEANS FALLBACK
    # ─────────────────────────────────────────────────────

    def build_feature_vector(self, item):
        """
        Builds the numerical representation of a food item
        for KMeans clustering.

        MUST be identical to similarity_engine.build_feature_vector
        so both models operate in the same feature space and
        comparisons are meaningful.

        13 features:
          [calories, protein, carbs, fats,
           has_chicken, has_beef, has_pork, has_fish,
           has_turkey, has_tofu, has_egg, has_lamb,
           has_vegetarian]

        one-hot protein encoding:
          "chicken" → [1,0,0,0,0,0,0,0,0]
          "fish"    → [0,0,0,1,0,0,0,0,0]
          "unknown" → [0,0,0,0,0,0,0,0,0]
        """
        macro_features = [
            item.get("calories", 0),
            item.get("protein",  0),
            item.get("carbs",    0),
            item.get("fats",     0)
        ]
        protein_flags = [
            1 if p == item.get("protein_type", "unknown") else 0
            for p in self.ALL_PROTEINS
        ]
        return np.array(macro_features + protein_flags, dtype=float)

    def fit_kmeans(self, items):
        """
        Fits KMeans on todays scraped items.
        Called once after scraping so the fallback
        has a reference point for ambiguous items.

        StandardScaler normalizes features before fitting so
        calorie values (large numbers like 400-900) dont
        dominate over protein type flags (0 or 1) in the
        distance calculation.

        Only called if there are enough items to fit 7 clusters.
        Silently skips if not enough data.
        """
        if len(items) < 7:
            return   # not enough items to form 7 clusters

        feature_matrix = np.array([
            self.build_feature_vector(item)
            for item in items
        ])

        feature_matrix_scaled = self.scaler.fit_transform(feature_matrix)
        self.kmeans.fit(feature_matrix_scaled)
        self.is_fitted = True

    def _kmeans_fallback(self, item):
        """
        Uses KMeans to assign a cluster when no rule matched.

        Maps KMeans integer label (0-6) to letter cluster id (A-G).
        Returns "G" (misc/topping) if KMeans hasnt been fitted yet
        since G is the safest default for unclassified items.

        This is a private method — only called from assign_cluster()
        when all rules have been exhausted without a match.
        """
        if not self.is_fitted:
            return "G"

        features = self.build_feature_vector(item).reshape(1, -1)
        try:
            features_scaled = self.scaler.transform(features)
            label = int(self.kmeans.predict(features_scaled)[0])
            label_map = {
                0: "A",
                1: "B",
                2: "C",
                3: "D",
                4: "E",
                5: "F",
                6: "G"
            }
            return label_map.get(label, "G")
        except Exception:
            return "G"

    # ─────────────────────────────────────────────────────
    # DATABASE
    # ─────────────────────────────────────────────────────

    def save_cluster(self, item):
        """
        Saves an item's cluster assignment to the meal_clusters
        table in SQLite.

        Called after every cluster assignment so returning items
        dont need to be reclassified on future scrapes.

        last_seen is updated every time the item appears on the
        menu so you can tell how recently each item was available.

        ON CONFLICT updates cluster_id and last_seen but keeps
        the original nutritional data — macros dont change for
        the same named item.
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO meal_clusters
                (meal_name, cluster_id, calories,
                 protein, carbs, fats,
                 protein_type, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, DATE('now'))
            ON CONFLICT(meal_name) DO UPDATE SET
                cluster_id = excluded.cluster_id,
                last_seen  = excluded.last_seen
        """, (
            item["meal_name"],
            item["cluster_id"],
            item.get("calories",     0),
            item.get("protein",      0),
            item.get("carbs",        0),
            item.get("fats",         0),
            item.get("protein_type", "unknown")
        ))
        conn.commit()
        conn.close()

    def load_cluster(self, meal_name):
        """
        Looks up a cached cluster assignment for a food item.

        Returns the cluster letter if found, None if this item
        has never been seen and clustered before.

        Called by assign_clusters_to_items() before running
        the assignment rules — avoids reclassifying items
        that have already been processed on a previous day.

        This is how cluster assignments stay stable across
        rotating menus — an item that disappears for a week
        and comes back gets the same cluster assignment.
        """
        conn = sqlite3.connect(self.db_path)
        row  = conn.execute("""
            SELECT cluster_id FROM meal_clusters
            WHERE meal_name = ?
        """, (meal_name,)).fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_clusters(self):
        """
        Returns all saved cluster assignments from SQLite.

        Used during development to verify clusters are
        making intuitive sense — run this after the first
        scrape to confirm items are landing in the right groups.

        Expected groupings:
          A: Grilled Chicken, Baked Tilapia, Turkey Breast
          B: Brown Rice, Quinoa, Sweet Potato
          C: Pasta, Mac and Cheese, Garlic Bread
          D: Broccoli, Asparagus, Garden Salad
          E: Beef Strips, Ground Beef, Pulled Pork
          F: Tofu, Lentils, Black Beans
          G: Caesar Dressing, Gravy, Hot Sauce
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT meal_name, cluster_id, protein_type,
                   calories, protein, carbs, fats
            FROM meal_clusters
            ORDER BY cluster_id, meal_name
        """).fetchall()
        conn.close()

        keys = [
            "meal_name", "cluster_id", "protein_type",
            "calories", "protein", "carbs", "fats"
        ]
        return [dict(zip(keys, row)) for row in rows]

    # ─────────────────────────────────────────────────────
    # INTROSPECTION — VERIFICATION AND DEBUGGING
    # ─────────────────────────────────────────────────────

    def get_cluster_summary(self, items):
        """
        Groups a list of items by their assigned cluster
        and returns a readable summary dict.

        Use this right after assign_clusters_to_items() during
        development to verify items landed where you expect.

        items = list of item dicts with cluster_id attached

        returns dict like:
          {
            "A (Lean Protein)":    ["Grilled Chicken", "Tilapia", ...],
            "B (Clean Starch)":    ["Brown Rice", "Quinoa", ...],
            "C (Heavy Starch)":    ["Pasta", "Mac and Cheese", ...],
            "D (Green Vegetable)": ["Broccoli", "Asparagus", ...],
            "E (Red Meat)":        ["Beef Strips", "Pulled Pork", ...],
            "F (Plant Protein)":   ["Tofu", "Lentils", ...],
            "G (Sauce / Topping)": ["Caesar Dressing", ...]
          }
        """
        summary = {label: [] for label in self.CLUSTER_LABELS}

        for item in items:
            cid = item.get("cluster_id", "G")
            if cid in summary:
                summary[cid].append(item["meal_name"])
            else:
                summary["G"].append(item["meal_name"])

        # return with readable labels, skip empty clusters
        return {
            f"{cid} ({self.CLUSTER_LABELS[cid]})": meals
            for cid, meals in summary.items()
            if meals
        }

    def verify_item(self, item):
        """
        Runs a single item through assignment and prints
        a detailed breakdown of which rule matched and why.

        Use this during development to debug unexpected
        cluster assignments.

        item = {
            "meal_name":    "Grilled Chicken Breast",
            "calories":     180,
            "protein":      35,
            "carbs":        0,
            "fats":         4,
            "protein_type": "chicken"
        }
        """
        protein = item.get("protein_type", "unknown")
        cal     = item.get("calories", 1)
        pro     = item.get("protein",  0)
        carbs   = item.get("carbs",    0)
        fats    = item.get("fats",     0)

        protein_pct = round((pro   * 4) / cal, 2)
        carb_pct    = round((carbs * 4) / cal, 2)
        fat_pct     = round((fats  * 9) / cal, 2)

        cluster = self.assign_cluster(item)
        label   = self.CLUSTER_LABELS.get(cluster, "Unknown")

        print(f"\n{'─'*50}")
        print(f"Item:        {item['meal_name']}")
        print(f"Protein type: {protein}")
        print(f"Calories:     {cal}")
        print(f"Protein %:    {protein_pct*100:.0f}%")
        print(f"Carb %:       {carb_pct*100:.0f}%")
        print(f"Fat %:        {fat_pct*100:.0f}%")
        print(f"→ Assigned:   {cluster} ({label})")
        print(f"{'─'*50}")

        return cluster