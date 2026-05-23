from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components


# ============================================================
# CONFIG
# ============================================================

MONDAY_API_URL = "https://api.monday.com/v2"
DEFAULT_API_VERSION = "2025-04"
PAGE_LIMIT = 500
APP_TIMEZONE = "Europe/London"
CACHE_TTL_SECONDS = 900

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

OWNER_ALIASES = {
    "gautham": "Gautham Marthandan",
    "gautham marthandan": "Gautham Marthandan",
    "amy": "Amy Harris",
    "amy harris": "Amy Harris",
    "ben": "Ben Mendelowitz",
    "ben mendelowitz": "Ben Mendelowitz",
    "kathy": "Kathy Morris",
    "kathy morris": "Kathy Morris",
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
    "produce": {"bg": "#F8FAFC", "text": "#334155", "border": "#CBD5E1"},
    "promote": {"bg": "#F5F3FF", "text": "#6D28D9", "border": "#DDD6FE"},
}

COLUMN_ALIASES = {
    "owner": ["owner", "owners", "person", "people", "assigned", "assignee", "lead", "campaign owner"],
    "date": ["date", "due", "deadline", "key date", "publish", "publication", "launch", "live date", "outreach date"],
    "status": ["status", "campaign status", "progress", "state"],
    "stage": ["stage", "phase", "workflow", "step", "campaign stage", "category"],
    "brand": ["brand", "site", "property", "vertical"],
}


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Campaign Owner Dashboard",
    page_icon="📌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 2.25rem;
            max-width: 1380px;
        }

        .hero {
            background: linear-gradient(135deg, #020617 0%, #111827 52%, #1e293b 100%);
            color: white;
            padding: 30px 32px;
            border-radius: 28px;
            box-shadow: 0 22px 60px rgba(15, 23, 42, 0.22);
            border: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 24px;
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
            max-width: 920px;
            color: #cbd5e1;
            font-size: 16px;
            line-height: 1.65;
        }

        .range-caption {
            color: #64748b;
            font-size: 13px;
            line-height: 1.45;
            margin-top: 12px;
            margin-bottom: 14px;
        }

        div[data-testid="stSidebar"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# BASIC HELPERS
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


def deescaped(value: Any) -> str:
    return html.unescape(str(value or ""))


def canonical_owner_name(value: str) -> str:
    cleaned = deescaped(value).strip()

    if not cleaned:
        return ""

    lowered = normalise(cleaned)

    if lowered in OWNER_ALIASES:
        return OWNER_ALIASES[lowered]

    for key, proper_name in OWNER_ALIASES.items():
        if re.search(rf"\b{re.escape(key)}\b", lowered):
            return proper_name

    return cleaned


def dedupe_keep_order(values: List[str]) -> List[str]:
    seen = set()
    output = []

    for value in values:
        cleaned = value.strip()
        key = normalise(cleaned)

        if cleaned and key not in seen:
            seen.add(key)
            output.append(cleaned)

    return output


def clean_brand_name(value: str) -> str:
    text = deescaped(value).strip()
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


def london_today() -> date:
    return datetime.now(ZoneInfo(APP_TIMEZONE)).date()


def month_range(year: int, month: int) -> Tuple[date, date]:
    start = date(year, month, 1)

    if month == 12:
        next_month_start = date(year + 1, 1, 1)
    else:
        next_month_start = date(year, month + 1, 1)

    return start, next_month_start - timedelta(days=1)


def add_months(value: date, offset: int) -> date:
    month_index = value.month - 1 + offset
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def get_month_options() -> List[Dict[str, Any]]:
    today = london_today()
    current_month = date(today.year, today.month, 1)

    options: List[Dict[str, Any]] = []

    for offset in range(-2, 10):
        month_start = add_months(current_month, offset)
        month_end = month_range(month_start.year, month_start.month)[1]

        options.append(
            {
                "label": month_start.strftime("%B %Y"),
                "start": month_start,
                "end": month_end,
            }
        )

    return options


def get_week_options_for_month(month_start: date, month_end: date) -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = [
        {
            "label": "All weeks",
            "start": month_start,
            "end": month_end,
        }
    ]

    first_monday = month_start - timedelta(days=month_start.weekday())
    cursor = first_monday
    week_number = 1

    while cursor <= month_end:
        raw_start = cursor
        raw_end = cursor + timedelta(days=6)

        clipped_start = max(raw_start, month_start)
        clipped_end = min(raw_end, month_end)

        if clipped_start <= clipped_end:
            options.append(
                {
                    "label": f"Week {week_number}: {clipped_start.strftime('%d %b')}–{clipped_end.strftime('%d %b')}",
                    "start": clipped_start,
                    "end": clipped_end,
                }
            )

        cursor += timedelta(days=7)
        week_number += 1

    return options


def default_week_index(week_options: List[Dict[str, Any]], month_start: date, month_end: date) -> int:
    today = london_today()

    if not (month_start <= today <= month_end):
        return 0

    for idx, option in enumerate(week_options):
        if option["start"] <= today <= option["end"]:
            return idx

    return 0


# ============================================================
# DATE + OWNER PARSING
# ============================================================

def parse_single_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)

    if pd.isna(parsed):
        return None

    return parsed.date()


def parse_monday_date_range(text: Any, raw_value: Any = None) -> Tuple[Optional[date], Optional[date]]:
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    if raw_value:
        try:
            parsed_value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value

            if isinstance(parsed_value, dict):
                if parsed_value.get("date"):
                    one_date = parse_single_date(parsed_value.get("date"))
                    return one_date, one_date

                from_date = parse_single_date(parsed_value.get("from"))
                to_date = parse_single_date(parsed_value.get("to"))

                if from_date or to_date:
                    return from_date or to_date, to_date or from_date
        except Exception:
            pass

    text_date = parse_single_date(text)

    if text_date:
        start_date = text_date
        end_date = text_date

    return start_date, end_date


def parse_group_week_range(group_title: str) -> Tuple[Optional[date], Optional[date]]:
    text = deescaped(group_title)
    lower = normalise(text)

    patterns = [
        r"(?:week\s*c\.?|week\s+commencing|w/c|wc|c\.)\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})",
        r"week\s+of\s+(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, lower)

        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))

            if year < 100:
                year += 2000

            try:
                start = date(year, month, day)
                return start, start + timedelta(days=6)
            except ValueError:
                return None, None

    return None, None


def format_display_date_range(start: Optional[date], end: Optional[date]) -> str:
    if not start and not end:
        return "No date"

    if start and not end:
        return start.strftime("%a %d %b")

    if end and not start:
        return end.strftime("%a %d %b")

    if start == end:
        return start.strftime("%a %d %b")

    if start.year == end.year and start.month == end.month:
        return f"{start.strftime('%d')}–{end.strftime('%d %b')}"

    if start.year == end.year:
        return f"{start.strftime('%d %b')}–{end.strftime('%d %b')}"

    return f"{start.strftime('%d %b %Y')}–{end.strftime('%d %b %Y')}"


def extract_people_from_value(raw_value: Any, user_map: Dict[str, str]) -> List[str]:
    names: List[str] = []

    if not raw_value:
        return names

    try:
        parsed_value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except Exception:
        return names

    if not isinstance(parsed_value, dict):
        return names

    people_bits = parsed_value.get("personsAndTeams") or parsed_value.get("persons_and_teams") or []

    if not isinstance(people_bits, list):
        return names

    for person in people_bits:
        if not isinstance(person, dict):
            continue

        person_id = str(person.get("id") or "").strip()
        kind = str(person.get("kind") or "").strip().lower()

        if kind == "person" and person_id in user_map:
            names.append(user_map[person_id])
        elif kind == "person" and person_id:
            names.append(f"Person {person_id}")
        elif kind == "team" and person_id:
            names.append(f"Team {person_id}")

    return names


def split_people_text(text: Any) -> List[str]:
    cleaned = deescaped(text).strip()

    if not cleaned:
        return []

    people = [p.strip() for p in re.split(r",|;|\||\n| / ", cleaned) if p.strip()]
    return people or [cleaned]


def extract_owners(owner_text: Any, owner_raw: Any, user_map: Dict[str, str]) -> List[str]:
    owners: List[str] = []

    owners.extend(extract_people_from_value(owner_raw, user_map))
    owners.extend(split_people_text(owner_text))

    canonicalised = [canonical_owner_name(owner) for owner in owners]
    canonicalised = [owner for owner in canonicalised if owner and not owner.lower().startswith("person ")]

    return dedupe_keep_order(canonicalised) or ["Unassigned"]


def owner_matches(owners: List[str], selected_owner: str) -> bool:
    if selected_owner == "All":
        return True

    selected_key = normalise(canonical_owner_name(selected_owner))

    for owner in owners:
        owner_key = normalise(canonical_owner_name(owner))

        if owner_key == selected_key:
            return True

        if selected_key in owner_key or owner_key in selected_key:
            return True

    return False


# ============================================================
# DISPLAY HELPERS
# ============================================================

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
<details class="campaign-card">
  <summary class="campaign-summary">
    <span class="summary-toggle" aria-hidden="true"></span>
    <div class="summary-main">
      <div class="badge-row">
        {badge(row.get("brand", "—"), brand_colours)}
        {badge(str(row.get("status", "—")), status_colours)}
        {badge(str(row.get("date_display", "No date")), {"bg": "#F8FAFC", "text": "#334155", "border": "#CBD5E1"})}
      </div>
      <div class="campaign-title">{html.escape(str(row.get("campaign", "Untitled campaign")))}</div>
      <div class="campaign-note">
        Board: {html.escape(str(row.get("board_name", "—")))} · Group: {html.escape(str(row.get("group", "—")))}
      </div>
    </div>
  </summary>

  <div class="campaign-details">
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
        <div class="mini-value">{html.escape(str(row.get("date_display", "No date")))}</div>
      </div>
    </div>
  </div>
</details>
""".strip()


# ============================================================
# MONDAY API QUERIES
# ============================================================

BOARD_COLUMNS_QUERY = """
query ($board_ids: [ID!]) {
  boards(ids: $board_ids) {
    id
    name
    columns {
      id
      title
      type
    }
  }
}
"""

USERS_QUERY = """
query {
  users {
    id
    name
    email
  }
}
"""

BOARD_ITEMS_SELECTED_QUERY = """
query ($board_ids: [ID!], $limit: Int!, $column_ids: [String]) {
  boards(ids: $board_ids) {
    id
    items_page(limit: $limit) {
      cursor
      items {
        id
        name
        group {
          id
          title
        }
        column_values(ids: $column_ids) {
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

NEXT_ITEMS_SELECTED_QUERY = """
query ($cursor: String!, $limit: Int!, $column_ids: [String]) {
  next_items_page(cursor: $cursor, limit: $limit) {
    cursor
    items {
      id
      name
      group {
        id
        title
      }
      column_values(ids: $column_ids) {
        id
        text
        value
        type
      }
    }
  }
}
"""

BOARD_ITEMS_ALL_QUERY = """
query ($board_ids: [ID!], $limit: Int!) {
  boards(ids: $board_ids) {
    id
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

NEXT_ITEMS_ALL_QUERY = """
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


def fetch_user_map(api_key: str, api_version: str) -> Dict[str, str]:
    try:
        data = monday_graphql(api_key, api_version, USERS_QUERY)
        users = data.get("users", []) or []

        mapping: Dict[str, str] = {}

        for user in users:
            user_id = str(user.get("id") or "").strip()
            name = str(user.get("name") or "").strip()

            if user_id and name:
                mapping[user_id] = canonical_owner_name(name)

        return mapping
    except Exception:
        return {}


def fetch_board_columns(
    api_key: str,
    api_version: str,
    board_ids: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    data = monday_graphql(
        api_key,
        api_version,
        BOARD_COLUMNS_QUERY,
        {"board_ids": [str(board_id) for board_id in board_ids]},
    )

    return data.get("boards", []) or []


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


def resolve_board_column_ids(columns: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    return {
        "owner": find_column_id(columns, get_secret("OWNER_COLUMN_ID", ""), COLUMN_ALIASES["owner"], ["people", "person"]),
        "date": find_column_id(columns, get_secret("DATE_COLUMN_ID", ""), COLUMN_ALIASES["date"], ["date", "timeline"]),
        "status": find_column_id(columns, get_secret("STATUS_COLUMN_ID", ""), COLUMN_ALIASES["status"], ["status"]),
        "stage": find_column_id(columns, get_secret("STAGE_COLUMN_ID", ""), COLUMN_ALIASES["stage"], ["dropdown", "status"]),
        "brand": find_column_id(columns, get_secret("BRAND_COLUMN_ID", ""), COLUMN_ALIASES["brand"], ["dropdown", "status"]),
    }


def fetch_board_items(
    api_key: str,
    api_version: str,
    board: Dict[str, Any],
    selected_column_ids: List[str],
) -> Dict[str, Any]:
    board_id = str(board.get("id", ""))

    try_selected = bool(selected_column_ids)

    if try_selected:
        try:
            data = monday_graphql(
                api_key,
                api_version,
                BOARD_ITEMS_SELECTED_QUERY,
                {
                    "board_ids": [board_id],
                    "limit": PAGE_LIMIT,
                    "column_ids": selected_column_ids,
                },
            )

            board_data = (data.get("boards") or [{}])[0]
            items_page = board_data.get("items_page") or {}
            all_items = list(items_page.get("items") or [])
            cursor = items_page.get("cursor")

            while cursor:
                next_data = monday_graphql(
                    api_key,
                    api_version,
                    NEXT_ITEMS_SELECTED_QUERY,
                    {
                        "cursor": cursor,
                        "limit": PAGE_LIMIT,
                        "column_ids": selected_column_ids,
                    },
                )

                next_page = next_data.get("next_items_page") or {}
                all_items.extend(next_page.get("items") or [])
                cursor = next_page.get("cursor")

            board["items"] = all_items
            return board

        except Exception:
            pass

    data = monday_graphql(
        api_key,
        api_version,
        BOARD_ITEMS_ALL_QUERY,
        {
            "board_ids": [board_id],
            "limit": PAGE_LIMIT,
        },
    )

    board_data = (data.get("boards") or [{}])[0]
    items_page = board_data.get("items_page") or {}
    all_items = list(items_page.get("items") or [])
    cursor = items_page.get("cursor")

    while cursor:
        next_data = monday_graphql(
            api_key,
            api_version,
            NEXT_ITEMS_ALL_QUERY,
            {
                "cursor": cursor,
                "limit": PAGE_LIMIT,
            },
        )

        next_page = next_data.get("next_items_page") or {}
        all_items.extend(next_page.get("items") or [])
        cursor = next_page.get("cursor")

    board["items"] = all_items
    return board


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_monday_data(
    api_key: str,
    api_version: str,
    board_ids: Tuple[str, ...],
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    boards = fetch_board_columns(api_key, api_version, board_ids)
    user_map = fetch_user_map(api_key, api_version)

    prepared_boards = []

    for board in boards:
        columns = board.get("columns", []) or []
        column_ids = resolve_board_column_ids(columns)
        selected_column_ids = dedupe_keep_order([value for value in column_ids.values() if value])

        board["resolved_column_ids"] = column_ids
        board["selected_column_ids"] = selected_column_ids
        prepared_boards.append(board)

    results: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=min(4, max(1, len(prepared_boards)))) as executor:
        futures = [
            executor.submit(
                fetch_board_items,
                api_key,
                api_version,
                board,
                board.get("selected_column_ids", []),
            )
            for board in prepared_boards
        ]

        for future in as_completed(futures):
            results.append(future.result())

    board_order = {str(board_id): idx for idx, board_id in enumerate(board_ids)}
    results.sort(key=lambda board: board_order.get(str(board.get("id", "")), 999))

    return results, user_map


# ============================================================
# MONDAY TRANSFORM
# ============================================================

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
    user_map: Dict[str, str],
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    for board in boards:
        board_id = str(board.get("id", ""))
        board_name = str(board.get("name", "Untitled board"))
        column_ids = board.get("resolved_column_ids", {}) or {}

        owner_col = column_ids.get("owner")
        date_col = column_ids.get("date")
        status_col = column_ids.get("status")
        stage_col = column_ids.get("stage")
        brand_col = column_ids.get("brand")

        for item in board.get("items", []) or []:
            group_title = (item.get("group") or {}).get("title") or "—"

            owner_text, owner_raw, _ = get_column_value(item, owner_col)
            date_text, date_raw, _ = get_column_value(item, date_col)
            status_text, _, _ = get_column_value(item, status_col)
            stage_text, _, _ = get_column_value(item, stage_col)
            brand_text, _, _ = get_column_value(item, brand_col)

            owners = extract_owners(owner_text, owner_raw, user_map)

            start_date, end_date = parse_monday_date_range(date_text, date_raw)

            if not start_date and not end_date:
                start_date, end_date = parse_group_week_range(group_title)

            brand = clean_brand_name(brand_text or board_brand_map.get(board_id) or board_name)

            rows.append(
                {
                    "board_id": board_id,
                    "board_name": board_name,
                    "group": group_title,
                    "item_id": str(item.get("id", "")),
                    "campaign": deescaped(item.get("name") or "Untitled campaign"),
                    "brand": brand,
                    "owners": owners,
                    "owners_display": ", ".join(owners),
                    "start_date": start_date,
                    "end_date": end_date or start_date,
                    "date_display": format_display_date_range(start_date, end_date or start_date),
                    "date_raw_text": date_text,
                    "status": deescaped(status_text or "—"),
                    "stage": deescaped(stage_text or "—"),
                }
            )

    df = pd.DataFrame(rows)

    if not df.empty:
        df["sort_date"] = pd.to_datetime(df["start_date"], errors="coerce")
        df = df.sort_values(["sort_date", "brand", "campaign"], na_position="last")

    return df


def owner_universe(df: pd.DataFrame) -> List[str]:
    if df.empty or "owners" not in df.columns:
        return []

    owners: List[str] = []

    for values in df["owners"]:
        if isinstance(values, list):
            owners.extend(values)

    return sorted(set(owners), key=lambda x: normalise(x))


def date_overlaps(
    item_start: Optional[date],
    item_end: Optional[date],
    selected_start: date,
    selected_end: date,
) -> bool:
    if not item_start and not item_end:
        return False

    actual_start = item_start or item_end
    actual_end = item_end or item_start

    return actual_start <= selected_end and actual_end >= selected_start


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
        filtered.apply(
            lambda row: date_overlaps(row.get("start_date"), row.get("end_date"), start_date, end_date),
            axis=1,
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

    return df[df["owners"].apply(lambda vals: owner_matches(vals, person))]


# ============================================================
# HTML RESULTS
# ============================================================

def cards_grid_html(df: pd.DataFrame) -> str:
    cards = "\n".join(campaign_card_html(row) for _, row in df.iterrows())
    return f'<div class="campaign-grid">{cards}</div>'


def owner_block_html(owner: str, owner_df: pd.DataFrame, open_by_default: bool = False) -> str:
    open_attr = " open" if open_by_default else ""

    return f"""
<details class="owner-block"{open_attr}>
  <summary class="owner-summary">
    <span class="owner-toggle" aria-hidden="true"></span>
    <div class="owner-summary-main">
      <div class="owner-name">{html.escape(owner)}</div>
      <div class="owner-sub">{len(owner_df)} campaign{'s' if len(owner_df) != 1 else ''} assigned</div>
    </div>
    <div class="count-pill">{len(owner_df)}</div>
  </summary>
  {cards_grid_html(owner_df)}
</details>
""".strip()


def build_results_html(filtered_df: pd.DataFrame, owner_filter: str) -> str:
    if filtered_df.empty:
        content = '<div class="empty-state">No campaigns found for the selected owner, brand and week.</div>'

    elif owner_filter == "All":
        blocks: List[str] = []

        for owner in owner_universe(filtered_df):
            owner_df = filtered_df[filtered_df["owners"].apply(lambda vals: owner_matches(vals, owner))]

            if owner_df.empty:
                continue

            blocks.append(owner_block_html(owner, owner_df, open_by_default=False))

        content = "\n".join(blocks)

    else:
        content = owner_block_html(owner_filter, filtered_df, open_by_default=False)

    return f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}

  html, body {{
    margin: 0;
    padding: 0;
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #020617;
  }}

  .results-panel {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 28px;
    box-shadow: 0 10px 34px rgba(15, 23, 42, 0.06);
    padding: 16px;
    height: 740px;
    overflow-y: auto;
    overflow-x: auto;
  }}

  .results-panel::-webkit-scrollbar {{ width: 10px; height: 10px; }}
  .results-panel::-webkit-scrollbar-track {{ background: #f1f5f9; border-radius: 999px; }}
  .results-panel::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 999px; border: 2px solid #f1f5f9; }}
  .results-panel::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}

  .results-inner {{
    min-width: 900px;
  }}

  details > summary {{
    list-style: none;
    cursor: pointer;
  }}

  details > summary::-webkit-details-marker {{
    display: none;
  }}

  .owner-block {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 24px;
    padding: 14px;
    margin-bottom: 14px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  }}

  .owner-block:last-child {{ margin-bottom: 0; }}

  .owner-summary {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 14px;
    padding: 2px 2px 0;
  }}

  .owner-block[open] .owner-summary {{
    margin-bottom: 12px;
  }}

  .owner-toggle::before {{
    content: "+";
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 999px;
    background: #f1f5f9;
    color: #020617;
    font-size: 16px;
    font-weight: 900;
    margin-right: 2px;
  }}

  .owner-block[open] .owner-toggle::before {{
    content: "−";
  }}

  .owner-summary-main {{
    flex: 1;
    min-width: 0;
  }}

  .owner-name {{
    font-size: 18px;
    font-weight: 850;
    letter-spacing: -0.03em;
    color: #020617;
    margin: 0;
  }}

  .owner-sub {{
    color: #64748b;
    font-size: 13px;
    margin-top: 2px;
  }}

  .count-pill {{
    background: #020617;
    color: white;
    border-radius: 999px;
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 850;
    white-space: nowrap;
  }}

  .campaign-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    align-items: start;
  }}

  .campaign-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 20px;
    padding: 14px;
    box-shadow: 0 5px 18px rgba(15, 23, 42, 0.04);
    min-width: 0;
  }}

  .campaign-card:hover {{
    transform: translateY(-1px);
    transition: 0.16s ease;
    box-shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
  }}

  .campaign-summary {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }}

  .summary-toggle::before {{
    content: "+";
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 999px;
    background: #f1f5f9;
    color: #020617;
    font-size: 15px;
    font-weight: 900;
    margin-top: 1px;
  }}

  .campaign-card[open] .summary-toggle::before {{
    content: "−";
  }}

  .summary-main {{
    flex: 1;
    min-width: 0;
  }}

  .badge-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-bottom: 10px;
  }}

  .badge {{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 4px 9px;
    font-size: 11px;
    font-weight: 850;
    border: 1px solid transparent;
    line-height: 1;
    white-space: nowrap;
  }}

  .campaign-title {{
    font-size: 16px;
    font-weight: 850;
    letter-spacing: -0.02em;
    color: #020617;
    margin-bottom: 6px;
    line-height: 1.3;
  }}

  .campaign-note {{
    color: #64748b;
    font-size: 12px;
    line-height: 1.45;
  }}

  .campaign-details {{
    margin-top: 12px;
  }}

  .mini-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    background: #f8fafc;
    border-radius: 15px;
    padding: 10px;
  }}

  .mini-label {{
    color: #94a3b8;
    font-size: 10px;
    font-weight: 800;
    margin-bottom: 2px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .mini-value {{
    color: #334155;
    font-size: 12px;
    font-weight: 850;
    word-break: break-word;
    line-height: 1.35;
  }}

  .empty-state {{
    border: 1px dashed #cbd5e1;
    border-radius: 24px;
    padding: 32px;
    text-align: center;
    color: #64748b;
    background: #f8fafc;
  }}

  @media (max-width: 900px) {{
    .results-inner {{ min-width: 680px; }}
    .campaign-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
  <div class="results-panel">
    <div class="results-inner">
      {content}
    </div>
  </div>
</body>
</html>
""".strip()


# ============================================================
# APP
# ============================================================

st.markdown(
    """
    <div class="hero">
        <div class="hero-pill">📌 Monday.com live dashboard</div>
        <h1 class="hero-title">Campaign Owner Dashboard</h1>
        <div class="hero-copy">
            Choose a month, week, brand and owner to see assigned campaigns in a compact weekly view.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

api_key = get_monday_api_key()
api_version = str(get_secret("MONDAY_API_VERSION", DEFAULT_API_VERSION) or DEFAULT_API_VERSION).strip()
board_ids = tuple(to_clean_list(get_secret("MONDAY_BOARD_IDS", [])) or DEFAULT_BOARD_IDS)

if not api_key:
    st.error("Missing Monday API key in Streamlit secrets.")
    st.stop()

refresh_col, _ = st.columns([1, 5])

with refresh_col:
    refresh_clicked = st.button("Refresh data", use_container_width=True)

if refresh_clicked:
    fetch_monday_data.clear()
    st.rerun()

try:
    with st.spinner("Pulling campaign data from Monday.com..."):
        monday_boards, monday_user_map = fetch_monday_data(api_key, api_version, board_ids)
        campaigns_df = build_rows(monday_boards, get_board_brand_map(), monday_user_map)
except Exception as exc:
    st.error("Could not fetch Monday data.")
    st.code(str(exc))
    st.stop()

if campaigns_df.empty:
    st.warning("No campaign items were returned from the selected Monday boards.")
    st.stop()

month_options = get_month_options()
month_labels = [option["label"] for option in month_options]

today = london_today()
current_month_label = date(today.year, today.month, 1).strftime("%B %Y")
default_month_index = month_labels.index(current_month_label) if current_month_label in month_labels else 0

filter_col_1, filter_col_2, filter_col_3, filter_col_4 = st.columns(4, gap="large")

with filter_col_1:
    selected_month_label = st.selectbox(
        "Month",
        month_labels,
        index=default_month_index,
        key="month_filter",
    )

selected_month = next(option for option in month_options if option["label"] == selected_month_label)

week_options = get_week_options_for_month(selected_month["start"], selected_month["end"])
week_labels = [option["label"] for option in week_options]
week_default_index = default_week_index(week_options, selected_month["start"], selected_month["end"])

with filter_col_2:
    selected_week_label = st.selectbox(
        "Week",
        week_labels,
        index=week_default_index,
        key=f"week_filter_{selected_month_label}",
    )

selected_week = next(option for option in week_options if option["label"] == selected_week_label)
selected_start = selected_week["start"]
selected_end = selected_week["end"]

with filter_col_3:
    brand_filter = st.selectbox(
        "Brand",
        ["All", "Action Network", "VegasInsider", "Canada Sports Betting", "RotoGrinders"],
        index=0,
        key="brand_filter",
    )

base_filtered_df = apply_base_filters(
    campaigns_df,
    start_date=selected_start,
    end_date=selected_end,
    brand=brand_filter,
)

owner_options = ["All"] + owner_universe(base_filtered_df)

with filter_col_4:
    owner_filter = st.selectbox(
        "Owner",
        owner_options,
        index=0,
        key="owner_filter",
    )

st.markdown(
    f"""
    <div class="range-caption">
        Showing: {selected_month_label} · {selected_week_label} · {selected_start.strftime('%d %b %Y')}–{selected_end.strftime('%d %b %Y')}
    </div>
    """,
    unsafe_allow_html=True,
)

filtered_df = apply_person_filter(base_filtered_df, owner_filter)

components.html(
    build_results_html(filtered_df, owner_filter),
    height=780,
    scrolling=False,
)
