"""TFT Analyst: Ranked Challenger analytics and meta statistics."""

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

units_tab, items_tab, comps_tab = st.tabs(["Champions", "Items", "Team Compositions"])

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
                filtered_units["Unit"].str.contains(unit_search.strip(), case=False, na=False)
            ]

        display_cols = ["Unit", "sample_count", "average_placement", "top4_rate_pct"]
        col_rename = {
            "sample_count": "Appearances",
            "average_placement": "Avg Placement",
            "top4_rate_pct": "Top 4 %",
        }
        if show_raw_ids:
            display_cols.append("unit_id")
            col_rename["unit_id"] = "Raw Game ID"

        st.dataframe(
            filtered_units[display_cols].rename(columns=col_rename),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Unit": st.column_config.TextColumn("Champion", width="medium"),
                "Appearances": st.column_config.NumberColumn("Appearances", format="%d", width="small"),
                "Avg Placement": st.column_config.NumberColumn(
                    "Avg Placement",
                    help="Lower is better (1.0 = 1st place)",
                    format="%.2f",
                    width="small",
                ),
                "Top 4 %": st.column_config.ProgressColumn(
                    "Top 4 Rate",
                    help="Percentage of games finishing in top 4",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                    width="medium",
                ),
            },
        )

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
                filtered_items["Item"].str.contains(item_search.strip(), case=False, na=False)
            ]

        display_cols = ["Item", "sample_count", "average_placement", "top4_rate_pct"]
        col_rename = {
            "sample_count": "Appearances",
            "average_placement": "Avg Placement",
            "top4_rate_pct": "Top 4 %",
        }
        if show_raw_ids:
            display_cols.append("item_id")
            col_rename["item_id"] = "Raw Game ID"

        st.dataframe(
            filtered_items[display_cols].rename(columns=col_rename),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Item": st.column_config.TextColumn("Item Name", width="medium"),
                "Appearances": st.column_config.NumberColumn("Appearances", format="%d", width="small"),
                "Avg Placement": st.column_config.NumberColumn(
                    "Avg Placement",
                    help="Lower is better",
                    format="%.2f",
                    width="small",
                ),
                "Top 4 %": st.column_config.ProgressColumn(
                    "Top 4 Rate",
                    help="Percentage of games finishing in top 4",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                    width="medium",
                ),
            },
        )

with comps_tab:
    st.caption("Exact final-board compositions. Minor unit changes create separate compositions.")

    col_comp_samples, col_comp_search = st.columns([1, 2])
    with col_comp_samples:
        comp_min_samples = st.number_input(
            "Min Comp Appearances",
            min_value=1,
            value=3,
            step=1,
            help="Minimum times this exact unit lineup appeared in ranked matches.",
        )
    with col_comp_search:
        comp_search = st.text_input(
            "Filter by Champion in Comp",
            "",
            placeholder="Type champion name (e.g. Lux, Ashe) to see boards running them...",
        )

    comps = query(
        """
        SELECT comp_units, sample_count, average_placement, top4_rate_pct
        FROM analytics.mart_comp_ratings
        WHERE set_number = %s AND sample_count >= %s
        ORDER BY average_placement ASC, sample_count DESC
        """,
        (set_number, comp_min_samples),
    )

    if comps.empty:
        st.info("No exact compositions meet this sample threshold. Lower it to discover recurring team boards.")
    else:
        comps["Clean Board"] = comps["comp_units"].map(clean_comp_units)
        comps["average_placement"] = comps["average_placement"].astype(float)
        comps["top4_rate_pct"] = comps["top4_rate_pct"].astype(float)

        filtered_comps = comps
        if comp_search.strip():
            filtered_comps = filtered_comps[
                filtered_comps["Clean Board"].str.contains(comp_search.strip(), case=False, na=False)
            ]

        display_cols = ["Clean Board", "sample_count", "average_placement", "top4_rate_pct"]
        col_rename = {
            "Clean Board": "Final Board Lineup",
            "sample_count": "Appearances",
            "average_placement": "Avg Placement",
            "top4_rate_pct": "Top 4 %",
        }
        if show_raw_ids:
            display_cols.append("comp_units")
            col_rename["comp_units"] = "Raw Board String"

        st.dataframe(
            filtered_comps[display_cols].rename(columns=col_rename),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Final Board Lineup": st.column_config.TextColumn(
                    "Final Board (Clean Champions)",
                    width="large",
                    help="Clean champion names making up this final board composition.",
                ),
                "Appearances": st.column_config.NumberColumn("Appearances", format="%d", width="small"),
                "Avg Placement": st.column_config.NumberColumn(
                    "Avg Placement",
                    help="Lower is better (1.0 = 1st place)",
                    format="%.2f",
                    width="small",
                ),
                "Top 4 %": st.column_config.ProgressColumn(
                    "Top 4 Rate",
                    format="%.1f%%",
                    min_value=0,
                    max_value=100,
                    width="medium",
                ),
            },
        )

st.markdown("<br>", unsafe_allow_html=True)
st.caption("Insights generated from post-match game data. Values represent associations from final boards, not causal impact.")
