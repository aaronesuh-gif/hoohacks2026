import streamlit as st
import json
import os

st.set_page_config(page_title="MacroSack", page_icon="🍽️", layout="centered")

# ── Storage ───────────────────────────────────────────────────────────────────
PROFILE_FILE = "user_profile.json"

def load_profile():
    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE) as f:
            return json.load(f)
    return None

def save_profile(p):
    with open(PROFILE_FILE, "w") as f:
        json.dump(p, f, indent=2)

if "profile" not in st.session_state:
    st.session_state.profile = load_profile()

if "show_profile" not in st.session_state:
    st.session_state.show_profile = st.session_state.profile is None

# ── Dining hall data ──────────────────────────────────────────────────────────
DINING_HALLS = {
    "🏛️ O'Hill (Observatory Hill)": [
        {"name": "Grilled Chicken Breast",  "calories": 280, "tags": "Protein · Savory"},
        {"name": "Pasta Marinara",          "calories": 420, "tags": "Carbs · Vegetarian"},
        {"name": "Caesar Salad",            "calories": 210, "tags": "Light · Vegetarian"},
        {"name": "Beef Stir Fry",           "calories": 390, "tags": "Protein · Umami"},
        {"name": "Seasonal Vegetable Soup", "calories": 150, "tags": "Light · Vegetarian"},
    ],
    "🏛️ Newcomb Hall": [
        {"name": "Carved Roast Turkey",     "calories": 310, "tags": "Protein · Savory"},
        {"name": "Mac & Cheese",            "calories": 480, "tags": "Carbs · Comfort"},
        {"name": "Sushi Rolls",             "calories": 260, "tags": "Light · Umami"},
        {"name": "BBQ Pulled Pork",         "calories": 440, "tags": "Protein · Smoky"},
        {"name": "Garden Salad Bar",        "calories": 120, "tags": "Light · Vegetarian"},
    ],
    "🏛️ Runk Dining Hall": [
        {"name": "Brick Oven Pizza",        "calories": 510, "tags": "Carbs · Comfort"},
        {"name": "Grilled Salmon",          "calories": 340, "tags": "Protein · Savory"},
        {"name": "Vegetable Curry",         "calories": 370, "tags": "Spicy · Vegetarian"},
        {"name": "Deli Sandwich Bar",       "calories": 430, "tags": "Carbs · Customizable"},
        {"name": "Yogurt Parfait",          "calories": 190, "tags": "Sweet · Light"},
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# PROFILE PAGE
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.show_profile:
    st.title("🍽️ MacroSack")
    st.write("Enter your details below.")
    st.divider()

    existing = st.session_state.profile or {}

    st.subheader("Height")
    c1, c2 = st.columns(2)
    with c1:
        ft = st.number_input("Feet (ft)", min_value=3, max_value=8,
                             value=int(existing.get("ft", 5)))
    with c2:
        ins = st.number_input("Inches (in)", min_value=0, max_value=11,
                              value=int(existing.get("ins", 9)))

    st.subheader("Weight")
    weight = st.number_input("Pounds (lbs)", min_value=50, max_value=600,
                             value=int(existing.get("weight_lbs", 160)))

    st.subheader("Daily calorie goal")
    calorie_goal = st.number_input("Calories (kcal)", min_value=500, max_value=10000,
                                   value=int(existing.get("calorie_goal", 2000)), step=50)

    st.write("")
    if st.button("Save & continue →", type="primary", use_container_width=True):
        profile = {
            "ft": ft, "ins": ins,
            "weight_lbs": weight,
            "calorie_goal": calorie_goal,
            "height_display": f"{ft} ft {ins} in",
            "weight_display": f"{weight} lbs",
        }
        st.session_state.profile = profile
        st.session_state.show_profile = False
        save_profile(profile)
        st.rerun()

    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
profile = st.session_state.profile

st.title("🍽️ MacroSack")

# Profile summary
c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
c1.metric("Height", profile["height_display"])
c2.metric("Weight", profile["weight_display"])
c3.metric("Daily goal", f"{profile['calorie_goal']:,} kcal")
with c4:
    st.write("")
    st.write("")
    if st.button("✏️ Edit"):
        st.session_state.show_profile = True
        st.rerun()

st.divider()
st.subheader("Today's recommended picks")

for hall, items in DINING_HALLS.items():
    st.markdown(f"#### {hall}")
    for item in items:
        col_name, col_tags, col_cal = st.columns([3, 3, 1])
        with col_name:
            st.write(item["name"])
        with col_tags:
            st.caption(item["tags"])
        with col_cal:
            st.write(f"{item['calories']} kcal")
    st.divider()