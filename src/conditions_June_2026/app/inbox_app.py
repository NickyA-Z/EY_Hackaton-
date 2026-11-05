"""Location Agent - file inbox (Streamlit).

Drop any file in; the app proposes what it is and where it belongs, you confirm,
then it is filed under data/raw and the common tables are rebuilt.

Run from src/conditions_June_2026:
    ../../.venv/bin/streamlit run app/inbox_app.py
Set ANTHROPIC_API_KEY to let Claude classify files the built-in rules don't know.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest import inbox, run                                   # noqa: E402
from ingest.classify import Proposal, classify                  # noqa: E402
from ingest.config import RAW_DIR, REQUESTED_MONTHS             # noqa: E402
from ingest.registry import CATEGORIES, UNKNOWN, Source         # noqa: E402

st.set_page_config(page_title="Location Agent – Inbox", page_icon="📥", layout="wide")
state = st.session_state
state.setdefault("uploader_key", 0)
state.setdefault("proposals", {})     # file fingerprint -> Proposal
state.setdefault("flash", [])         # messages to show after a rerun

CATEGORY_KEYS = list(CATEGORIES)


def fingerprint(p: Path) -> str:
    s = p.stat()
    return f"{p.name}:{s.st_size}:{int(s.st_mtime)}"


def label(key: str) -> str:
    cat = CATEGORIES[key]
    kind = "parser" if isinstance(cat, Source) else "store only" if key != UNKNOWN.key else "?"
    return f"{key}  ·  {kind}"


# --- sidebar ---------------------------------------------------------------------------
llm_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
with st.sidebar:
    st.header("Settings")
    use_llm = st.toggle("Ask Claude about unknown files", value=llm_ready,
                        help="Only the file name, size and first 40 lines are sent.")
    if use_llm and not llm_ready:
        st.warning("ANTHROPIC_API_KEY is not set – Claude can’t be reached; rules only.")
    st.caption(f"Months kept in the tables: {', '.join(map(str, REQUESTED_MONTHS))}")
    if st.button("Rebuild tables now"):
        with st.spinner("Rebuilding observations and tide_events…"):
            tables = run.build()
        st.success(f"observations: {len(tables['observations']):,} rows · "
                   f"tide_events: {len(tables['tide_events']):,} rows")

st.title("📥 File inbox")
st.write("Add data in any format. The app proposes a category and a place under "
         "`data/raw`; nothing is stored until you confirm.")

for kind, msg in state.flash:
    getattr(st, kind)(msg)
state.flash = []

# --- 1. receive ---------------------------------------------------------------------------
uploads = st.file_uploader("Drop files here", accept_multiple_files=True,
                           key=f"uploader_{state.uploader_key}")
if uploads:
    for f in uploads:
        try:
            inbox.receive(f.name, f.getvalue())
        except inbox.InboxError as e:
            state.flash.append(("error", str(e)))
    state.uploader_key += 1          # clear the widget so files aren't added twice
    st.rerun()
st.caption(f"You can also copy files into `{inbox.INBOX_DIR.relative_to(RAW_DIR.parent.parent)}` "
           "and press **Refresh**.")
st.button("Refresh")

# --- 2. review each pending file -------------------------------------------------------------
files = inbox.pending()
if not files:
    st.info("The inbox is empty.")

for path in files:
    fp = fingerprint(path)
    if fp not in state.proposals:
        with st.spinner(f"Classifying {path.name}…"):
            state.proposals[fp] = classify(path, use_llm=use_llm and llm_ready)
    proposal: Proposal = state.proposals[fp]

    with st.container(border=True):
        st.subheader(path.name)
        st.caption(f"{path.stat().st_size:,} bytes")
        how = {"rule": "format rule", "llm": "Claude", "none": "nobody"}[proposal.method]
        st.markdown(f"**Proposal:** `{proposal.category}` · confidence {proposal.confidence:.0%} "
                    f"· by {how} — {proposal.reason}")
        if proposal.note:
            st.warning(proposal.note)

        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        category = c1.selectbox("Category", CATEGORY_KEYS, format_func=label,
                                index=CATEGORY_KEYS.index(proposal.category), key=f"cat_{fp}")
        cat = CATEGORIES[category]
        st.caption(cat.description)
        needs = cat.needs
        source_id = c2.text_input("Source id", proposal.source_id or "", key=f"sid_{fp}",
                                  disabled="source_id" not in needs,
                                  help="Station, buoy or point, e.g. 9410670")
        period = c3.text_input("Period (YYYYMM or YYYY)", proposal.period or "", key=f"per_{fp}",
                               disabled="period" not in needs)
        product = proposal.extra.get("product", "met")
        if category == "coops":
            product = c4.selectbox("Product", ["wind", "air_temperature", "water_temperature", "met"],
                                   index=["wind", "air_temperature", "water_temperature", "met"].index(product),
                                   key=f"prod_{fp}")
        is_sample = st.checkbox("Hand-made sample file (is_sample = true)", key=f"sample_{fp}")

        edited = Proposal(category=category, confidence=proposal.confidence, method=proposal.method,
                          reason=proposal.reason, source_id=source_id.strip() or None,
                          period=period.strip() or None, extra={"product": product})
        try:
            dest = inbox.target_path(path, edited)
            st.markdown(f"**Will be stored as:** `{dest.relative_to(RAW_DIR.parent.parent)}`")
            ready = True
        except inbox.InboxError as e:
            st.error(str(e))
            ready = False
        dup = inbox.find_duplicate(path, inbox.sha256(path))
        if dup:
            st.error(f"An identical file is already stored as `{dup}` – reject this one.")
            ready = False
        elif ready and dest.exists():
            st.error(f"`{dest.name}` already exists with different content – "
                     "check the source id / period, or rename.")
            ready = False

        pv = inbox.preview(path, edited) if ready else None
        if pv is not None:
            if pv.error:
                st.error(f"Dry run: {pv.error}")
                ready = False
            else:
                m1, m2, m3 = st.columns(3)
                m1.metric("Rows parsed", f"{pv.rows:,}")
                m2.metric(f"Rows in months {REQUESTED_MONTHS}", f"{pv.rows_in_months:,}")
                m3.metric("Time range (UTC)", f"{pv.first[:10]} → {pv.last[:10]}")
                if pv.rows_in_months == 0:
                    st.warning("No rows fall in the months the tables keep; nothing will show up.")
                for p in pv.problems:
                    st.warning(f"Check: {p}")
                st.dataframe(pv.sample, hide_index=True, width="stretch")
        elif ready:
            st.info("No parser for this category yet – the file will be stored, not loaded into the tables.")

        b1, b2, _ = st.columns([2, 1, 5])
        if b1.button("Confirm & process", key=f"ok_{fp}", type="primary", disabled=not ready):
            try:
                dest = inbox.confirm(path, edited, is_sample=is_sample)
            except inbox.InboxError as e:
                state.flash.append(("error", f"{path.name}: {e}"))
            else:
                msg = f"Stored {path.name} as {dest.relative_to(RAW_DIR)}."
                if isinstance(cat, Source):
                    with st.spinner("Rebuilding tables…"):
                        tables = run.build()
                    msg += (f" Tables rebuilt: observations {len(tables['observations']):,} rows, "
                            f"tide_events {len(tables['tide_events']):,} rows.")
                state.flash.append(("success", msg))
            state.proposals.pop(fp, None)
            st.rerun()
        if b2.button("Reject", key=f"no_{fp}"):
            inbox.reject(path)
            state.flash.append(("info", f"Moved {path.name} to inbox/.rejected"))
            state.proposals.pop(fp, None)
            st.rerun()

# --- 3. recently stored -----------------------------------------------------------------------
manifest = inbox.load_manifest()
if manifest:
    st.divider()
    st.subheader("Recently stored")
    recent = sorted(manifest.items(), key=lambda kv: kv[1].get("confirmed_at", ""), reverse=True)[:10]
    st.dataframe([{"file": k, "category": v["category"], "from": v["original_name"],
                   "sample": v["is_sample"], "by": v["classified_by"], "when (UTC)": v["confirmed_at"]}
                  for k, v in recent], hide_index=True, width="stretch")
