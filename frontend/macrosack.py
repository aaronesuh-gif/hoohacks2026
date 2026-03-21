import streamlit as st
import json
import os

st.set_page_config(page_title="MacroSack", page_icon="🍽️", layout="centered")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.stApp { background: #FAFAF7; }
.profile-card {
    background: white; border: 1px solid #E8E6DF;
    border-radius: 16px; padding: 20px 24px;
    margin-bottom: 1.5rem; display: flex; gap: 32px; flex-wrap: wrap;
}
.stat-block { text-align: center; }
.stat-value { font-family: 'DM Serif Display', serif; font-size: 24px; color: #1a1a1a; }
.stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: #9a9690; margin-top: 2px; }
.hall-card {
    background: white; border: 1px solid #E8E6DF;
    border-radius: 16px; padding: 18px 20px; margin-bottom: 16px;
}
.hall-name { font-family: 'DM Serif Display', serif; font-size: 18px; color: #1a1a1a; margin-bottom: 12px; }
.food-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 0; border-bottom: 0.5px solid #F0EEE8;
}
.food-row:last-child { border-bottom: none; }
.food-row-name { font-size: 14px; color: #1a1a1a; }
.food-row-meta { font-size: 12px; color: #9a9690; white-space: nowrap; margin-left: 12px; }
.tag-pill {
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 99px; background: #F0EEE8; color: #6b6860; margin: 2px 2px 0 0;
}
.section-label {
    font-size: 11px; font-weight: 500; letter-spacing: 0.08em;
    text-transform: uppercase; color: #9a9690; margin-bottom: 12px;
}
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

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

# Always start on profile page if flagged
if "show_profile" not in st.session_state:
    st.session_state.show_profile = st.session_state.profile is None

# ── Dining hall data ──────────────────────────────────────────────────────────
DINING_HALLS = {
    "O'Hill (Observatory Hill)": [
        {"name": "Grilled Chicken Breast",  "calories": 280, "tags": ["Protein", "Savory"]},
        {"name": "Pasta Marinara",          "calories": 420, "tags": ["Carbs", "Vegetarian"]},
        {"name": "Caesar Salad",            "calories": 210, "tags": ["Light", "Vegetarian"]},
        {"name": "Beef Stir Fry",           "calories": 390, "tags": ["Protein", "Umami"]},
        {"name": "Seasonal Vegetable Soup", "calories": 150, "tags": ["Light", "Vegetarian"]},
    ],
    "Newcomb Hall": [
        {"name": "Carved Roast Turkey",     "calories": 310, "tags": ["Protein", "Savory"]},
        {"name": "Mac & Cheese",            "calories": 480, "tags": ["Carbs", "Comfort"]},
        {"name": "Sushi Rolls",             "calories": 260, "tags": ["Light", "Umami"]},
        {"name": "BBQ Pulled Pork",         "calories": 440, "tags": ["Protein", "Smoky"]},
        {"name": "Garden Salad Bar",        "calories": 120, "tags": ["Light", "Vegetarian"]},
    ],
    "Runk Dining Hall": [
        {"name": "Brick Oven Pizza",        "calories": 510, "tags": ["Carbs", "Comfort"]},
        {"name": "Grilled Salmon",          "calories": 340, "tags": ["Protein", "Savory"]},
        {"name": "Vegetable Curry",         "calories": 370, "tags": ["Spicy", "Vegetarian"]},
        {"name": "Deli Sandwich Bar",       "calories": 430, "tags": ["Carbs", "Customizable"]},
        {"name": "Yogurt Parfait",          "calories": 190, "tags": ["Sweet", "Light"]},
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# PROFILE PAGE
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.show_profile:
    st.markdown("# 🍽️ MacroSack")
    st.markdown("Enter your details below.")
    st.divider()

    existing = st.session_state.profile or {}

    st.markdown("### Height")
    c1, c2 = st.columns(2)
    with c1:
        ft = st.number_input("Feet (ft)", min_value=3, max_value=8,
                             value=int(existing.get("ft", 5)))
    with c2:
        ins = st.number_input("Inches (in)", min_value=0, max_value=11,
                              value=int(existing.get("ins", 9)))

    st.markdown("### Weight")
    weight = st.number_input("Pounds (lbs)", min_value=50, max_value=600,
                             value=int(existing.get("weight_lbs", 160)))

    st.markdown("### Daily calorie goal")
    calorie_goal = st.number_input("Calories (kcal)", min_value=500, max_value=10000,
                                   value=int(existing.get("calorie_goal", 2000)), step=50)

    st.markdown("")
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

st.markdown("# 🍽️ MacroSack")

# Profile summary
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
with col1:
    st.metric("Height", profile["height_display"])
with col2:
    st.metric("Weight", profile["weight_display"])
with col3:
    st.metric("Daily goal", f"{profile['calorie_goal']:,} kcal")
with col4:
    st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
    if st.button("✏️ Edit"):
        st.session_state.show_profile = True
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()
st.markdown("### Today's recommended picks")

# Render each dining hall using native Streamlit widgets
for hall, items in DINING_HALLS.items():
    with st.container():
        st.markdown(f"**{hall}**")
        for item in items:
            left, right = st.columns([4, 1])
            with left:
                tags = "  ".join([f"`{t}`" for t in item["tags"]])
                st.markdown(f"{item['name']}  {tags}")
            with right:
                st.markdown(f"<div style='text-align:right; color:#9a9690; font-size:13px; padding-top:4px'>{item['calories']} kcal</div>", unsafe_allow_html=True)
        st.markdown("---")