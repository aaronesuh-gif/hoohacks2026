import streamlit as st
import sqlite3
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scoring.recommender             import get_recommendations, on_feedback
from models.preference_model import PreferenceModel

DB_PATH = "Database/meals.db"

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="UVA Dining",
    page_icon="🍽️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 520px; }

.meal-card { background: white; border: 0.5px solid #e8e8e8; border-radius: 14px; padding: 16px 18px; margin-bottom: 12px; }
.meal-rank { font-size: 11px; color: #999; margin-bottom: 3px; font-weight: 500; letter-spacing: 0.04em; }
.meal-name { font-size: 15px; font-weight: 500; color: #111; margin-bottom: 10px; line-height: 1.4; }
.cluster-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 10px; }
.cluster-tag { font-size: 10px; padding: 2px 8px; border-radius: 99px; border: 0.5px solid #e0e0e0; color: #666; background: #f8f8f8; }
.macro-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 10px; }
.macro-box { background: #f7f7f7; border-radius: 8px; padding: 6px; text-align: center; }
.macro-val { font-size: 14px; font-weight: 500; color: #111; }
.macro-label { font-size: 10px; color: #999; margin-top: 1px; }
.score-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.score-bar-bg { flex: 1; height: 4px; background: #f0f0f0; border-radius: 99px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 99px; }
.score-val { font-size: 11px; color: #999; min-width: 30px; text-align: right; }
.confidence-row { display: flex; align-items: center; gap: 6px; }
.conf-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.conf-text { font-size: 12px; color: #666; }
.section-label { font-size: 11px; font-weight: 500; color: #aaa; letter-spacing: 0.07em; text-transform: uppercase; margin-bottom: 10px; margin-top: 4px; }
.stat-card { background: #f7f7f7; border-radius: 10px; padding: 14px 16px; }
.stat-val { font-size: 26px; font-weight: 500; color: #111; }
.stat-label { font-size: 12px; color: #888; margin-top: 2px; }
.cluster-row-display { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.cluster-name-label { font-size: 13px; color: #333; min-width: 120px; }
.cluster-bar-bg { flex: 1; height: 6px; background: #f0f0f0; border-radius: 99px; overflow: hidden; }
.cluster-bar-fill { height: 100%; border-radius: 99px; }
.cluster-score-label { font-size: 12px; color: #888; min-width: 32px; text-align: right; }
.page-title { font-size: 20px; font-weight: 500; color: #111; }
.page-subtitle { font-size: 13px; color: #888; margin-top: 2px; }
.toast-success { background: #f0faf5; color: #1a7a52; border-radius: 8px; padding: 8px 12px; font-size: 13px; text-align: center; margin-top: 6px; }
.stButton > button { border-radius: 10px; font-family: 'DM Sans', sans-serif; font-weight: 500; border: 0.5px solid #ddd; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────

def create_tables():
    import os
    os.makedirs("Database", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cluster_preferences (
            cluster_id TEXT PRIMARY KEY,
            likes      INT  DEFAULT 0,
            dislikes   INT  DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS todays_meals (
            meal_name TEXT, components TEXT, component_clusters TEXT,
            calories REAL, protein REAL, carbs REAL, fats REAL,
            protein_type TEXT, dining_hall TEXT
        );
        CREATE TABLE IF NOT EXISTS user_profile (
            name TEXT, goal TEXT, daily_calories INT, meals_per_day INT,
            meal_calories INT, goal_protein REAL, goal_carbs REAL,
            goal_fats REAL, dorm TEXT
        );
    """)
    conn.commit()
    conn.close()


def get_user_profile():
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute("SELECT * FROM user_profile LIMIT 1").fetchone()
        conn.close()
        if not row:
            return None
        keys = ["name","goal","daily_calories","meals_per_day","meal_calories",
                "goal_protein","goal_carbs","goal_fats","dorm"]
        return dict(zip(keys, row))
    except Exception:
        return None


def save_user_profile(profile):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM user_profile")
    conn.execute("""
        INSERT INTO user_profile
        (name,goal,daily_calories,meals_per_day,meal_calories,
         goal_protein,goal_carbs,goal_fats,dorm)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        profile["name"], profile["goal"], profile["daily_calories"],
        profile["meals_per_day"], profile["meal_calories"],
        profile["goal_protein"], profile["goal_carbs"],
        profile["goal_fats"], profile["dorm"],
    ))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────

create_tables()

if "page"           not in st.session_state: st.session_state.page = "home"
if "feedback_given" not in st.session_state: st.session_state.feedback_given = {}

preference_model = PreferenceModel()

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

# hall names exactly as stored by campusdish.py
ALL_HALLS = ["Fresh Food Company", "Observatory Hill", "Runk"]

DORMS = sorted([
    "Alderman Road", "Balz-Dobie", "Bice House", "Bonnycastle",
    "Brown College", "Cauthen House", "Copeley Hill", "Dunglison",
    "Emmet/Ivy", "Gooch-Dillard", "Hereford", "Kellogg", "Lambeth",
    "Lefevre", "Lile-Maupin", "McCormick Road", "Newcomb (On-site)",
    "O'Hill (On-site)", "Runk (On-site)", "Watson-Webb",
])

WALKING_DISTANCES = {
    "Fresh Food Company": {
        "Runk (On-site)": 0.0, "Cauthen House": 0.1, "Bice House": 0.1,
        "Hereford": 0.2, "Lile-Maupin": 0.2, "Brown College": 0.3,
        "Balz-Dobie": 0.4, "Gooch-Dillard": 0.4, "Kellogg": 0.4,
        "Bonnycastle": 0.5, "Watson-Webb": 0.5, "Lefevre": 0.5,
        "Dunglison": 0.6, "Lambeth": 0.7, "Emmet/Ivy": 0.8,
        "Copeley Hill": 0.9, "Alderman Road": 1.0, "McCormick Road": 1.1,
        "O'Hill (On-site)": 1.2, "Newcomb (On-site)": 1.3,
    },
    "Observatory Hill": {
        "O'Hill (On-site)": 0.0, "McCormick Road": 0.1, "Alderman Road": 0.2,
        "Emmet/Ivy": 0.3, "Lambeth": 0.4, "Dunglison": 0.5,
        "Lefevre": 0.5, "Watson-Webb": 0.6, "Bonnycastle": 0.6,
        "Balz-Dobie": 0.7, "Gooch-Dillard": 0.7, "Kellogg": 0.7,
        "Brown College": 0.8, "Hereford": 0.9, "Lile-Maupin": 0.9,
        "Copeley Hill": 1.0, "Cauthen House": 1.1, "Bice House": 1.1,
        "Newcomb (On-site)": 1.2, "Runk (On-site)": 1.2,
    },
    "Runk": {
        "Newcomb (On-site)": 0.0, "Dunglison": 0.2, "Lefevre": 0.2,
        "Watson-Webb": 0.3, "Bonnycastle": 0.3, "Lambeth": 0.4,
        "Alderman Road": 0.4, "McCormick Road": 0.5, "Balz-Dobie": 0.5,
        "Gooch-Dillard": 0.5, "Kellogg": 0.5, "Emmet/Ivy": 0.6,
        "Brown College": 0.7, "O'Hill (On-site)": 0.8, "Hereford": 0.9,
        "Lile-Maupin": 0.9, "Copeley Hill": 1.0, "Cauthen House": 1.1,
        "Bice House": 1.1, "Runk (On-site)": 1.3,
    }
}

CLUSTER_NAMES = {
    "A": "Lean Protein", "B": "Clean Starch", "C": "Heavy Starch",
    "D": "Green Vegetable", "E": "Red Meat", "F": "Plant Protein",
    "G": "Sauce / Topping",
}

CONFIDENCE_COLORS = {
    "love": "#1D9E75", "like": "#378ADD",
    "neutral": "#BA7517", "dislike": "#E24B4A", "unknown": "#CCCCCC",
}

CONFIDENCE_LABELS = {
    "love": "You love this type", "like": "You like this type",
    "neutral": "Mixed feelings", "dislike": "You tend to avoid",
    "unknown": "Haven't tried yet",
}


def get_distance_label(dorm, hall):
    d = WALKING_DISTANCES.get(hall, {}).get(dorm)
    if d is None:   return "?"
    if d == 0.0:    return "On-site"
    return f"{d:.1f} mi · ~{round(d*20)} min"


def get_score_color(score):
    if score >= 0.75: return "#1D9E75"
    if score >= 0.55: return "#378ADD"
    return "#888780"


def parse_components_with_clusters(meal):
    components = meal["components"].split(",")
    clusters   = meal["component_clusters"].split(",")
    return [{"name": n.strip(), "cluster_id": c.strip()}
            for n, c in zip(components, clusters)]


# ─────────────────────────────────────────────────────────────
# MEAL CARD
# ─────────────────────────────────────────────────────────────

def render_meal_card(scored, rank, hall_key):
    meal       = scored["meal"]
    score      = scored["score"]
    confidence = scored["confidence"]
    meal_key   = f"{hall_key}_{rank}"

    cwc        = parse_components_with_clusters(meal)
    bar_color  = get_score_color(score)
    bar_width  = int(score * 100)
    conf_color = CONFIDENCE_COLORS.get(confidence, "#CCC")
    conf_label = CONFIDENCE_LABELS.get(confidence, "")

    tags_html = "".join([
        f'<span class="cluster-tag">{CLUSTER_NAMES.get(c["cluster_id"], c["cluster_id"])}</span>'
        for c in cwc
    ])

    st.markdown(f"""
    <div class="meal-card">
        <div class="meal-rank">#{rank}</div>
        <div class="meal-name">{meal['meal_name']}</div>
        <div class="cluster-tags">{tags_html}</div>
        <div class="score-row">
            <div class="score-bar-bg">
                <div class="score-bar-fill" style="width:{bar_width}%;background:{bar_color};"></div>
            </div>
            <div class="score-val">{score:.2f}</div>
        </div>
        <div class="macro-row">
            <div class="macro-box"><div class="macro-val">{int(meal['calories'])}</div><div class="macro-label">cal</div></div>
            <div class="macro-box"><div class="macro-val">{int(meal['protein'])}g</div><div class="macro-label">protein</div></div>
            <div class="macro-box"><div class="macro-val">{int(meal['carbs'])}g</div><div class="macro-label">carbs</div></div>
            <div class="macro-box"><div class="macro-val">{int(meal['fats'])}g</div><div class="macro-label">fat</div></div>
        </div>
        <div class="confidence-row">
            <span class="conf-dot" style="background:{conf_color};"></span>
            <span class="conf-text">{conf_label}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if meal_key not in st.session_state.feedback_given:
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if st.button("👍", key=f"like_{meal_key}"):
                on_feedback(meal, liked=True)
                st.session_state.feedback_given[meal_key] = "liked"
                st.rerun()
        with col2:
            if st.button("👎", key=f"dislike_{meal_key}"):
                on_feedback(meal, liked=False)
                st.session_state.feedback_given[meal_key] = "disliked"
                st.rerun()
    else:
        result = st.session_state.feedback_given[meal_key]
        st.markdown(f"""
        <div class="toast-success">
            {"Liked! Cluster scores updated." if result == "liked" else "Noted. Cluster scores updated."}
        </div>
        """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────

def page_onboarding():
    st.markdown('<div class="page-title">🍽️ UVA Dining</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Set up your profile to get started</div><br>', unsafe_allow_html=True)

    with st.form("onboarding_form"):
        name  = st.text_input("Your name", placeholder="e.g. Aaron")
        dorm  = st.selectbox("Your dorm", DORMS, index=DORMS.index("Gooch-Dillard"))
        goal  = st.radio("Fitness goal", ["Bulk", "Cut", "Maintain", "Athletic"], horizontal=True)
        daily_cal     = st.number_input("Daily calories", 1200, 5000, 3000, 50)
        meals_per_day = st.selectbox("Meals per day", [2, 3, 4, 5], index=1)
        submitted     = st.form_submit_button("Get started →", use_container_width=True)

        if submitted and name:
            meal_cal = daily_cal // meals_per_day
            split    = {"Bulk": (.30,.45,.25), "Cut": (.40,.35,.25),
                        "Maintain": (.30,.40,.30), "Athletic": (.30,.50,.20)}[goal]
            save_user_profile({
                "name": name, "goal": goal,
                "daily_calories": daily_cal, "meals_per_day": meals_per_day,
                "meal_calories":  meal_cal,
                "goal_protein":   round((meal_cal * split[0]) / 4),
                "goal_carbs":     round((meal_cal * split[1]) / 4),
                "goal_fats":      round((meal_cal * split[2]) / 9),
                "dorm":           dorm,
            })
            st.session_state.page = "home"
            st.rerun()
        elif submitted:
            st.warning("Please enter your name.")


def page_home():
    profile = get_user_profile()
    dorm    = profile.get("dorm", "") if profile else ""
    name    = profile.get("name", "there") if profile else "there"

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<div class="page-title">Today\'s meals</div>', unsafe_allow_html=True)
        st.markdown('<div class="page-subtitle">Ranked by your preferences</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div style="text-align:right;padding-top:8px;font-size:13px;color:#888;">Hi, {name}</div>',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    recommendations = get_recommendations()

    tab_labels = [f"{h}  ·  {get_distance_label(dorm, h)}" for h in ALL_HALLS]
    tabs       = st.tabs(tab_labels)

    for tab, hall in zip(tabs, ALL_HALLS):
        with tab:
            scored_meals = recommendations.get(hall, [])
            if not scored_meals:
                st.markdown("""
                <div style="text-align:center;padding:40px 0;color:#aaa;font-size:14px;">
                    No meals available right now.<br>
                    Run <code>python seed_data.py</code> to load demo data.
                </div>
                """, unsafe_allow_html=True)
                continue
            st.markdown('<div class="section-label">Top picks for you</div>', unsafe_allow_html=True)
            for rank, scored in enumerate(scored_meals, 1):
                render_meal_card(scored, rank, hall.replace(" ", "_").replace("'", ""))


def page_stats():
    st.markdown('<div class="page-title">My preferences</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Based on your ratings</div><br>', unsafe_allow_html=True)

    summary        = preference_model.get_cluster_summary()
    total_likes    = sum(c["likes"]    for c in summary)
    total_dislikes = sum(c["dislikes"] for c in summary)
    total_rated    = total_likes + total_dislikes

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="stat-card"><div class="stat-val">{total_rated}</div><div class="stat-label">Meals rated</div></div>',
                    unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="stat-card"><div class="stat-val">{total_likes}</div><div class="stat-label">Liked</div></div>',
                    unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Food type preferences</div>', unsafe_allow_html=True)

    if not summary:
        st.markdown('<div style="text-align:center;padding:30px 0;color:#aaa;font-size:14px;">Rate some meals to see your preferences here.</div>',
                    unsafe_allow_html=True)
        return

    for cluster in summary:
        score     = cluster["score"]
        bar_pct   = int(score * 100)
        bar_color = get_score_color(score)
        st.markdown(f"""
        <div class="cluster-row-display">
            <div class="cluster-name-label">{cluster['label']}</div>
            <div class="cluster-bar-bg">
                <div class="cluster-bar-fill" style="width:{bar_pct}%;background:{bar_color};"></div>
            </div>
            <div class="cluster-score-label">{score:.2f}</div>
        </div>
        <div style="font-size:11px;color:#bbb;margin-bottom:10px;padding-left:130px;">
            {cluster['likes']} liked · {cluster['dislikes']} disliked
        </div>
        """, unsafe_allow_html=True)


def page_settings():
    profile = get_user_profile()
    st.markdown('<div class="page-title">Settings</div><br>', unsafe_allow_html=True)

    with st.form("settings_form"):
        current_dorm = profile.get("dorm", DORMS[0]) if profile else DORMS[0]
        dorm_idx     = DORMS.index(current_dorm) if current_dorm in DORMS else 0
        dorm         = st.selectbox("Your dorm", DORMS, index=dorm_idx)

        current_goal = profile.get("goal", "Maintain") if profile else "Maintain"
        goal         = st.radio("Fitness goal", ["Bulk","Cut","Maintain","Athletic"],
                                index=["Bulk","Cut","Maintain","Athletic"].index(current_goal),
                                horizontal=True)

        current_cal   = int(profile.get("daily_calories", 3000)) if profile else 3000
        daily_cal     = st.number_input("Daily calories", 1200, 5000, current_cal, 50)

        current_mpd   = int(profile.get("meals_per_day", 3)) if profile else 3
        meals_per_day = st.selectbox("Meals per day", [2,3,4,5],
                                     index=[2,3,4,5].index(current_mpd))

        saved = st.form_submit_button("Save changes", use_container_width=True)
        if saved:
            meal_cal = daily_cal // meals_per_day
            split    = {"Bulk": (.30,.45,.25), "Cut": (.40,.35,.25),
                        "Maintain": (.30,.40,.30), "Athletic": (.30,.50,.20)}[goal]
            existing_name = profile.get("name","") if profile else ""
            save_user_profile({
                "name": existing_name, "goal": goal,
                "daily_calories": daily_cal, "meals_per_day": meals_per_day,
                "meal_calories":  meal_cal,
                "goal_protein":   round((meal_cal * split[0]) / 4),
                "goal_carbs":     round((meal_cal * split[1]) / 4),
                "goal_fats":      round((meal_cal * split[2]) / 9),
                "dorm":           dorm,
            })
            st.success("Saved!")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="border-top:0.5px solid #eee;padding-top:16px;"><div style="font-size:13px;color:#aaa;margin-bottom:10px;">Danger zone</div></div>',
                unsafe_allow_html=True)

    if st.button("Reset preference history", use_container_width=True):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM cluster_preferences")
        conn.commit()
        conn.close()
        preference_model.cluster_stats = {}
        st.success("Preference history cleared.")
        st.rerun()


# ─────────────────────────────────────────────────────────────
# NAV + ROUTER
# ─────────────────────────────────────────────────────────────

def render_nav():
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="border-top:0.5px solid #eee;padding-top:8px;"></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🏠  Home",     use_container_width=True):
            st.session_state.page = "home";     st.rerun()
    with col2:
        if st.button("📊  Stats",    use_container_width=True):
            st.session_state.page = "stats";    st.rerun()
    with col3:
        if st.button("⚙️  Settings", use_container_width=True):
            st.session_state.page = "settings"; st.rerun()


profile = get_user_profile()
if profile is None:
    page_onboarding()
else:
    page = st.session_state.get("page", "home")
    if   page == "home":     page_home()
    elif page == "stats":    page_stats()
    elif page == "settings": page_settings()
    render_nav()