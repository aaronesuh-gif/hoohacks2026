class ClusterModel:
    """
    Classifies individual food items into one of 7 food type clusters
    based on protein type and macro ratios.

    This is a rule-based classifier — not a learning algorithm.
    It runs on every scraped item once per day and attaches a
    cluster letter. It does not learn, does not store anything,
    does not update from feedback.

    Its only job is to give the preference model a consistent
    label for each food type so that preference history can
    transfer across new menu items automatically.

    THE 7 CLUSTERS:
      A — Lean Protein      chicken, fish, turkey, egg
                            high protein%, very low carb
      B — Clean Starch      rice, quinoa, sweet potato
                            high carb%, low fat
      C — Heavy Starch      pasta, fries, garlic bread
                            high carb%, higher fat
      D — Green Vegetable   broccoli, asparagus, spinach
                            very low calorie, low fat
      E — Red Meat          beef, pork, lamb
                            high protein%, higher fat than A
      F — Plant Protein     tofu, lentils, beans
                            protein + carb mix
      G — Sauce / Topping   dressings, condiments, unknowns
                            very high fat% or very low calorie

    WHY RULES OVER KMEANS:
      KMeans cannot reliably separate chicken from tofu because
      their macros can overlap significantly. Using protein_type
      explicitly guarantees they always land in different clusters,
      which keeps preference signal clean and never bleeds
      between food types the user treats completely differently.
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

    def assign_cluster(self, item):
        """
        Assigns a single food item to a cluster.

        Uses protein_type (from protein_detector.py) and
        macro ratio calculations. Rules checked in priority
        order — first match wins.

        item = {
            "meal_name":    "Grilled Chicken Breast",
            "calories":     180,
            "protein":      35,
            "carbs":        0,
            "fats":         4,
            "protein_type": "chicken"
        }

        Returns one letter string: "A" "B" "C" "D" "E" "F" "G"
        """
        protein = item.get("protein_type", "unknown")
        cal     = item.get("calories", 0)
        pro     = item.get("protein",  0)
        carbs   = item.get("carbs",    0)
        fats    = item.get("fats",     0)

        if cal <= 0:
            return "G"

        protein_pct = (pro   * 4) / cal
        carb_pct    = (carbs * 4) / cal
        fat_pct     = (fats  * 9) / cal

        # G first — catch condiments before any other rule fires
        if cal < 80 or (fat_pct >= 0.70 and cal < 200):
            return "G"

        # A — lean protein
        if protein in ["chicken", "fish", "turkey", "egg"]:
            if protein_pct >= 0.40 and carbs <= 8:
                return "A"

        # E — red meat
        if protein in ["beef", "pork", "lamb"]:
            if protein_pct >= 0.25 and carbs <= 10:
                return "E"

        # F — plant protein
        if protein in ["tofu", "vegetarian"]:
            if protein_pct >= 0.15:
                return "F"

        # D — green vegetable
        if cal <= 100 and fat_pct <= 0.25 and protein_pct <= 0.35:
            return "D"

        # B — clean starch
        if carb_pct >= 0.60 and fat_pct <= 0.20:
            return "B"

        # C — heavy starch
        if carb_pct >= 0.50 and fat_pct > 0.20:
            return "C"

        # fallback
        return "G"

    def assign_clusters_to_items(self, items):
        """
        Assigns cluster_id to every item in a list.
        Returns the same list with cluster_id attached to each item.
        No database. No caching. Pure computation.

        Called by meal_builder after scraping before assembly.
        """
        for item in items:
            item["cluster_id"] = self.assign_cluster(item)
        return items

    def verify_item(self, item):
        """
        Prints the cluster assignment for one item.
        Use during development to confirm items land correctly.

        Expected results:
          Grilled Chicken Breast  →  A (Lean Protein)
          Brown Rice              →  B (Clean Starch)
          Pasta                   →  C (Heavy Starch)
          Steamed Broccoli        →  D (Green Vegetable)
          Ground Beef             →  E (Red Meat)
          Tofu                    →  F (Plant Protein)
          Caesar Dressing         →  G (Sauce / Topping)
        """
        cluster = self.assign_cluster(item)
        label   = self.CLUSTER_LABELS.get(cluster, "Unknown")
        print(f"{item['meal_name']:35} → {cluster} ({label})")
        return cluster

    def get_cluster_summary(self, items):
        """
        Groups a list of items by cluster after assignment.
        Use right after assign_clusters_to_items() during
        development to verify groupings look correct.
        Items must already have cluster_id attached.
        """
        summary = {cid: [] for cid in self.CLUSTER_LABELS}
        for item in items:
            cid = item.get("cluster_id", "G")
            summary.setdefault(cid, []).append(item["meal_name"])
        return {
            f"{cid} ({self.CLUSTER_LABELS[cid]})": names
            for cid, names in summary.items()
            if names
        }