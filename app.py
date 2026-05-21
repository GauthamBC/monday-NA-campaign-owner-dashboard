from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# Config
# ============================================================

MONDAY_API_URL = "https://api.monday.com/v2"
DEFAULT_API_VERSION = "2025-04"
PAGE_LIMIT = 500
APP_TIMEZONE = "Europe/London"

DEFAULT_BOARD_IDS = [
    "6727663754",  # Vegas Insider
    "6727665427",  # Action Network
    "7101616385",  # Canada Sports Betting
    "7077539299",  # Roto Grinders
]

DEFAULT_BOARD_BRANDS = {
    "6727663754": "VegasInsider",
    "6727665427": "Action Network",
    "7101616385": "Canada Sports Betting",
    "7077539299": "RotoGrinders",
}

BRAND_COLOURS = {
    "action network": {"bg": "#EAFBF2", "text": "#087443", "border": "#B7E5CC"},
    "vegasinsider": {"bg": "#FFF7DA", "text": "#8A6300", "border": "#F2C23A"},
    "vegas insider": {"bg": "#FFF7DA", "text": "#8A6300", "border": "#F2C23A"},
    "canada sports betting": {"bg": "#FFF0F1", "text": "#B90719", "border": "#EF0D23"},
    "ca sports betting": {"bg": "#FFF0F1", "text": "#B90719", "border": "#EF0D23"},
    "csb": {"bg": "#FFF0F1", "text": "#B90719", "border": "#EF0D23"},
    "rotogrinders": {"bg": "#EFF8FF", "text": "#075985", "border": "#BAE6FD"},
    "roto grinders": {"bg": "#EFF8FF", "text": "#075985", "border": "#BAE6FD"},
}

STATUS_COLOURS = {
    "done": {"bg": "#ECFDF5", "text": "#047857", "border": "#A7F3D0"},
    "working on it": {"bg": "#EFF6FF", "text": "#1D4ED8", "border": "#BFDBFE"},
    "outreach in progress": {"bg": "#F5F3FF", "text": "#6D28D9", "border": "#DDD6FE"},
    "commissioned": {"bg": "#FEF3C7", "text": "#A16207", "border": "#FDE68A"},
    "live on site": {"bg": "#ECFEFF", "text": "#0E7490", "border": "#A5F3FC"},
}

COLUMN_ALIASES = {
    "owner": ["owner", "owners", "person", "people", "assigned", "assignee", "lead", "campaign owner"],
    "date": ["date", "due", "deadline", "key date", "publish", "publication", "launch", "live date", "outreach date"],
    "status": ["status", "campaign status", "progress", "state"],
    "stage": ["stage", "phase", "workflow", "step", "campaign stage", "category"],
    "priority": ["priority", "urgency"],
    "brand": ["brand", "site", "property", "vertical"],
}


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="Campaign Owner Dashboard",
    page_icon="📌",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 3rem;
            max-width: 1320px;
        }

        .hero {
            background: linear-gradient(135deg, #020617 0%, #111827 52%, #1e293b 100%);
            color: white;
            padding: 30px 32px;
            border-radius: 28px;
            box-shadow: 0 22px 60px rgba(15, 23, 42, 0.22);
            border: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 22px;
        }

        .hero-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 12px;
            border-radius: 999px;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.12);
            color: #e2e8f0;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.02em;
            margin-bottom: 16px;
        }

        .hero-title {
            font-size: clamp(32px, 5vw, 52px);
            line-height: 1.02;
            font-weight: 850;
            letter-spacing: -0.055em;
            margin: 0;
        }

        .hero-copy {
            margin-top: 13px;
            max-width: 820px;
            color: #cbd5e1;
            font-size: 16px;
            line-height: 1.65;
        }

        .people-panel {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 28px;
            padding: 18px;
            box-shadow: 0 10px 34px rgba(15, 23, 42, 0.06);
            position: sticky;
            top: 18px;
        }

        .panel-kicker {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: #94a3b8;
            font-weight: 850;
            font-size: 11px;
            margin-bottom: 4px;
        }

        .panel-title {
            font-size: 22px;
            font-weight: 850;
            letter-spacing: -0.04em;
            color: #020617;
            margin-bottom: 4px;
        }

        .panel-copy {
            font-size: 13px;
            color: #64748b;
            line-height: 1.5;
            margin-bottom: 14px;
        }

        .section-kicker {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            color: #94a3b8;
            font-weight: 850;
            font-size: 12px;
            margin-bottom: 4px;
        }

        .section-title {
            font-size: 30px;
            font-weight: 850;
            letter-spacing: -0.045em;
            color: #020617;
            margin: 0 0 6px;
        }

        .section-sub {
            color: #64748b;
            font-size: 14px;
            margin-bottom: 18px;
        }

        .owner-block {
            background: rgba(255,255,255,0.72);
            border: 1px solid #e2e8f0;
            border-radius: 28px;
            padding: 18px;
            margin-bottom: 18px;
            box-shadow: 0 10px 34px rgba(15, 23, 42, 0.05);
        }

        .owner-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 14px;
        }

        .owner-name {
            font-size: 19px;
            font-weight: 850;
            letter-spacing: -0.03em;
            color: #020617;
            margin: 0;
        }

        .owner-sub {
            color: #64748b;
            font-size: 13px;
            margin-top: 3px;
        }

        .count-pill {
            background: #020617;
            color: white;
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 13px;
            font-weight: 850;
            white-space: nowrap;
        }

        .campaign-card {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 24px;
            padding: 18px;
            margin-bottom: 14px;
            box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06);
        }

        .campaign-card:hover {
            transform: translateY(-1px);
            transition: 0.18s ease;
            box-shadow: 0 14px 36px rgba(15, 23, 42, 0.09);
        }

        .badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 850;
            border: 1px solid transparent;
            line-height: 1;
        }

        .campaign-title {
            font-size: 18px;
            font-weight: 850;
            letter-spacing: -0.025em;
            color: #020617;
            margin-bottom: 8px;
        }

        .campaign-note {
            color: #64748b;
            font-size: 13px;
            line-height: 1.55;
            margin-bottom: 14px;
        }

        .mini-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            background: #f8fafc;
            border-radius: 18px;
            padding: 12px;
        }

        .mini-label {
            color: #94a3b8;
            font-size: 11px;
            font-weight: 750;
            margin-bottom: 3px;
        }

        .mini-value {
            color: #334155;
            font-size: 13px;
            font-weight: 850;
            word-break: break-word;
        }

        div[data-testid="stSidebar"] {
            border-right: 1px solid #e2e8f0;
        }

        div.stButton > button {
            border-radius: 16px;
            min-height: 46px;
            font-weight: 800;
            border: 1px solid #e2e8f0;
            text-align: left;
            justify-content: flex-start;
        }

        @media (max-width: 900px) {
            .hero { padding: 24px; border-radius: 24px; }
            .mini-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .people-panel { position: static; }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Helpers
# ============================================================

def get_secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def get_monday_api_key() -> str:
    top_level = str(get_secret("MONDAY_API_KEY", "") or "").strip()
    if top_level:
        return top_level

    try:
        return str(st.secrets["monday"]["monday_api_token"] or "").strip()
    except Exception:
        return ""


def to_clean_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[\n,]+", value) if part.strip()]
    if isinstance(value, Iterable):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def normalise(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def clean_brand_name(value: str) -> str:
    text = str(value or "").strip()
    lower = normalise(text)

    if "vegas" in lower:
        return "VegasInsider"
    if "action" in lower:
        return "Action Network"
    if "canada" in lower or "ca sports" in lower or lower == "csb":
        return "Canada Sports Betting"
    if "roto" in lower:
        return "RotoGrinders"

    replacements = {
        "Vegas Insider": "VegasInsider",
        "VegasInsider": "VegasInsider",
        "Action Network": "Action Network",
        "Canada Sports Betting": "Canada Sports Betting",
        "CA Sports Betting": "Canada Sports Betting",
        "CSB": "Canada Sports Betting",
        "Roto Grinders": "RotoGrinders",
        "RotoGrinders": "RotoGrinders",
    }

    return replacements.get(text, text)


def split_people(text: Any) -> List[str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ["Unassigned"]

    people = [p.strip() for p in re.split(r",|;|\||\n", cleaned) if p.strip()]
    return people or [cleaned]


def london_today() -> date:
    return datetime.now(ZoneInfo(APP_TIMEZONE)).date()


def month_range(year: int, month: int) -> Tuple[date, date]:
    start = date(year, month, 1)

    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    end = next_month_start - timedelta(days=1)
    return start, end


def period_range(period: str, custom_start: Optional[date] = None, custom_end: Optional[date] = None) -> Tuple[date, date]:
    today = london_today()
    start_this_week = today - timedelta(days=today.weekday())

    if period == "This Week":
        return start_this_week, start_this_week + timedelta(days=6)

    if period == "Next Week":
        return start_this_week + timedelta(days=7), start_this_week + timedelta(days=13)

    if period == "This Month":
        return month_range(today.year, today.month)

    if period == "Next Month":
        next_month_seed = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        return month_range(next_month_seed.year, next_month_seed.month)

    if custom_start and custom_end:
        return min(custom_start, custom_end), max(custom_start, custom_end)

    return start_this_week, start_this_week + timedelta(days=6)


def parse_monday_date(text: Any, raw_value: Any = None) -> Optional[date]:
    candidates: List[str] = []

    if text:
        candidates.append(str(text))

    if raw_value:
        try:
            parsed_value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
            if isinstance(parsed_value, dict):
                for key in ["date", "from", "to"]:
                    if parsed_value.get(key):
                        candidates.append(str(parsed_value[key]))
        except Exception:
            pass

    for candidate in candidates:
        parsed = pd.to_datetime(candidate, errors="coerce", dayfirst=False)
        if not pd.isna(parsed):
            return parsed.date()

    return None


def format_display_date(value: Optional[date]) -> str:
    if value is None or pd.isna(value):
        return "No date"

    return value.strftime("%a %d %b")


def style_for_brand(brand: str) -> Dict[str, str]:
    return BRAND_COLOURS.get(
        normalise(brand),
        {"bg": "#F1F5F9", "text": "#334155", "border": "#CBD5E1"},
    )


def style_for_status(status: str) -> Dict[str, str]:
    return STATUS_COLOURS.get(
        normalise(status),
        {"bg": "#F8FAFC", "text": "#475569", "border": "#CBD5E1"},
    )


def badge(label: str, colours: Dict[str, str]) -> str:
    safe = html.escape(str(label or "—"))

    return (
        f'<span class="badge" style="background:{colours["bg"]}; '
        f'color:{colours["text"]}; border-color:{colours["border"]};">{safe}</span>'
    )


def campaign_card_html(row: pd.Series) -> str:
    brand_colours = style_for_brand(row.get("brand", ""))
    status_colours = style_for_status(row.get("status", ""))

    return f"""
<div class="campaign-card">
  <div class="badge-row">
    {badge(row.get("brand", "—"), brand_colours)}
    {badge(str(row.get("status", "—")), status_colours)}
    {badge(str(row.get("key_date_display", "No date")), {"bg": "#F8FAFC", "text": "#334155", "border": "#CBD5E1"})}
  </div>

  <div class="campaign-title">{html.escape(str(row.get("campaign", "Untitled campaign")))}</div>

  <div class="campaign-note">
    Board: {html.escape(str(row.get("board_name", "—")))}
    · Group: {html.escape(str(row.get("group", "—")))}
  </div>

  <div class="mini-grid">
    <div>
      <div class="mini-label">Owner</div>
      <div class="mini-value">{html.escape(str(row.get("owners_display", "—")))}</div>
    </div>
    <div>
      <div class="mini-label">Category</div>
      <div class="mini-value">{html.escape(str(row.get("stage", "—")))}</div>
    </div>
    <div>
      <div class="mini-label">Status</div>
      <div class="mini-value">{html.escape(str(row.get("status", "—")))}</div>
    </div>
    <div>
      <div class="mini-label">Date</div>
      <div class="mini-value">{html.escape(str(row.get("key_date_display", "No date")))}</div>
    </div>
  </div>
</div>
""".strip()


# ============================================================
# Monday API
# ============================================================

BOARD_ITEMS_QUERY = """
query ($board_ids: [ID!], $limit: Int!) {
  boards(ids: $board_ids) {
    id
    name
    columns {
      id
      title
      type
    }
    items_page(limit: $limit) {
      cursor
      items {
        id
        name
        group {
          id
          title
        }
        column_values {
          id
          text
          value
          type
        }
      }
    }
  }
}
"""

NEXT_ITEMS_PAGE_QUERY = """
query ($cursor: String!, $limit: Int!) {
  next_items_page(cursor: $cursor, limit: $limit) {
    cursor
    items {
      id
      name
      group {
        id
        title
      }
      column_values {
        id
        text
        value
        type
      }
    }
  }
}
"""

LIST_BOARDS_QUERY = """
query {
  boards(limit: 100) {
    id
    name
  }
}
"""


def monday_graphql(
    api_key: str,
    api_version: str,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
        "API-Version": api_version,
    }

    response = requests.post(
        MONDAY_API_URL,
        headers=headers,
        json={"query": query, "variables": variables or {}},
        timeout=45,
    )

    if response.status_code != 200:
        raise RuntimeError(f"Monday API HTTP {response.status_code}: {response.text[:800]}")

    body = response.json()

    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"], indent=2))

    return body.get("data", {})


@st.cache_data(ttl=300, show_spinner=False)
def list_boards(api_key: str, api_version: str) -> pd.DataFrame:
    data = monday_graphql(api_key, api_version, LIST_BOARDS_QUERY)
    return pd.DataFrame(data.get("boards", []))


@st.cache_data(ttl=300, show_spinner=False)
def fetch_monday_boards(api_key: str, api_version: str, board_ids: Tuple[str, ...]) -> List[Dict[str, Any]]:
    boards: List[Dict[str, Any]] = []

    for board_id in board_ids:
        data = monday_graphql(
            api_key,
            api_version,
            BOARD_ITEMS_QUERY,
            {"board_ids": [str(board_id)], "limit": PAGE_LIMIT},
        )

        board_list = data.get("boards", [])
        if not board_list:
            continue

        board = board_list[0]
        items_page = board.get("items_page") or {}
        all_items = list(items_page.get("items") or [])
        cursor = items_page.get("cursor")

        while cursor:
            next_data = monday_graphql(
                api_key,
                api_version,
                NEXT_ITEMS_PAGE_QUERY,
                {"cursor": cursor, "limit": PAGE_LIMIT},
            )
            next_page = next_data.get("next_items_page") or {}
            all_items.extend(next_page.get("items") or [])
            cursor = next_page.get("cursor")

        board["items"] = all_items
        boards.append(board)

    return boards


# ============================================================
# Monday transform
# ============================================================

def find_column_id(
    columns: List[Dict[str, Any]],
    explicit_id: Optional[str],
    aliases: List[str],
    fallback_types: Optional[List[str]] = None,
) -> Optional[str]:
    explicit_id = str(explicit_id or "").strip()

    if explicit_id:
        return explicit_id

    alias_set = {normalise(alias) for alias in aliases}

    for col in columns:
        title = normalise(col.get("title"))
        if title in alias_set:
            return str(col.get("id"))

    for col in columns:
        title = normalise(col.get("title"))
        if any(alias in title for alias in alias_set):
            return str(col.get("id"))

    if fallback_types:
        type_set = {normalise(t) for t in fallback_types}
        for col in columns:
            if normalise(col.get("type")) in type_set:
                return str(col.get("id"))

    return None


def get_column_value(item: Dict[str, Any], column_id: Optional[str]) -> Tuple[str, Any, str]:
    if not column_id:
        return "", None, ""

    for col in item.get("column_values", []) or []:
        if str(col.get("id")) == str(column_id):
            return col.get("text") or "", col.get("value"), col.get("type") or ""

    return "", None, ""


def get_board_brand_map() -> Dict[str, str]:
    mapping = dict(DEFAULT_BOARD_BRANDS)
    raw = get_secret("BOARD_BRANDS", {}) or {}

    try:
        mapping.update({str(k): clean_brand_name(str(v)) for k, v in dict(raw).items()})
    except Exception:
        pass

    return mapping


def build_rows(
    boards: List[Dict[str, Any]],
    board_brand_map: Dict[str, str],
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    column_debug: List[Dict[str, Any]] = []
    mapping_debug: List[Dict[str, Any]] = []

    explicit_owner_id = get_secret("OWNER_COLUMN_ID", "")
    explicit_date_id = get_secret("DATE_COLUMN_ID", "")
    explicit_status_id = get_secret("STATUS_COLUMN_ID", "")
    explicit_stage_id = get_secret("STAGE_COLUMN_ID", "")
    explicit_priority_id = get_secret("PRIORITY_COLUMN_ID", "")
    explicit_brand_id = get_secret("BRAND_COLUMN_ID", "")

    for board in boards:
        board_id = str(board.get("id", ""))
        board_name = str(board.get("name", "Untitled board"))
        columns = board.get("columns", []) or []

        for col in columns:
            column_debug.append(
                {
                    "board_id": board_id,
                    "board_name": board_name,
                    "column_id": col.get("id"),
                    "column_title": col.get("title"),
                    "column_type": col.get("type"),
                }
            )

        owner_col = find_column_id(columns, explicit_owner_id, COLUMN_ALIASES["owner"], ["people", "person"])
        date_col = find_column_id(columns, explicit_date_id, COLUMN_ALIASES["date"], ["date", "timeline"])
        status_col = find_column_id(columns, explicit_status_id, COLUMN_ALIASES["status"], ["status"])
        stage_col = find_column_id(columns, explicit_stage_id, COLUMN_ALIASES["stage"], ["dropdown", "status"])
        priority_col = find_column_id(columns, explicit_priority_id, COLUMN_ALIASES["priority"], ["status", "dropdown"])
        brand_col = find_column_id(columns, explicit_brand_id, COLUMN_ALIASES["brand"], ["dropdown", "status"])

        mapping_debug.append(
            {
                "board_id": board_id,
                "board_name": board_name,
                "owner_column_id": owner_col,
                "date_column_id": date_col,
                "status_column_id": status_col,
                "stage_column_id": stage_col,
                "priority_column_id": priority_col,
                "brand_column_id": brand_col,
                "brand_fallback": board_brand_map.get(board_id, board_name),
            }
        )

        for item in board.get("items", []) or []:
            owner_text, _, _ = get_column_value(item, owner_col)
            date_text, date_raw, _ = get_column_value(item, date_col)
            status_text, _, _ = get_column_value(item, status_col)
            stage_text, _, _ = get_column_value(item, stage_col)
            priority_text, _, _ = get_column_value(item, priority_col)
            brand_text, _, _ = get_column_value(item, brand_col)

            owners = split_people(owner_text)
            parsed_date = parse_monday_date(date_text, date_raw)
            brand = clean_brand_name(brand_text or board_brand_map.get(board_id) or board_name)

            rows.append(
                {
                    "board_id": board_id,
                    "board_name": board_name,
                    "group": (item.get("group") or {}).get("title") or "—",
                    "item_id": str(item.get("id", "")),
                    "campaign": item.get("name") or "Untitled campaign",
                    "brand": brand,
                    "owners": owners,
                    "owners_display": ", ".join(owners),
                    "key_date": parsed_date,
                    "key_date_display": format_display_date(parsed_date),
                    "date_raw_text": date_text,
                    "status": status_text or "—",
                    "stage": stage_text or "—",
                    "priority": priority_text or "—",
                }
            )

    df = pd.DataFrame(rows)
    col_df = pd.DataFrame(column_debug)
    map_df = pd.DataFrame(mapping_debug)

    if not df.empty:
        df["sort_date"] = pd.to_datetime(df["key_date"], errors="coerce")
        df = df.sort_values(["sort_date", "brand", "campaign"], na_position="last")

    return df, col_df, map_df


def owner_universe(df: pd.DataFrame) -> List[str]:
    if df.empty or "owners" not in df.columns:
        return []

    owners: List[str] = []

    for values in df["owners"]:
        owners.extend(values if isinstance(values, list) else split_people(values))

    return sorted(set(owners))


def apply_base_filters(
    df: pd.DataFrame,
    start_date: date,
    end_date: date,
    brand: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    filtered = df.copy()

    filtered = filtered[
        filtered["key_date"].apply(
            lambda d: d is not None and not pd.isna(d) and start_date <= d <= end_date
        )
    ]

    if brand != "All":
        filtered = filtered[filtered["brand"] == brand]

    return filtered.sort_values(["sort_date", "brand", "campaign"], na_position="last")


def apply_person_filter(df: pd.DataFrame, person: str) -> pd.DataFrame:
    if df.empty:
        return df

    if person == "All":
        return df

    return df[df["owners"].apply(lambda vals: person in vals)]


def owner_counts(df: pd.DataFrame) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for _, row in df.iterrows():
        owners = row.get("owners", [])
        if not isinstance(owners, list):
            owners = split_people(owners)

        for owner in owners:
            counts[owner] = counts.get(owner, 0) + 1

    return counts


def safe_button_key(prefix: str, value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")
    return f"{prefix}_{cleaned or 'blank'}"


# ============================================================
# App
# ============================================================

st.markdown(
    """
    <div class="hero">
        <div class="hero-pill">📌 Monday.com live dashboard</div>
        <h1 class="hero-title">Campaign Owner Dashboard</h1>
        <div class="hero-copy">
            Click a person on the left to see their assigned campaigns across Action Network, VegasInsider,
            Canada Sports Betting and RotoGrinders.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

api_key = get_monday_api_key()
api_version = str(get_secret("MONDAY_API_VERSION", DEFAULT_API_VERSION) or DEFAULT_API_VERSION).strip()
secret_board_ids = to_clean_list(get_secret("MONDAY_BOARD_IDS", [])) or DEFAULT_BOARD_IDS

with st.sidebar:
    st.header("Filters")

    period_filter = st.selectbox(
        "Date range",
        ["This Week", "Next Week", "This Month", "Next Month", "Custom"],
        index=0,
    )

    brand_filter = st.selectbox(
        "Brand",
        ["All", "Action Network", "VegasInsider", "Canada Sports Betting", "RotoGrinders"],
        index=0,
    )

    custom_start: Optional[date] = None
    custom_end: Optional[date] = None

    if period_filter == "Custom":
        today = london_today()
        default_start = today - timedelta(days=today.weekday())
        default_end = default_start + timedelta(days=6)

        custom_value = st.date_input(
            "Custom range",
            value=(default_start, default_end),
            format="DD/MM/YYYY",
        )

        if isinstance(custom_value, tuple) and len(custom_value) == 2:
            custom_start, custom_end = custom_value
        elif isinstance(custom_value, date):
            custom_start = custom_value
            custom_end = custom_value

    selected_start, selected_end = period_range(period_filter, custom_start, custom_end)

    with st.expander("Setup", expanded=False):
        if api_key:
            st.success("Monday API key loaded")
        else:
            st.error("Missing Monday API key")

        st.caption(f"API version: `{api_version}`")

        board_ids_text = st.text_area(
            "Board IDs",
            value="\n".join(secret_board_ids),
            help="Use one board ID per line. These can also sit in MONDAY_BOARD_IDS inside Streamlit secrets.",
            height=105,
        )

        board_ids = tuple(to_clean_list(board_ids_text))

        if st.button("Refresh Monday data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

if not api_key:
    st.info("Add your Monday API token to Streamlit secrets, then rerun the app.")
    st.code(
        """
# Preferred new format:
MONDAY_API_KEY = "your_monday_api_token_here"

# Your old format is also supported:
[monday]
monday_api_token = "your_monday_api_token_here"
        """.strip(),
        language="toml",
    )
    st.stop()

if not board_ids:
    st.warning("Add at least one Monday board ID to continue.")

    with st.expander("Find available board IDs", expanded=True):
        try:
            boards_df = list_boards(api_key, api_version)
            if boards_df.empty:
                st.info("No boards were returned for this token.")
            else:
                st.dataframe(boards_df, use_container_width=True, hide_index=True)
                st.caption("Copy the board IDs you need into the sidebar or MONDAY_BOARD_IDS in secrets.")
        except Exception as exc:
            st.error("Could not list boards with this API key.")
            st.code(str(exc))

    st.stop()

try:
    with st.spinner("Pulling campaign data from Monday.com..."):
        monday_boards = fetch_monday_boards(api_key, api_version, board_ids)
        campaigns_df, columns_df, mapping_df = build_rows(monday_boards, get_board_brand_map())
except Exception as exc:
    st.error("Could not fetch Monday data.")
    st.code(str(exc))
    st.stop()

if campaigns_df.empty:
    st.warning("The selected board IDs were found, but no items were returned.")
    with st.expander("Column Debug"):
        st.dataframe(columns_df, use_container_width=True, hide_index=True)
    st.stop()

base_filtered_df = apply_base_filters(
    campaigns_df,
    start_date=selected_start,
    end_date=selected_end,
    brand=brand_filter,
)

counts = owner_counts(base_filtered_df)
people = sorted(counts.keys())

if "selected_owner" not in st.session_state:
    st.session_state.selected_owner = "All"

valid_people = ["All"] + people

if st.session_state.selected_owner not in valid_people:
    st.session_state.selected_owner = "All"

selected_owner = st.session_state.selected_owner
filtered_df = apply_person_filter(base_filtered_df, selected_owner)

left_col, right_col = st.columns([1, 2.25], gap="large")

with left_col:
    st.markdown(
        f"""
        <div class="people-panel">
            <div class="panel-kicker">People</div>
            <div class="panel-title">Assigned owners</div>
            <div class="panel-copy">
                {html.escape(period_filter)} · {selected_start.strftime('%d %b')}–{selected_end.strftime('%d %b')}<br>
                {html.escape(brand_filter)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    all_label = f"{'✅ ' if selected_owner == 'All' else ''}All Campaigns · {len(base_filtered_df)}"

    if st.button(
        all_label,
        key="person_all",
        use_container_width=True,
        type="primary" if selected_owner == "All" else "secondary",
    ):
        st.session_state.selected_owner = "All"
        st.rerun()

    if not people:
        st.info("No assigned people found for the selected range/brand.")
    else:
        for person in people:
            count = counts.get(person, 0)
            label = f"{'✅ ' if selected_owner == person else ''}{person} · {count}"

            if st.button(
                label,
                key=safe_button_key("person", person),
                use_container_width=True,
                type="primary" if selected_owner == person else "secondary",
            ):
                st.session_state.selected_owner = person
                st.rerun()

with right_col:
    st.markdown(
        f"""
        <div class="section-kicker">Current view</div>
        <div class="section-title">
            {html.escape(selected_owner)}
        </div>
        <div class="section-sub">
            {html.escape(brand_filter)} · {html.escape(period_filter)}
            · {selected_start.strftime('%d %b')}–{selected_end.strftime('%d %b')}
            · Showing {len(filtered_df)} campaign{'s' if len(filtered_df) != 1 else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if filtered_df.empty:
        st.info("No campaigns found for the selected person, brand and date range.")
    else:
        if selected_owner == "All":
            for owner in owner_universe(filtered_df):
                owner_df = filtered_df[filtered_df["owners"].apply(lambda vals: owner in vals)]

                if owner_df.empty:
                    continue

                cards_html = "\n".join(campaign_card_html(row) for _, row in owner_df.iterrows())

                owner_html = f"""
<div class="owner-block">
  <div class="owner-header">
    <div>
      <div class="owner-name">{html.escape(owner)}</div>
      <div class="owner-sub">{len(owner_df)} campaign{'s' if len(owner_df) != 1 else ''} assigned</div>
    </div>
    <div class="count-pill">{len(owner_df)}</div>
  </div>
  {cards_html}
</div>
""".strip()

                st.markdown(owner_html, unsafe_allow_html=True)
        else:
            cards_html = "\n".join(campaign_card_html(row) for _, row in filtered_df.iterrows())
            st.markdown(cards_html, unsafe_allow_html=True)

with st.expander("Column Debug — use this to lock the right Monday column IDs", expanded=False):
    st.write("Detected mappings")
    st.dataframe(mapping_df, use_container_width=True, hide_index=True)

    st.write("All board columns")
    st.dataframe(columns_df, use_container_width=True, hide_index=True)

    st.caption(
        "Copy the correct column IDs into Streamlit secrets as OWNER_COLUMN_ID, DATE_COLUMN_ID, "
        "STATUS_COLUMN_ID, STAGE_COLUMN_ID, PRIORITY_COLUMN_ID and BRAND_COLUMN_ID."
    )
