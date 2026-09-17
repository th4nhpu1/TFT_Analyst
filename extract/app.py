"""TFT Analyst: Ranked Challenger analytics and meta statistics."""

import json
import os
import re

import pandas as pd
import psycopg2
import streamlit as st

st.set_page_config(
    page_title="TFT Analyst",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SPECIAL_CHAMPIONS = {
    "kaisa": "Kai'Sa",
    "khazix": "Kha'Zix",
    "kogmaw": "Kog'Maw",
    "reksai": "Rek'Sai",
    "velkoz": "Vel'Koz",
    "chogath": "Cho'Gath",
    "leblanc": "LeBlanc",
    "masteryi": "Master Yi",
    "elderdragon": "Elder Dragon",
    "crimsonraptor": "Crimson Raptor",
    "scuttlecrab": "Scuttle Crab",
    "brambleback": "Brambleback",
    "cinderling": "Cinderling",
    "murkwolf": "Murkwolf",
}

SPECIAL_ITEMS = {
    "bfsword": "B.F. Sword",
    "giantsbelt": "Giant's Belt",
    "needlesslylargerod": "Needlessly Large Rod",
    "tearofthegoddess": "Tear of the Goddess",
    "edgeofnight": "Edge of Night",
    "handofjustice": "Hand of Justice",
    "guinsoosrageblade": "Guinsoo's Rageblade",
    "warmogsarmor": "Warmog's Armor",
    "titansresolve": "Titan's Resolve",
    "rabadonsdeathcap": "Rabadon's Deathcap",
    "dragonsclaw": "Dragon's Claw",
    "thiefsgloves": "Thief's Gloves",
    "steraksgage": "Sterak's Gage",
    "spearofshojin": "Spear of Shojin",
    "nashorstooth": "Nashor's Tooth",
    "archangelsstaff": "Archangel's Staff",
    "ludenstempest": "Luden's Tempest",
    "zhonyasparadox": "Zhonya's Paradox",
    "gamblersblade": "Gambler's Blade",
    "goldcollector": "The Collector",
    "witsend": "Wit's End",
    "seekersarmguard": "Seeker's Armguard",
    "mogulsmail": "Mogul's Mail",
    "protectorsvow": "Protector's Vow",
    "tacticianscrown": "Tactician's Crown",
    "tacticianscape": "Tactician's Cape",
    "tacticiansshield": "Tactician's Shield",
    "krakensfury": "Kraken's Fury",
    "strikersflail": "Striker's Flail",
    "aegisofdawn": "Aegis of Dawn",
    "aegisofdusk": "Aegis of Dusk",
    "talismanofascension": "Talisman of Ascension",
}


def clean_unit_name(identifier: str) -> str:
    """Normalize raw game unit IDs (e.g. DA_Lux18_Base, DA_Lux_18) to clean names (e.g. Lux)."""
    if not identifier or not isinstance(identifier, str):
        return ""
    name = identifier.strip()
    name = re.sub(r"^(DA_|TFT\d+_)", "", name)
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"(_Base|_AD|_AP|Small)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"(_?\d+)$", "", name)
    name = re.sub(r"(_Base|_AD|_AP|Small)$", "", name, flags=re.IGNORECASE)
    name = name.replace("_", " ").strip()

    key = name.replace(" ", "").lower()
    if key in SPECIAL_CHAMPIONS:
        return SPECIAL_CHAMPIONS[key]

    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()
    return name


def clean_item_name(identifier: str) -> str:
    """Normalize raw game item IDs (e.g. DA_18_EmblemBlackthorn, DA_GuinsoosRageblade) to human-readable names."""
    if not identifier or not isinstance(identifier, str):
        return ""
    raw = identifier.strip()

    is_radiant = bool(re.search(r"Radiant", raw, flags=re.IGNORECASE))
    is_artifact = bool(re.search(r"Artifact", raw, flags=re.IGNORECASE))
    is_component = bool(re.search(r"Component", raw, flags=re.IGNORECASE))

    name = re.sub(r"^(DA_|TFT\d+_)", "", raw)
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"^(Item_)?Artifact_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^Component_", "", name, flags=re.IGNORECASE)
    name = re.sub(r"(_?Radiant)$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"(\d+)$", "", name)

    emblem_match = re.match(r"Emblem([A-Za-z]+?)(Augment)?$", name)
    if emblem_match:
        base_trait = emblem_match.group(1)
        is_augment = bool(emblem_match.group(2))
        base_trait = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", base_trait).strip()
        result = f"{base_trait} Emblem"
        if is_augment:
            result += " (Augment)"
        return result

    name = name.replace("_", " ").strip()
    key = name.replace(" ", "").lower()
    clean_base = SPECIAL_ITEMS.get(key)
    if not clean_base:
        clean_base = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).strip()

    tags = []
    if is_radiant:
        tags.append("Radiant")
    if is_artifact and "Artifact" not in clean_base:
        tags.append("Artifact")
    if is_component and "Component" not in clean_base and not any(
        w in clean_base for w in ("Sword", "Vest", "Belt", "Rod", "Cloak", "Bow", "Gloves", "Spatula", "Tear")
    ):
        tags.append("Component")

    if tags:
        return f"{clean_base} ({', '.join(tags)})"
    return clean_base


def clean_comp_units(comp_string: str) -> str:
    """Normalize comp unit string by cleaning each champion identifier."""
    if not comp_string or not isinstance(comp_string, str):
        return ""
    units = [clean_unit_name(u.strip()) for u in comp_string.split("+") if u.strip()]
    return " + ".join(units)


def normalize_champion_key(key: str) -> str:
    if not key or not isinstance(key, str):
        return ""
    k = re.sub(r"^(DA_|TFT\d+_)", "", key, flags=re.IGNORECASE)
    k = re.sub(r"^\d+_", "", k)
    k = re.sub(r"(_Base|_AD|_AP|Small|_18|18)$", "", k, flags=re.IGNORECASE)
    k = re.sub(r"(_?\d+)$", "", k)
    k = re.sub(r"(_Base|_AD|_AP|Small)$", "", k, flags=re.IGNORECASE)
    return k.replace("_", "").replace(" ", "").replace("'", "").lower()


def normalize_item_key(key: str) -> str:
    if not key or not isinstance(key, str):
        return ""
    k = re.sub(r"^(DA_|TFT\d+_)", "", key, flags=re.IGNORECASE)
    k = re.sub(r"^\d+_", "", k)
    k = re.sub(r"^(Item_)?Artifact_", "", k, flags=re.IGNORECASE)
    k = re.sub(r"^Component_", "", k, flags=re.IGNORECASE)
    k = re.sub(r"(_?Radiant)$", "", k, flags=re.IGNORECASE)
    k = re.sub(r"(\d+)$", "", k)
    return k.replace("_", "").replace(" ", "").replace("'", "").lower()


def load_assets():
    assets_path = os.path.join(os.path.dirname(__file__), "tft_assets.json")
    data = {"champions": {}, "items": {}}
    if os.path.exists(assets_path):
        try:
            with open(assets_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    champ_index = {}
    for raw_id, c_data in data.get("champions", {}).items():
        champ_index[raw_id] = c_data
        champ_index[raw_id.lower()] = c_data
        clean = clean_unit_name(raw_id)
        if clean:
            champ_index[clean] = c_data
            champ_index[clean.lower()] = c_data
        norm = normalize_champion_key(raw_id)
        if norm and norm not in champ_index:
            champ_index[norm] = c_data
        clean_norm = normalize_champion_key(clean)
        if clean_norm and clean_norm not in champ_index:
            champ_index[clean_norm] = c_data

    item_index = {}
    for raw_id, i_data in data.get("items", {}).items():
        item_index[raw_id] = i_data
        item_index[raw_id.lower()] = i_data
        clean = clean_item_name(raw_id)
        if clean:
            item_index[clean] = i_data
            item_index[clean.lower()] = i_data
        norm = normalize_item_key(raw_id)
        if norm and norm not in item_index:
            item_index[norm] = i_data

    data["champ_index"] = champ_index
    data["item_index"] = item_index
    return data


TFT_ASSETS = load_assets()

COST_COLORS = {
    1: "#94A3B8",  # Slate 400
    2: "#10B981",  # Emerald 500
    3: "#3B82F6",  # Blue 500
    4: "#A855F7",  # Purple 500
    5: "#F59E0B",  # Gold 500
}


def get_unit_data(unit_id: str) -> dict:
    if not unit_id or not isinstance(unit_id, str):
        return {}
    idx = TFT_ASSETS.get("champ_index", {})
    if unit_id in idx:
        return idx[unit_id]
    u_lower = unit_id.lower()
    if u_lower in idx:
        return idx[u_lower]
    clean = clean_unit_name(unit_id)
    if clean in idx:
        return idx[clean]
    if clean.lower() in idx:
        return idx[clean.lower()]
    norm = normalize_champion_key(unit_id)
    if norm in idx:
        return idx[norm]
    norm_clean = normalize_champion_key(clean)
    if norm_clean in idx:
        return idx[norm_clean]
    return {}


def get_unit_icon(unit_id: str) -> str:
    ch = get_unit_data(unit_id)
    if ch.get("icon_url"):
        return ch["icon_url"]
    clean = clean_unit_name(unit_id).replace(" ", "").replace("'", "")
    return f"https://ddragon.leagueoflegends.com/cdn/14.20.1/img/champion/{clean}.png"


def get_unit_cost(unit_id: str) -> int:
    ch = get_unit_data(unit_id)
    return ch.get("cost", 1)


def get_item_data(item_id: str) -> dict:
    if not item_id or not isinstance(item_id, str):
        return {}
    idx = TFT_ASSETS.get("item_index", {})
    if item_id in idx:
        return idx[item_id]
    i_lower = item_id.lower()
    if i_lower in idx:
        return idx[i_lower]
    clean = clean_item_name(item_id)
    if clean in idx:
        return idx[clean]
    if clean.lower() in idx:
        return idx[clean.lower()]
    norm = normalize_item_key(item_id)
    if norm in idx:
        return idx[norm]
    return {}


def get_item_icon(item_id: str) -> str:
    it = get_item_data(item_id)
    return it.get("icon_url", "")


def render_unit_avatar(unit_id: str, size: int = 36, show_name: bool = False, show_cost: bool = False) -> str:
    icon_url = get_unit_icon(unit_id)
    cost = get_unit_cost(unit_id)
    border_color = COST_COLORS.get(cost, "#94A3B8")
    name = clean_unit_name(unit_id)

    html = f'<div style="display: inline-flex; flex-direction: column; align-items: center; margin: 2px; position: relative;">'
    html += f'<div style="width: {size}px; height: {size}px; border-radius: 7px; border: 2px solid {border_color}; overflow: hidden; background: #0F172A; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">'
    html += f'<img src="{icon_url}" alt="{name}" title="{name} ({cost}-cost)" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display=\'none\'"/>'
    html += "</div>"
    if show_cost:
        html += f'<span style="position: absolute; top: -3px; right: -3px; background: {border_color}; color: #0B0F19; font-size: 0.6rem; font-weight: 700; border-radius: 3px; padding: 0 3px; line-height: 12px;">{cost}</span>'
    if show_name:
        html += f'<span style="font-size: 0.7rem; color: #CBD5E1; margin-top: 3px; max-width: {size+12}px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center;">{name}</span>'
    html += "</div>"
    return html


def render_item_icon(item_id: str, size: int = 32, show_name: bool = False) -> str:
    icon_url = get_item_icon(item_id)
    name = clean_item_name(item_id)

    html = f'<div style="display: inline-flex; flex-direction: column; align-items: center; margin: 2px;">'
    html += f'<div style="width: {size}px; height: {size}px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); overflow: hidden; background: #1E293B; box-shadow: 0 2px 5px rgba(0,0,0,0.25);">'
    html += f'<img src="{icon_url}" alt="{name}" title="{name}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display=\'none\'"/>'
    html += "</div>"
    if show_name:
        html += f'<span style="font-size: 0.7rem; color: #CBD5E1; margin-top: 2px; max-width: {size+12}px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center;">{name}</span>'
    html += "</div>"
    return html


def render_board_lineup(units_list, avatar_size: int = 32, show_names: bool = False) -> str:
    chips = [render_unit_avatar(u, size=avatar_size, show_name=show_names, show_cost=False) for u in units_list if u]
    return f'<div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">{"".join(chips)}</div>'


def connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=5432,
        dbname=os.environ.get("POSTGRES_DB", "tft_data"),
        user=os.environ.get("POSTGRES_USER", "admin"),
        password=os.environ.get("POSTGRES_PASSWORD", "muasaulamuacuachungta"),
    )


@st.cache_data(ttl=300)
def query(sql, params=()):
    with connection() as db:
        with db.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [item.name for item in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)


CUSTOM_CSS = """
<style>
/* Modern Esports Dark Theme */
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1240px;
}

/* Header Typography */
.tft-header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 4px;
}

.tft-title {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #F8FAFC;
    margin: 0;
}

.tft-badge {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #0AC8B9;
    background: rgba(10, 200, 185, 0.12);
    border: 1px solid rgba(10, 200, 185, 0.28);
    border-radius: 6px;
    padding: 3px 8px;
}

.tft-subtitle {
    font-size: 0.92rem;
    color: #94A3B8;
    margin-bottom: 1.6rem;
}

/* KPI Metric Cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 2rem;
}

.kpi-card {
    background: #131B2E;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.kpi-label {
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #94A3B8;
    margin-bottom: 6px;
}

.kpi-value {
    font-size: 1.7rem;
    font-weight: 700;
    color: #F8FAFC;
    line-height: 1.2;
    letter-spacing: -0.02em;
}

.kpi-sub {
    font-size: 0.76rem;
    color: #64748B;
    margin-top: 4px;
}

/* Tab button adjustments */
button[data-baseweb="tab"] {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    padding: 10px 20px !important;
}

/* Modern dataframe container */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

try:
    sets = query("SELECT DISTINCT set_number FROM analytics.mart_unit_ratings ORDER BY set_number DESC")
except (psycopg2.Error, KeyError):
    st.error("Rankings are unavailable. Ensure PostgreSQL is running and dbt transformations are applied.")
    st.stop()

if sets.empty:
    st.info("No recent ranked matches are available yet. Run the collector, then dbt.")
    st.stop()

with st.sidebar:
    st.markdown("### TFT Analyst")
    st.caption("Challenger meta & board statistics")
    st.divider()

    set_options = sets["set_number"].tolist()
    set_number = st.selectbox("TFT Set", set_options, index=0)

    min_samples = st.number_input(
        "Min Champion Appearances",
        min_value=1,
        value=50,
        step=25,
        help="Filter out niche champions with low sample volume.",
    )

    st.divider()
    show_raw_ids = st.checkbox(
        "Developer Mode: Show Raw IDs",
        value=False,
        help="Display original internal game IDs (e.g. DA_Lux18_Base) alongside clean names.",
    )

st.markdown(
    f"""
    <div class="tft-header">
        <h1 class="tft-title">TFT Analyst</h1>
        <span class="tft-badge">Set {set_number} Challenger</span>
    </div>
    <div class="tft-subtitle">
        VN2 High-Elo Ranked Matches &bull; Final Board Intelligence &bull; Lower Average Placement is Better
    </div>
    """,
    unsafe_allow_html=True,
)

overview = query(
    """
    SELECT count(DISTINCT match_id) AS matches,
           count(*) AS player_results,
           max(played_at) AS newest_match
    FROM analytics.stg_match_participants
    WHERE queue_id = 1100 AND set_number = %s
      AND played_at >= current_timestamp - interval '14 days'
    """,
    (set_number,),
)

matches_cnt = int(overview.at[0, "matches"]) if not overview.empty and overview.at[0, "matches"] else 0
player_cnt = int(overview.at[0, "player_results"]) if not overview.empty and overview.at[0, "player_results"] else 0
newest = overview.at[0, "newest_match"] if not overview.empty else None
newest_str = newest.strftime("%d %b %Y, %H:%M") if newest else "—"

units_count_df = query(
    "SELECT count(DISTINCT unit_id) as total_units FROM analytics.mart_unit_ratings WHERE set_number = %s",
    (set_number,),
)
total_units = int(units_count_df.at[0, "total_units"]) if not units_count_df.empty else 0

st.markdown(
    f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Ranked Matches</div>
            <div class="kpi-value">{matches_cnt:,}</div>
            <div class="kpi-sub">Last 14 days</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Player Results</div>
            <div class="kpi-value">{player_cnt:,}</div>
            <div class="kpi-sub">8 players per lobby</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Tracked Champions</div>
            <div class="kpi-value">{total_units}</div>
            <div class="kpi-sub">Active in meta dataset</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Latest Match</div>
            <div class="kpi-value" style="font-size: 1.25rem; padding-top: 5px;">{newest_str}</div>
            <div class="kpi-sub">Auto-refreshed</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Ingestion Run Progress Check
try:
    with connection() as progress_db:
        with progress_db.cursor() as progress_cursor:
            progress_cursor.execute("""
                SELECT status, jsonb_array_length(state -> 'players'),
                    (SELECT count(*) FROM jsonb_array_elements(state -> 'players') p
                     WHERE p -> 'match_ids' <> 'null'::jsonb),
                    jsonb_array_length(state -> 'processed'),
                    coalesce((state ->> 'unique_references')::integer, 0),
                    coalesce((state ->> 'saved')::integer, 0)
                FROM ingestion_runs ORDER BY started_at DESC LIMIT 1
            """)
            collection = progress_cursor.fetchone()
except (psycopg2.Error, KeyError):
    collection = None

if collection:
    status, sampled, histories, processed, references, saved = collection
    with st.expander(f"Latest data collection: {status}"):
        st.write(f"Players selected: {sampled}/350 · Histories loaded: {histories}/{sampled}")
        st.write(f"Unique matches checked: {processed}/{references or 'pending'} · New matches saved: {saved}")
        st.caption("50 players per rank, Gold through Challenger. Ratings rebuild when collection finishes.")
        st.button("Refresh collection status")


def rating_rows(data, label_column, id_column, section):
    """Clickable, paginated rankings with MetaTFT-inspired icons and details action."""
    if data.empty:
        st.info("No results match these filters.")
        return None
    pages = (len(data) + 9) // 10
    page = st.selectbox(f"{section} page", list(range(1, pages + 1)), key=f"{section}_page")
    st.caption(f"{len(data)} results · Click an entry name or Details to explore pairing synergies.")

    if section == "Comps":
        header = st.columns([1.9, 2.3, 1.2, 0.9, 0.8, 0.9])
        for column, text in zip(header, ["Composition", "Board Lineup", "Games (Play %)", "Avg place", "Top 4", "Details"]):
            column.markdown(f"**{text}**")
        for _, row in data.iloc[(page - 1) * 10:page * 10].iterrows():
            ident = str(row[id_column])
            cols = st.columns([1.9, 2.3, 1.2, 0.9, 0.8, 0.9])
            name_clicked = cols[0].button(str(row[label_column]), key=f"{section}_name_{ident}", use_container_width=True)
            board_units = row.get("most_common_board") or []
            cols[1].markdown(render_board_lineup(board_units, avatar_size=28, show_names=False), unsafe_allow_html=True)
            p_rate = (int(row['sample_count']) / max(1, matches_cnt)) * 100
            cols[2].markdown(f"<b>{int(row['sample_count']):,}</b> <span style='color: #0AC8B9; font-size: 0.8rem; font-weight: 600;'>({p_rate:.1f}%)</span>", unsafe_allow_html=True)
            avg_p = float(row['average_placement'])
            p_color = "#10B981" if avg_p < 4.0 else "#F8FAFC"
            cols[3].markdown(f'<span style="color: {p_color}; font-weight: 600;">{avg_p:.2f}</span>', unsafe_allow_html=True)
            cols[4].write(f"{float(row['top4_rate_pct']):.1f}%")
            more_clicked = cols[5].button("Details", key=f"{section}_more_{ident}")
            if name_clicked or more_clicked:
                st.session_state[f"{section}_selected"] = ident
            if show_raw_ids:
                cols[0].caption(ident)
    else:
        header = st.columns([0.6, 2.6, 1, 1, 1, 1])
        for column, text in zip(header, ["", section, "Appearances", "Avg place", "Top 4", "Details"]):
            column.markdown(f"**{text}**")
        for _, row in data.iloc[(page - 1) * 10:page * 10].iterrows():
            ident = str(row[id_column])
            cols = st.columns([0.6, 2.6, 1, 1, 1, 1])
            if section == "Champions":
                cols[0].markdown(render_unit_avatar(ident, size=36, show_cost=True), unsafe_allow_html=True)
                cost = get_unit_cost(ident)
                btn_label = f"{row[label_column]} ({cost}g)"
            else:
                cols[0].markdown(render_item_icon(ident, size=34), unsafe_allow_html=True)
                btn_label = str(row[label_column])

            name_clicked = cols[1].button(btn_label, key=f"{section}_name_{ident}", use_container_width=True)
            cols[2].write(f"{int(row['sample_count']):,}")
            avg_p = float(row['average_placement'])
            p_color = "#10B981" if avg_p < 4.0 else "#F8FAFC"
            cols[3].markdown(f'<span style="color: {p_color}; font-weight: 600;">{avg_p:.2f}</span>', unsafe_allow_html=True)
            cols[4].write(f"{float(row['top4_rate_pct']):.1f}%")
            more_clicked = cols[5].button("Details", key=f"{section}_more_{ident}")
            if name_clicked or more_clicked:
                st.session_state[f"{section}_selected"] = ident
            if show_raw_ids:
                cols[1].caption(ident)

    selected_id = st.session_state.get(f"{section}_selected")
    selected = data.loc[data[id_column].astype(str) == selected_id]
    if selected.empty:
        return None
    st.divider()
    if st.button("Close details", key=f"{section}_close"):
        st.session_state.pop(f"{section}_selected", None)
        return None
    return selected.iloc[0]


def pair_details(selected_id, kind):
    selected_column, result_column = ('unit_id', 'item_id') if kind == 'champion' else ('item_id', 'unit_id')
    pairs = query(f"""
        SELECT {result_column}, match_count, sample_count, average_placement, top4_rate_pct
        FROM analytics.mart_unit_item_ratings
        WHERE set_number = %s AND {selected_column} = %s AND match_count >= 10
        ORDER BY average_placement ASC, match_count DESC, {result_column}
    """, (set_number, selected_id))
    st.caption("At least 10 distinct matches per pairing. Only items equipped on that champion count. Lower average placement is better.")
    if pairs.empty:
        st.info("No pairings have reached 10 matches yet.")
        return

    label = 'Item' if kind == 'champion' else 'Champion'
    cleaner = clean_item_name if kind == 'champion' else clean_unit_name
    icon_getter = get_item_icon if kind == 'champion' else get_unit_icon

    pairs[label] = pairs[result_column].map(cleaner)
    pairs['Icon'] = pairs[result_column].map(icon_getter)
    pairs['average_placement'] = pairs['average_placement'].astype(float)
    pairs['top4_rate_pct'] = pairs['top4_rate_pct'].astype(float)

    st.dataframe(
        pairs[['Icon', label, 'match_count', 'sample_count', 'average_placement', 'top4_rate_pct']].rename(columns={
            'match_count': 'Matches',
            'sample_count': 'Player results',
            'average_placement': 'Avg Placement',
            'top4_rate_pct': 'Top 4 %',
        }),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Icon": st.column_config.ImageColumn("", width="small"),
            label: st.column_config.TextColumn(label, width="medium"),
            "Matches": st.column_config.NumberColumn("Matches", format="%d", width="small"),
            "Player results": st.column_config.NumberColumn("Player Results", format="%d", width="small"),
            "Avg Placement": st.column_config.NumberColumn("Avg Placement", format="%.2f", help="Lower is better", width="small"),
            "Top 4 %": st.column_config.ProgressColumn("Top 4 Rate", format="%.1f%%", min_value=0, max_value=100, width="medium"),
        }
    )


units_tab, items_tab, comps_tab = st.tabs(["Champions", "Items", "Team Compositions"])

# --- Champions Tab ---
with units_tab:
    units = query(
        """
        SELECT unit_id, sample_count, average_placement, top4_rate_pct
        FROM analytics.mart_unit_ratings
        WHERE set_number = %s AND sample_count >= %s
        ORDER BY average_placement ASC, sample_count DESC
        """,
        (set_number, min_samples),
    )

    if units.empty:
        st.info("No champions meet this sample threshold. Lower the threshold in the sidebar.")
    else:
        units["Unit"] = units["unit_id"].map(clean_unit_name)
        units["average_placement"] = units["average_placement"].astype(float)
        units["top4_rate_pct"] = units["top4_rate_pct"].astype(float)

        # Meta Top 3 Highlights Spotlight
        top_3 = units.head(3)
        spot_cols = st.columns(3)
        for idx, (_, ch_row) in enumerate(top_3.iterrows()):
            with spot_cols[idx]:
                uid = ch_row["unit_id"]
                c_name = ch_row["Unit"]
                c_cost = get_unit_cost(uid)
                b_color = COST_COLORS.get(c_cost, "#94A3B8")
                c_icon = get_unit_icon(uid)
                c_avg = ch_row["average_placement"]
                c_top4 = ch_row["top4_rate_pct"]
                st.markdown(
                    f"""
                    <div style="background: #131B2E; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                        <div style="width: 46px; height: 46px; border-radius: 8px; border: 2.5px solid {b_color}; overflow: hidden; flex-shrink: 0; background: #0F172A;">
                            <img src="{c_icon}" style="width: 100%; height: 100%; object-fit: cover;"/>
                        </div>
                        <div style="flex-grow: 1;">
                            <div style="display: flex; align-items: center; gap: 6px;">
                                <span style="font-weight: 700; font-size: 0.95rem; color: #F8FAFC;">{c_name}</span>
                                <span style="font-size: 0.68rem; font-weight: 700; background: {b_color}; color: #0B0F19; border-radius: 3px; padding: 1px 4px;">{c_cost}g</span>
                            </div>
                            <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 2px;">
                                Avg: <span style="color: #10B981; font-weight: 600;">{c_avg:.2f}</span> &bull; Top 4: <span style="color: #0AC8B9; font-weight: 600;">{c_top4:.1f}%</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        col_search, col_stats = st.columns([2, 1])
        with col_search:
            unit_search = st.text_input("Search Champion", "", placeholder="Type champion name (e.g. Lux, Ahri)...")
        with col_stats:
            top_unit = units.iloc[0]["Unit"]
            top_place = units.iloc[0]["average_placement"]
            st.caption(f"Top Performer: **{top_unit}** ({top_place:.2f} avg placement)")

        filtered_units = units
        if unit_search.strip():
            filtered_units = filtered_units[
                filtered_units["Unit"].str.contains(unit_search.strip(), case=False, na=False, regex=False)
            ]

        selected_unit = rating_rows(filtered_units, "Unit", "unit_id", "Champions")
        if selected_unit is not None:
            c_cost = get_unit_cost(selected_unit['unit_id'])
            b_color = COST_COLORS.get(c_cost, "#94A3B8")
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 12px; margin: 12px 0;">
                    <div style="width: 44px; height: 44px; border-radius: 8px; border: 2.5px solid {b_color}; overflow: hidden; background: #0F172A;">
                        <img src="{get_unit_icon(selected_unit['unit_id'])}" style="width: 100%; height: 100%; object-fit: cover;"/>
                    </div>
                    <h3 style="margin: 0; color: #F8FAFC;">Best items for {selected_unit['Unit']}</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
            pair_details(selected_unit['unit_id'], 'champion')

# --- Items Tab ---
with items_tab:
    items = query(
        """
        SELECT item_id, sample_count, average_placement, top4_rate_pct
        FROM analytics.mart_item_ratings
        WHERE set_number = %s AND sample_count >= %s
        ORDER BY average_placement ASC, sample_count DESC
        """,
        (set_number, min_samples),
    )

    if items.empty:
        st.info("No items meet this sample threshold. Lower the threshold in the sidebar.")
    else:
        items["Item"] = items["item_id"].map(clean_item_name)
        items["average_placement"] = items["average_placement"].astype(float)
        items["top4_rate_pct"] = items["top4_rate_pct"].astype(float)

        # Meta Top 3 Items Spotlight
        top_3_items = items.head(3)
        spot_i_cols = st.columns(3)
        for idx, (_, it_row) in enumerate(top_3_items.iterrows()):
            with spot_i_cols[idx]:
                iid = it_row["item_id"]
                i_name = it_row["Item"]
                i_icon = get_item_icon(iid)
                i_avg = it_row["average_placement"]
                i_top4 = it_row["top4_rate_pct"]
                st.markdown(
                    f"""
                    <div style="background: #131B2E; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);">
                        <div style="width: 42px; height: 42px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); overflow: hidden; flex-shrink: 0; background: #1E293B;">
                            <img src="{i_icon}" style="width: 100%; height: 100%; object-fit: cover;"/>
                        </div>
                        <div style="flex-grow: 1;">
                            <div style="font-weight: 700; font-size: 0.95rem; color: #F8FAFC; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px;">{i_name}</div>
                            <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 2px;">
                                Avg: <span style="color: #10B981; font-weight: 600;">{i_avg:.2f}</span> &bull; Top 4: <span style="color: #0AC8B9; font-weight: 600;">{i_top4:.1f}%</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        col_cat, col_search_item = st.columns([1, 2])
        with col_cat:
            category = st.selectbox(
                "Item Category",
                ["All", "Standard Items", "Radiant", "Artifacts", "Emblems", "Components"],
            )
        with col_search_item:
            item_search = st.text_input("Search Item", "", placeholder="Type item name (e.g. Guinsoo, Emblem)...")

        filtered_items = items
        if category == "Radiant":
            filtered_items = filtered_items[filtered_items["Item"].str.contains(r"\(Radiant\)", case=False)]
        elif category == "Artifacts":
            filtered_items = filtered_items[filtered_items["Item"].str.contains(r"\(Artifact\)", case=False)]
        elif category == "Emblems":
            filtered_items = filtered_items[filtered_items["Item"].str.contains("Emblem", case=False)]
        elif category == "Components":
            filtered_items = filtered_items[
                filtered_items["Item"].str.contains(
                    r"Sword|Vest|Belt|Rod|Cloak|Bow|Gloves|Spatula|Tear|\(Component\)", case=False
                )
            ]
        elif category == "Standard Items":
            filtered_items = filtered_items[
                ~filtered_items["Item"].str.contains(r"\(Radiant\)|\(Artifact\)|Emblem", case=False)
            ]

        if item_search.strip():
            filtered_items = filtered_items[
                filtered_items["Item"].str.contains(item_search.strip(), case=False, na=False, regex=False)
            ]

        selected_item = rating_rows(filtered_items, "Item", "item_id", "Items")
        if selected_item is not None:
            st.markdown(
                f"""
                <div style="display: flex; align-items: center; gap: 12px; margin: 12px 0;">
                    <div style="width: 40px; height: 40px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.15); overflow: hidden; background: #1E293B;">
                        <img src="{get_item_icon(selected_item['item_id'])}" style="width: 100%; height: 100%; object-fit: cover;"/>
                    </div>
                    <h3 style="margin: 0; color: #F8FAFC;">Best champions with {selected_item['Item']}</h3>
                </div>
                """,
                unsafe_allow_html=True
            )
            pair_details(selected_item['item_id'], 'item')

# --- Compositions Tab ---
with comps_tab:
    min_1pct_matches = max(1, int(round(matches_cnt * 0.01)))
    st.caption(
        f"Meta compositions appearing in at least 1% of total matches (>= {min_1pct_matches} of {matches_cnt:,} games). "
        "Grouped by key carry champions and primary traits. Lower average placement is better."
    )

    col_comp_samples, col_comp_search = st.columns([1.2, 2])
    with col_comp_samples:
        comp_min_samples = st.number_input(
            f"Min Appearances (>= 1% = {min_1pct_matches} games)",
            min_value=min_1pct_matches,
            value=min_1pct_matches,
            step=1,
            help=f"Limited to compositions appearing in at least 1% of total recorded matches ({min_1pct_matches} of {matches_cnt:,} games).",
        )
    with col_comp_search:
        comp_search = st.text_input(
            "Search Comp",
            "",
            placeholder="Search carries, trait, flex, or reroll...",
        )

    comps = query(
        """
        SELECT comp_id, comp_name, sample_count, average_placement, top4_rate_pct,
               most_common_board, board_sample_count, board_share_pct, example_board
        FROM analytics.mart_comp_ratings
        WHERE set_number = %s AND sample_count >= %s
        ORDER BY average_placement ASC, sample_count DESC
        """,
        (set_number, comp_min_samples),
    )

    if comps.empty:
        st.info("No comps meet this sample threshold. Lower it to see more comps.")
    else:
        comps["average_placement"] = comps["average_placement"].astype(float)
        comps["top4_rate_pct"] = comps["top4_rate_pct"].astype(float)

        filtered_comps = comps
        if comp_search.strip():
            filtered_comps = filtered_comps[
                filtered_comps["comp_name"].str.contains(comp_search.strip(), case=False, na=False, regex=False)
            ]

        selected = rating_rows(filtered_comps, "comp_name", "comp_id", "Comps")
        if selected is not None:
            p_rate = (int(selected['sample_count']) / max(1, matches_cnt)) * 100
            st.markdown(f"### {selected['comp_name']}")
            st.markdown(
                f"<div style='font-size: 0.9rem; color: #94A3B8; margin-bottom: 12px; display: flex; gap: 16px; flex-wrap: wrap;'>"
                f"<span>Play Rate: <b style='color: #0AC8B9;'>{p_rate:.1f}%</b> ({int(selected['sample_count']):,} games)</span>"
                f"<span>Avg Placement: <b style='color: #10B981;'>{float(selected['average_placement']):.2f}</b></span>"
                f"<span>Top 4 Rate: <b style='color: #F8FAFC;'>{float(selected['top4_rate_pct']):.1f}%</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Most Common End Board (Visual Lineup with Champion Avatars & Cost Borders)
            st.markdown("**Most Common End Board**")
            board_units = selected["most_common_board"] or []
            st.markdown(
                f"""
                <div style="background: #131B2E; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                    {render_board_lineup(board_units, avatar_size=46, show_names=True)}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                f"This lineup appeared in {selected['board_sample_count']} of {selected['sample_count']} "
                f"comp results ({float(selected['board_share_pct']):.1f}%). Below is its latest recorded match example."
            )

            # Example Board with Champions, Stars & Equipped Items (MetaTFT Style)
            st.markdown("**Example Match Itemization**")
            example_units = selected["example_board"] or []
            unit_cards_html = []
            for unit in example_units:
                u_id = unit.get("character_id") or unit.get("name", "")
                name = clean_unit_name(u_id)
                stars = unit.get("tier", 1)
                cost = get_unit_cost(u_id)
                border_color = COST_COLORS.get(cost, "#94A3B8")
                star_str = "★" * stars
                u_icon = get_unit_icon(u_id)

                raw_items = unit.get("itemNames") or unit.get("items") or []
                item_imgs = []
                for itm in raw_items:
                    itm_id = str(itm)
                    itm_icon = get_item_icon(itm_id)
                    itm_name = clean_item_name(itm_id)
                    if itm_icon:
                        item_imgs.append(f'<img src="{itm_icon}" alt="{itm_name}" title="{itm_name}" style="width: 22px; height: 22px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.2);"/>')
                items_html = f'<div style="display: flex; gap: 3px; margin-top: 6px; min-height: 24px;">{"".join(item_imgs)}</div>'

                unit_card = f"""
                <div style="display: flex; flex-direction: column; align-items: center; background: #0B0F19; border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 10px 8px; min-width: 80px;">
                    <span style="color: #F59E0B; font-size: 0.72rem; font-weight: 700; margin-bottom: 2px;">{star_str}</span>
                    <div style="width: 44px; height: 44px; border-radius: 8px; border: 2.5px solid {border_color}; overflow: hidden; background: #0F172A; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
                        <img src="{u_icon}" alt="{name}" title="{name} ({cost}-cost)" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'"/>
                    </div>
                    <span style="font-size: 0.75rem; color: #F8FAFC; margin-top: 4px; font-weight: 600; text-align: center; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{name}</span>
                    {items_html}
                </div>
                """
                unit_cards_html.append(unit_card)

            st.markdown(
                f"""
                <div style="display: flex; gap: 10px; flex-wrap: wrap; background: #131B2E; border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 16px; margin-bottom: 16px;">
                    {"".join(unit_cards_html)}
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("<br>", unsafe_allow_html=True)
st.caption("Insights generated from post-match game data. Values represent associations from final boards, not causal impact.")
