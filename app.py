import os
import time
import io
import csv
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlencode

import requests
import streamlit as st

# -------------------- SEC endpoints --------------------
SEC_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik_padded}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_nodashes}/{primary_doc}"

# Add support for foreign issuer equivalents
FORMS_TO_SHOW = ["10-K", "10-Q", "8-K", "DEF 14A", "20-F", "6-K"]
HISTORY_LIMITS = {"10-K": 5, "10-Q": 8, "8-K": 12, "DEF 14A": 5, "20-F": 5, "6-K": 12}

# -------------------- Price (best-effort "last close") --------------------
STOOQ_QUOTE_CSV = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"

# -------------------- SEC investor/resources links --------------------
SEC_LINKS = {
    "Search Filings": "https://www.sec.gov/search-filings",
    "EDGAR Full Text Search": "https://www.sec.gov/edgar/search/",
    "Using EDGAR to Research Investments": "https://www.sec.gov/search-filings/edgar-search-assistance/using-edgar-research-investments",
    "How to Read a 10-K (Investor Bulletin)": "https://www.sec.gov/answers/reada10k.htm",
    "How to Read a 10-K/10-Q (Fast Answers)": "https://www.sec.gov/fast-answers/answersreada10khtm.html",
    "EDGAR Search Assistance Hub": "https://www.sec.gov/search-filings/edgar-search-assistance",
}

# Per-form “Read on SEC” links (official, best available)
FORM_READ_ON_SEC = {
    "10-K": "https://www.sec.gov/answers/reada10k.htm",
    "10-Q": "https://www.sec.gov/fast-answers/answersreada10khtm.html",
    "8-K": "https://www.sec.gov/fast-answers/answersform8khtm.html",
    "DEF 14A": "https://www.sec.gov/answers/proxyhtf.htm",
    "20-F": "https://www.sec.gov/divisions/corpfin/internatl/foreign-private-issuers-overview.shtml#IIIB1a",
    "6-K": "https://www.sec.gov/divisions/corpfin/internatl/foreign-private-issuers-overview.shtml#IIIB3",
}

# -------------------- Copy --------------------
DISCLAIMER_ONE_LINER = "Informational only — not investment advice. Verify directly on SEC EDGAR."
ABOUT_PAGE = """
## About

This app gives fast access to official SEC EDGAR filings for US-listed companies and foreign issuers trading in the US.

Filings are primary sources. Investors use them to judge business quality, financial health, risks, cash flow, and incentives — straight from required disclosures.

Not investment advice. Not affiliated with the SEC.
""".strip()

FORM_GLOSSARY = {
    "10-K": "Annual report (audited). Full business + financial picture.",
    "10-Q": "Quarterly update (unaudited). Trend-check and changes.",
    "8-K": "Material events between reports (deals, changes, updates).",
    "DEF 14A": "Proxy statement: compensation, governance, voting matters.",
    "20-F": "Annual report for foreign private issuers (10-K equivalent).",
    "6-K": "Interim/current reports for foreign issuers (8-K equivalent).",
}


# -------------------- Styling --------------------
def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 1180px; padding-top: 0.6rem; padding-bottom: 1.9rem; }
        header[data-testid="stHeader"] { background: transparent; }
        section[data-testid="stSidebar"] { display: none; }

        html, body, [class*="css"] { font-size: 18px !important; }

        :root{
          --card: var(--secondary-background-color);
          --fg: var(--text-color);
          --muted: color-mix(in srgb, var(--fg) 70%, transparent);
          --muted2: color-mix(in srgb, var(--fg) 55%, transparent);
          --stroke: color-mix(in srgb, var(--fg) 16%, transparent);
          --stroke2: color-mix(in srgb, var(--fg) 24%, transparent);
          --accent: #2ea8ff;
          --accent2: #00d3a7;
        }

        input {
          font-size: 1.05rem !important;
          padding: 0.70rem !important;
          border-radius: 10px !important;
          border: 1px solid var(--stroke) !important;
          background: color-mix(in srgb, var(--card) 92%, transparent) !important;
          color: var(--fg) !important;
        }

        .topbar{
          padding: 12px 14px;
          border-radius: 12px;
          border: 1px solid var(--stroke);
          background:
            radial-gradient(900px 420px at 0% 0%, color-mix(in srgb, var(--accent) 10%, transparent), transparent 60%),
            radial-gradient(900px 420px at 100% 10%, color-mix(in srgb, var(--accent2) 7%, transparent), transparent 60%),
            color-mix(in srgb, var(--card) 96%, transparent);
          margin: 6px 0 10px 0;
        }
        .brand { font-weight: 980; letter-spacing: -0.02em; font-size: 1.18rem; color: var(--fg); }
        .sub { color: var(--muted); font-size: 0.96rem; margin-top: 3px; }

        .panel {
          border: 1px solid var(--stroke);
          border-radius: 12px;
          padding: 12px 14px;
          background: color-mix(in srgb, var(--card) 96%, transparent);
          box-shadow: none;
          margin: 8px 0;
        }
        .divider { height: 1px; background: var(--stroke); margin: 10px 0 8px 0; }

        .muted { color: var(--muted); }
        .muted2 { color: var(--muted2); }

        div.stButton > button {
          border-radius: 10px !important;
          padding: 0.62rem 0.85rem !important;
          font-weight: 820 !important;
          border: 1px solid var(--stroke) !important;
          background: color-mix(in srgb, var(--card) 96%, transparent) !important;
          transition: border-color 110ms ease, background 110ms ease, transform 120ms ease;
          box-shadow: none !important;
          color: var(--fg) !important;
        }
        div.stButton > button:hover {
          border-color: color-mix(in srgb, var(--accent) 45%, transparent) !important;
          background: color-mix(in srgb, var(--accent) 6%, var(--card)) !important;
          transform: translateY(-1px);
        }

        button[kind="primary"]{
          border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--stroke)) !important;
          background: linear-gradient(
            90deg,
            color-mix(in srgb, var(--accent) 22%, var(--card)),
            color-mix(in srgb, var(--accent2) 18%, var(--card))
          ) !important;
          color: var(--fg) !important;
        }
        button[kind="primary"]:hover{
          border-color: color-mix(in srgb, var(--accent2) 55%, transparent) !important;
          background: linear-gradient(
            90deg,
            color-mix(in srgb, var(--accent) 28%, var(--card)),
            color-mix(in srgb, var(--accent2) 22%, var(--card))
          ) !important;
        }

        .filing-title a{
          font-weight: 920;
          font-size: 1.06rem;
          color: var(--fg);
          text-decoration: none;
        }
        .filing-title a:hover{
          text-decoration: underline;
          text-decoration-color: color-mix(in srgb, var(--accent2) 55%, transparent);
        }
        .meta{ margin-top: 6px; color: var(--muted2); font-size: 0.93rem; }

        .dir-link{
          display:block;
          text-decoration:none !important;
          color: var(--fg) !important;
          border: 1px solid var(--stroke);
          border-radius: 12px;
          padding: 9px 12px;
          margin: 6px 0;
          background: color-mix(in srgb, var(--card) 96%, transparent);
          transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }
        .dir-link:hover{
          border-color: color-mix(in srgb, var(--accent) 45%, transparent);
          background: color-mix(in srgb, var(--accent) 6%, var(--card));
          transform: translateY(-1px);
        }
        .dir-alt{
          background: color-mix(in srgb, var(--accent) 2.3%, var(--card)) !important;
        }
        .dir-top{
          display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;
          align-items:baseline;
        }
        .dir-ticker{ font-weight: 950; letter-spacing: -0.01em; }
        .dir-cik{ color: var(--muted2); font-weight: 750; }
        .dir-hairline{
          display:block;
          width: 100%;
          height: 1px;
          background: var(--stroke2);
          margin: 6px 0;
          opacity: 0.95;
        }
        .dir-title{ color: var(--muted2); margin-top: 2px; font-size: 0.94rem; }

        .wf-grid{ display:flex; flex-direction:column; gap:8px; }
        .wf-row{
          border:1px solid var(--stroke);
          border-radius:12px;
          padding:10px 12px;
          background: color-mix(in srgb, var(--card) 96%, transparent);
          transition: border-color 120ms ease, background 120ms ease;
        }
        .wf-row:hover{
          border-color: color-mix(in srgb, var(--accent2) 38%, transparent);
          background: color-mix(in srgb, var(--accent2) 4%, var(--card));
        }
        .wf-head{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; }
        .wf-form{ font-weight: 950; letter-spacing:-0.01em; }
        .wf-tag{ color: var(--muted2); font-weight: 750; }
        .wf-body{
          margin-top: 4px;
          color: var(--muted);
          font-size: 0.95rem;
          line-height: 1.25rem;
        }

        .company-link{
          display:block;
          text-decoration:none !important;
          color: var(--fg) !important;
        }
        .company-link:hover .panel{
          border-color: color-mix(in srgb, var(--accent2) 45%, transparent);
          background: color-mix(in srgb, var(--accent2) 4%, var(--card));
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -------------------- Networking (SEC headers + retry) --------------------
def _sec_contact() -> str:
    try:
        contact = st.secrets.get("SEC_CONTACT_EMAIL", None)  # type: ignore[attr-defined]
    except Exception:
        contact = None
    if not contact:
        contact = os.getenv("SEC_CONTACT_EMAIL", "").strip()
    return contact or "you@yourdomain.com"


def build_headers() -> Dict[str, str]:
    contact = _sec_contact()
    return {
        "User-Agent": f"FilingsFinderStreamlit/1.0 ({contact})",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json,text/html,*/*",
    }


def fetch_json(url: str) -> Any:
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=build_headers(), timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    raise last_err if last_err else RuntimeError("Unknown error fetching JSON")


# -------------------- SEC helpers --------------------
@st.cache_data(ttl=24 * 3600, show_spinner="Loading SEC ticker list…")
def get_ticker_entries() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    data = fetch_json(SEC_TICKER_CIK_URL)

    entries: List[Dict[str, Any]] = []
    stats = {"raw_rows": 0, "kept": 0, "skipped_blank_ticker": 0, "skipped_missing_cik": 0}

    for _, entry in data.items():
        stats["raw_rows"] += 1

        t = str(entry.get("ticker", "") or "").upper().strip()
        if not t:
            stats["skipped_blank_ticker"] += 1
            continue

        cik_raw = entry.get("cik_str", 0)
        try:
            cik = int(cik_raw)
        except Exception:
            cik = 0
        if not cik:
            stats["skipped_missing_cik"] += 1
            continue

        title = str(entry.get("title", "") or "").strip()
        entries.append({"ticker": t, "cik": cik, "title": title})
        stats["kept"] += 1

    entries.sort(key=lambda x: x["ticker"])
    return entries, stats


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_ticker_cik_map() -> Dict[str, int]:
    entries, _ = get_ticker_entries()
    return {e["ticker"]: int(e["cik"]) for e in entries}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_company_submissions(cik_int: int) -> Dict[str, Any]:
    cik_padded = f"{cik_int:010d}"
    time.sleep(0.2)  # gentle base rate-limiting
    return fetch_json(SEC_SUBMISSIONS_URL.format(cik_padded=cik_padded))


def edgar_browse_url(cik_int: int) -> str:
    return f"https://www.sec.gov/edgar/browse/?CIK={cik_int}&owner=exclude"


def days_since(date_str: str) -> Optional[int]:
    try:
        filed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.today().date()
        return (today - filed_date).days
    except Exception:
        return None


def _recent_arrays(submissions: Dict[str, Any]) -> Tuple[List[str], List[str], List[str], List[str], List[str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", []) or []
    dates = recent.get("filingDate", []) or []
    accessions = recent.get("accessionNumber", []) or []
    primary_docs = recent.get("primaryDocument", []) or []
    report_dates = recent.get("reportDate", []) or []
    return forms, dates, accessions, primary_docs, report_dates


def filings_for_form(submissions: Dict[str, Any], form_type: str, limit: int) -> List[Dict[str, Any]]:
    forms, dates, accessions, primary_docs, report_dates = _recent_arrays(submissions)
    out: List[Dict[str, Any]] = []
    cik_int = int(submissions["cik"])

    for i, f in enumerate(forms):
        if f != form_type:
            continue

        accession = accessions[i]
        accession_nodashes = accession.replace("-", "")
        primary_doc = primary_docs[i]
        url = SEC_ARCHIVES_BASE.format(
            cik_int=cik_int,
            accession_no_nodashes=accession_nodashes,
            primary_doc=primary_doc,
        )

        filed = dates[i] if i < len(dates) else ""
        age = days_since(filed) if filed else None
        period = report_dates[i] if i < len(report_dates) else "" or ""

        out.append(
            {
                "form": form_type,
                "filing_date": filed,
                "days_since": age,
                "period": period,
                "accession": accession,
                "url": url,
            }
        )

        if len(out) >= limit:
            break

    return out


def build_results(submissions: Dict[str, Any], ticker: str, cik_int: int) -> Dict[str, Any]:
    company_name = submissions.get("name", "Unknown Company")
    latest: List[Dict[str, Any]] = []
    history: Dict[str, List[Dict[str, Any]]] = {}

    for form in FORMS_TO_SHOW:
        limit = HISTORY_LIMITS.get(form, 5)
        rows = filings_for_form(submissions, form, limit=limit)
        history[form] = rows
        if rows:
            latest.append(rows[0])

    return {
        "company_name": company_name,
        "ticker": ticker,
        "cik": cik_int,
        "browse_url": edgar_browse_url(cik_int),
        "latest": latest,
        "history": history,
    }


# -------------------- Price --------------------
@st.cache_data(ttl=900, show_spinner=False)
def get_last_close_best_effort(ticker: str) -> Optional[float]:
    t = ticker.strip().upper()
    if not t:
        return None
    symbol = f"{t.lower()}.us"
    url = STOOQ_QUOTE_CSV.format(symbol=symbol)

    try:
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        text = r.text.strip()
        if not text:
            return None
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return None
        close_str = (rows[0].get("Close") or "").strip()
        if close_str in ("", "N/A", "-"):
            return None
        return float(close_str)
    except Exception:
        return None


# -------------------- Routing via query params --------------------
def _get_query_params() -> Dict[str, List[str]]:
    try:
        return dict(st.query_params)  # type: ignore[attr-defined]
    except Exception:
        return st.experimental_get_query_params()


def _clear_query_params() -> None:
    try:
        st.query_params.clear()  # type: ignore[attr-defined]
    except Exception:
        st.experimental_set_query_params()


def build_self_link(page: str, ticker: Optional[str] = None) -> str:
    params = {"page": page}
    if ticker:
        params["ticker"] = ticker
        params["auto"] = "1"
    return "?" + urlencode(params)


# -------------------- App state + actions --------------------
def set_page(name: str) -> None:
    st.session_state.page = name


def clear_all() -> None:
    st.session_state.results = None
    st.session_state.ticker_value = ""
    st.session_state.input_key = f"ticker_input_{time.time_ns()}"


# -------------------- (3) THROTTLE: soft, per-session rate limit --------------------
# Goal: stop users from hammering SEC endpoints and getting 429/403.
# - One lookup every ~1.1s (tweakable)
# - Enforced only on submit_lookup (the place that triggers SEC calls)
THROTTLE_SECONDS = 1.1


def _throttle_or_block() -> Optional[str]:
    now = time.time()
    last = float(st.session_state.get("_last_lookup_ts", 0.0))
    elapsed = now - last
    if elapsed < THROTTLE_SECONDS:
        wait = THROTTLE_SECONDS - elapsed
        return f"Please wait {wait:.1f}s and try again (rate limit)."
    st.session_state["_last_lookup_ts"] = now
    return None


# --- Progress UI pinned under LEFT panel buttons ---
def init_lookup_progress_slots() -> None:
    if "lookup_progress_bar" not in st.session_state:
        st.session_state.lookup_progress_bar = st.empty()
    if "lookup_progress_status" not in st.session_state:
        st.session_state.lookup_progress_status = st.empty()


def _progress_set(p: int, msg: str) -> None:
    p = max(0, min(100, int(p)))
    try:
        st.session_state.lookup_progress_bar.progress(p, text=msg)  # type: ignore[attr-defined]
        st.session_state.lookup_progress_status.empty()
    except TypeError:
        st.session_state.lookup_progress_bar.progress(p)
        st.session_state.lookup_progress_status.info(msg)


def _progress_clear() -> None:
    try:
        st.session_state.lookup_progress_bar.empty()
    except Exception:
        pass
    try:
        st.session_state.lookup_progress_status.empty()
    except Exception:
        pass


def _friendly_sec_error(e: Exception) -> str:
    s = str(e)
    code = None
    if isinstance(e, requests.HTTPError):
        try:
            code = e.response.status_code  # type: ignore[union-attr]
        except Exception:
            code = None
    if code in (403, 429):
        return (
            "SEC temporarily blocked or rate-limited requests.\n\n"
            "- Wait 30–60 seconds and try again.\n"
            "- Make sure SEC_CONTACT_EMAIL is set in Streamlit Secrets.\n"
            "- Avoid rapid repeated lookups."
        )
    if code and 500 <= code <= 599:
        return "SEC server error. Try again in a minute."
    if "timeout" in s.lower():
        return "Request timed out. Try again."
    return f"Request failed: {s}"


def submit_lookup() -> None:
    ticker = (st.session_state.get("ticker_value", "") or "").strip().upper()
    if not ticker:
        st.session_state.results = {"error": "Enter a ticker."}
        return

    # (3) apply throttle BEFORE any calls
    throttle_msg = _throttle_or_block()
    if throttle_msg:
        st.session_state.results = {"error": throttle_msg}
        return

    if "lookup_progress_bar" not in st.session_state or "lookup_progress_status" not in st.session_state:
        st.session_state.lookup_progress_bar = st.empty()
        st.session_state.lookup_progress_status = st.empty()

    try:
        _progress_set(10, "Starting lookup…")
        _progress_set(20, "Loading SEC ticker→CIK map…")
        mapping = get_ticker_cik_map()

        _progress_set(40, f"Finding CIK for {ticker}…")
        cik_int = mapping.get(ticker)
        if not cik_int:
            st.session_state.results = {"error": f"Ticker '{ticker}' not found in SEC mapping file."}
            return

        _progress_set(65, "Fetching SEC submissions…")
        submissions = get_company_submissions(cik_int)

        _progress_set(85, "Building results…")
        st.session_state.results = build_results(submissions, ticker, cik_int)

        _progress_set(100, "Done")
        time.sleep(0.15)

    except Exception as e:
        st.session_state.results = {"error": _friendly_sec_error(e)}

    finally:
        _progress_clear()


# -------------------- UI helpers --------------------
def topbar() -> None:
    st.markdown(
        """
        <div class="topbar">
          <div class="brand">SEC Filings Finder</div>
          <div class="sub">Primary-source due diligence. Type a US ticker and press Enter.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def nav_row(active: str) -> None:
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1], gap="small")
    with c1:
        st.button("Lookup", key="nav_lookup", use_container_width=True, disabled=(active == "lookup"),
                  on_click=set_page, args=("lookup",))
    with c2:
        st.button("Directory", key="nav_directory", use_container_width=True, disabled=(active == "directory"),
                  on_click=set_page, args=("directory",))
    with c3:
        st.button("How to Use", key="nav_howto", use_container_width=True, disabled=(active == "howto"),
                  on_click=set_page, args=("howto",))
    with c4:
        st.button("About", key="nav_about", use_container_width=True, disabled=(active == "about"),
                  on_click=set_page, args=("about",))
    with c5:
        st.button("Clear", key="nav_clear", use_container_width=True, on_click=clear_all)


def render_filing_card(f: Dict[str, Any]) -> None:
    filed = f.get("filing_date", "")
    age = f.get("days_since")
    period = f.get("period", "")

    meta_bits = []
    if filed:
        meta_bits.append(f"Filed {filed}")
    if isinstance(age, int):
        meta_bits.append(f"{age} days ago")
    if period:
        meta_bits.append(f"Period {period}")
    meta = " · ".join(meta_bits)

    st.markdown(
        f"""
        <div class="panel">
          <div class="filing-title"><a href="{f['url']}" target="_blank">{f['form']}</a></div>
          <div class="meta">{meta}</div>
          <div class="meta">Accession {f['accession']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def workflow_dropdown() -> None:
    with st.expander("Workflow", expanded=False):
        st.markdown(
            """
            <div class="wf-grid">
              <div class="wf-row">
                <div class="wf-head">
                  <div class="wf-form">10-K / 20-F</div>
                  <div class="wf-tag">Annual baseline</div>
                </div>
                <div class="wf-body">
                  Full business overview, risks, audited financials, long-term strategy.
                  <br/><span class="muted2">20-F is the foreign issuer equivalent of a 10-K.</span>
                </div>
              </div>

              <div class="wf-row">
                <div class="wf-head">
                  <div class="wf-form">10-Q</div>
                  <div class="wf-tag">Quarterly trends</div>
                </div>
                <div class="wf-body">
                  Quarterly performance updates, margins, liquidity, balance sheet movement.
                </div>
              </div>

              <div class="wf-row">
                <div class="wf-head">
                  <div class="wf-form">8-K / 6-K</div>
                  <div class="wf-tag">Material events</div>
                </div>
                <div class="wf-body">
                  Major events between reports: deals, leadership changes, financing updates.
                  <br/><span class="muted2">6-K is the foreign issuer equivalent of an 8-K.</span>
                </div>
              </div>

              <div class="wf-row">
                <div class="wf-head">
                  <div class="wf-form">DEF 14A</div>
                  <div class="wf-tag">Governance</div>
                </div>
                <div class="wf-body">
                  Executive compensation, board structure, voting items, shareholder power.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# -------------------- Pages --------------------
def page_lookup() -> None:
    topbar()
    nav_row("lookup")

    left, right = st.columns([1.0, 1.55], gap="large")

    with left:
        st.markdown("<div class='panel'>", unsafe_allow_html=True)
        st.markdown("### Ticker lookup")

        input_key = st.session_state.get("input_key", "ticker_input_0")

        def _enter_submit():
            st.session_state.ticker_value = st.session_state.get(input_key, "")
            submit_lookup()

        st.text_input(
            "Ticker",
            key=input_key,
            value=st.session_state.get("ticker_value", ""),
            placeholder="AAPL, MSFT, JPM, BIDU",
            label_visibility="collapsed",
            on_change=_enter_submit,
        )

        st.session_state.ticker_value = st.session_state.get(input_key, "")

        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            st.button(
                "Get filings",
                key="btn_get_filings",
                type="primary",
                use_container_width=True,
                on_click=submit_lookup,
            )
        with c2:
            st.button("Clear", key="btn_clear_panel", use_container_width=True, on_click=clear_all)

        init_lookup_progress_slots()

        st.markdown(f"<div class='muted' style='margin-top:10px;'>{DISCLAIMER_ONE_LINER}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        workflow_dropdown()

    with right:
        r = st.session_state.get("results")

        if isinstance(r, dict) and r.get("error"):
            st.error(r["error"])
            return

        if not r:
            st.markdown(
                """
                <div class="panel">
                  <div style="font-weight:900;">No company loaded yet.</div>
                  <div class="muted">Type a ticker and press Enter, or open one from Directory.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        last_close = get_last_close_best_effort(r["ticker"])
        price_line = f"${last_close:,.2f}" if last_close is not None else "N/A"

        st.markdown(
            f"""
            <a class="company-link" href="{r['browse_url']}" target="_blank">
              <div class="panel">
                <div style="display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;">
                  <div style="font-size:1.20rem; font-weight:980;">{r['company_name']}</div>
                  <div class="muted2">{r['ticker']} · CIK {r['cik']}</div>
                </div>
                <div class="divider"></div>
                <div style="display:flex; gap:10px; align-items:baseline; flex-wrap:wrap;">
                  <div class="muted">Last close</div>
                  <div style="font-weight:950;">{price_line}</div>
                </div>
              </div>
            </a>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Form glossary", expanded=False):
            for k, v in FORM_GLOSSARY.items():
                st.markdown(f"**{k}** — {v}")

        st.markdown("### Latest filings")
        if not r["latest"]:
            st.info("No recent filings found in SEC 'recent'. Use SEC EDGAR to view all filings.")
        else:
            for f in r["latest"]:
                render_filing_card(f)

        st.markdown("### Filing history")
        for form in FORMS_TO_SHOW:
            limit = HISTORY_LIMITS.get(form, 5)
            rows = r["history"].get(form, [])
            with st.expander(f"{form} — last {min(limit, len(rows))}", expanded=False):
                if not rows:
                    st.info("No filings found in SEC 'recent'.")
                else:
                    for f in rows:
                        render_filing_card(f)


def page_directory() -> None:
    topbar()
    nav_row("directory")

    entries, stats = get_ticker_entries()

    st.markdown(
        f"""
        <div class="panel">
          <div style="display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap;">
            <div style="font-weight:950;">Directory</div>
            <div class="muted2">
              Loaded <b>{stats['kept']:,}</b> tickers
              <span style="opacity:.6;">(raw: {stats['raw_rows']:,}, skipped: {stats['raw_rows']-stats['kept']:,})</span>
            </div>
          </div>
          <div class="muted">Search tickers or company names. Click any row to open filings.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    q = st.text_input(
        "Search",
        key="dir_search",
        placeholder="Search: ticker (AAPL) or name (Apple)",
        label_visibility="collapsed",
    )
    q_norm = (q or "").strip().lower()

    filtered = [e for e in entries if (q_norm in e["ticker"].lower() or q_norm in e["title"].lower())] if q_norm else entries

    page_size = 100
    total = len(filtered)
    pages = max(1, (total + page_size - 1) // page_size)

    if "dir_page" not in st.session_state:
        st.session_state.dir_page = 1
    st.session_state.dir_page = max(1, min(int(st.session_state.dir_page), pages))

    def _prev_page():
        st.session_state.dir_page = max(1, int(st.session_state.dir_page) - 1)

    def _next_page():
        st.session_state.dir_page = min(pages, int(st.session_state.dir_page) + 1)

    p1, p2, p3, p4 = st.columns([1, 1.4, 1, 2.2], gap="small")

    with p1:
        st.button("← Prev", use_container_width=True, disabled=(st.session_state.dir_page <= 1),
                  on_click=_prev_page, key="dir_prev")

    with p2:
        st.selectbox(
            "Page",
            options=list(range(1, pages + 1)),
            key="dir_page",
            label_visibility="collapsed",
        )

    with p3:
        st.button("Next →", use_container_width=True, disabled=(st.session_state.dir_page >= pages),
                  on_click=_next_page, key="dir_next")

    with p4:
        st.markdown(
            f"<div class='muted' style='padding-top:10px;'>"
            f"Results: <b>{total:,}</b> · Page <b>{st.session_state.dir_page}</b> / <b>{pages}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )

    page = int(st.session_state.dir_page)
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    slice_ = filtered[start:end]

    for idx, e in enumerate(slice_):
        row_link = build_self_link("lookup", e["ticker"])
        alt_class = "dir-alt" if (idx % 2 == 1) else ""
        st.markdown(
            f"""
            <a class="dir-link {alt_class}" href="{row_link}" target="_self" rel="noopener">
              <div class="dir-top">
                <div class="dir-ticker">{e['ticker']}</div>
                <div class="dir-cik">CIK {e['cik']}</div>
              </div>
              <span class="dir-hairline"></span>
              <div class="dir-title">{e['title']}</div>
            </a>
            """,
            unsafe_allow_html=True,
        )


def page_howto() -> None:
    topbar()
    nav_row("howto")

    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown("## How to Use")

    st.markdown("### Official SEC resources")
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.link_button("Search Filings", SEC_LINKS["Search Filings"])
        st.link_button("EDGAR Full Text Search", SEC_LINKS["EDGAR Full Text Search"])
    with c2:
        st.link_button("Using EDGAR to Research", SEC_LINKS["Using EDGAR to Research Investments"])
        st.link_button("EDGAR Search Assistance", SEC_LINKS["EDGAR Search Assistance Hub"])
    with c3:
        st.link_button("How to Read a 10-K", SEC_LINKS["How to Read a 10-K (Investor Bulletin)"])
        st.link_button("10-K/10-Q Fast Answers", SEC_LINKS["How to Read a 10-K/10-Q (Fast Answers)"])

    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    def howto_section(form: str, body_md: str):
        cols = st.columns([3, 1], gap="small")
        with cols[0]:
            st.markdown(f"### {form}")
        with cols[1]:
            st.link_button("Read on SEC", FORM_READ_ON_SEC[form])
        with st.expander(f"Details: {form}", expanded=False):
            st.markdown(body_md)

    howto_section(
        "10-K",
        """
What to focus on:
- Business model & segments
- Risk Factors (watch what changed year-over-year)
- MD&A (the “why” behind the numbers)
- Financial statements + notes (debt, leases, contingencies)
- Cash flow quality (operating cash flow vs net income)
        """.strip(),
    )

    howto_section(
        "10-Q",
        """
What to focus on:
- What changed since the last 10-K (margins, demand, pricing)
- Liquidity (cash, revolver use, working capital)
- Guidance / outlook language
        """.strip(),
    )

    howto_section(
        "8-K",
        """
What to focus on:
- Deals & acquisitions (terms, conditions, financing)
- Leadership changes
- Financing updates (debt/equity, credit agreements)
        """.strip(),
    )

    howto_section(
        "DEF 14A",
        """
What to focus on:
- Executive compensation (what management is paid to do)
- Governance (board independence, voting structure, rights)
- Related-party transactions (conflicts)
        """.strip(),
    )

    howto_section(
        "20-F",
        """
What to focus on:
- Business overview and geographic exposure
- Risk factors (currency, regulatory, geopolitical)
- Reconciliation to U.S. GAAP (if applicable)
        """.strip(),
    )

    howto_section(
        "6-K",
        """
What to focus on:
- Material updates between annual reports
- Earnings releases and operational updates
- Strategic partnerships or restructurings
        """.strip(),
    )

    st.markdown("</div>", unsafe_allow_html=True)


def page_about() -> None:
    topbar()
    nav_row("about")
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.markdown(ABOUT_PAGE)
    st.markdown("</div>", unsafe_allow_html=True)


# -------------------- App --------------------
def main() -> None:
    st.set_page_config(page_title="SEC Filings Finder", layout="wide")
    inject_css()

    # Session defaults
    if "page" not in st.session_state:
        st.session_state.page = "lookup"
    if "results" not in st.session_state:
        st.session_state.results = None
    if "ticker_value" not in st.session_state:
        st.session_state.ticker_value = ""
    if "input_key" not in st.session_state:
        st.session_state.input_key = "ticker_input_0"
    if "auto_lookup" not in st.session_state:
        st.session_state.auto_lookup = False

    # Handle query-param routing (Directory row click)
    qp = _get_query_params()
    qp_page = (qp.get("page", [""])[0] if isinstance(qp.get("page"), list) else qp.get("page", "")) or ""
    qp_ticker = (qp.get("ticker", [""])[0] if isinstance(qp.get("ticker"), list) else qp.get("ticker", "")) or ""
    qp_auto = (qp.get("auto", [""])[0] if isinstance(qp.get("auto"), list) else qp.get("auto", "")) or ""

    if qp_page in {"lookup", "directory", "howto", "about"}:
        st.session_state.page = qp_page

    if qp_ticker:
        st.session_state.ticker_value = qp_ticker.strip().upper()
        st.session_state.input_key = f"ticker_input_{time.time_ns()}"

    if qp_auto == "1" and qp_ticker:
        st.session_state.page = "lookup"
        st.session_state.auto_lookup = True

    if qp:
        _clear_query_params()

    if st.session_state.auto_lookup:
        st.session_state.auto_lookup = False
        submit_lookup()

    page = st.session_state.page
    if page == "lookup":
        page_lookup()
    elif page == "directory":
        page_directory()
    elif page == "howto":
        page_howto()
    elif page == "about":
        page_about()
    else:
        page_lookup()

    st.markdown(f"<div class='muted' style='margin-top:14px;'>{DISCLAIMER_ONE_LINER}</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()


