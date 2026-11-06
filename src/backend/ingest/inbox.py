"""Inbox: quarantine incoming files, preview them, and file them under data/weather/raw.

Flow:  receive() -> classify.classify() -> preview() -> [user confirms] -> confirm()
Nothing in data/weather/raw is ever overwritten. Every confirmed file is recorded in
data/weather/raw/manifest.json (hash, category, is_sample, time), which run.py reads.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from . import schema
from .classify import PERIOD_RE, Proposal
from .config import RAW_DIR, REQUESTED_MONTHS
from .registry import CATEGORIES, UNKNOWN, Source

INBOX_DIR = RAW_DIR.parent / "inbox"
MANIFEST = "manifest.json"
MAX_BYTES = 200 * 1024 * 1024          # refuse files above 200 MB
NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class InboxError(Exception):
    """A user-facing problem (bad name, duplicate, missing field, ...)."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str) -> str:
    """Strip any directory part and odd characters; keep the extension."""
    base = Path(name.replace("\\", "/")).name
    base = NAME_RE.sub("_", base).strip("._") or "file"
    return base[:120]


# --- manifest ----------------------------------------------------------------------

def load_manifest(raw_dir: Path = RAW_DIR) -> dict:
    p = raw_dir / MANIFEST
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _save_manifest(manifest: dict, raw_dir: Path) -> None:
    p = raw_dir / MANIFEST
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    tmp.replace(p)


def find_duplicate(src: Path, digest: str, raw_dir: Path = RAW_DIR) -> Optional[str]:
    """Relative path of an identical file already in raw_dir (manifest or same-size scan)."""
    for rel, entry in load_manifest(raw_dir).items():
        if entry.get("sha256") == digest:
            return rel
    size = src.stat().st_size
    for p in raw_dir.rglob("*"):   # files stored before the manifest existed
        if p.is_file() and p.name != MANIFEST and p.stat().st_size == size and sha256(p) == digest:
            return p.relative_to(raw_dir).as_posix()
    return None


# --- receiving -----------------------------------------------------------------------

def receive(name: str, data: bytes, inbox: Path = INBOX_DIR) -> Path:
    """Store uploaded bytes in the inbox under a safe, unique name."""
    if len(data) > MAX_BYTES:
        raise InboxError(f"{name}: file is larger than {MAX_BYTES // 2**20} MB")
    inbox.mkdir(parents=True, exist_ok=True)
    base = safe_name(name)
    stem = base.split(".")[0]
    target, n = inbox / base, 1
    while target.exists():
        target = inbox / f"{stem}_{n}{base[len(stem):]}"
        n += 1
    target.write_bytes(data)
    return target


def pending(inbox: Path = INBOX_DIR) -> list[Path]:
    if not inbox.exists():
        return []
    return sorted(p for p in inbox.iterdir() if p.is_file() and not p.name.startswith("."))


# --- naming and preview ----------------------------------------------------------------

def target_path(src: Path, proposal: Proposal, raw_dir: Path = RAW_DIR) -> Path:
    cat = CATEGORIES[proposal.category]
    if cat.key == UNKNOWN.key:
        raise InboxError("choose a category first")
    missing = proposal.missing_fields()
    if missing:
        raise InboxError(f"please fill in: {', '.join(missing)}")
    if proposal.period and not PERIOD_RE.match(proposal.period):
        raise InboxError("period must be YYYYMM (or YYYY for a whole year)")
    if cat.filename is None:
        name = safe_name(src.name)
    else:
        ext = ".txt.gz" if src.name.endswith(".gz") else ".txt"
        name = cat.filename.format(
            source_id=safe_name(proposal.source_id or ""), period=proposal.period or "",
            ext=ext, product=proposal.extra.get("product", "met"))
    return raw_dir / cat.subdir / name


@dataclass
class Preview:
    rows: int
    rows_in_months: int
    first: Optional[str]
    last: Optional[str]
    problems: list[str]
    sample: pd.DataFrame
    error: Optional[str] = None


def preview(src: Path, proposal: Proposal, months=REQUESTED_MONTHS) -> Optional[Preview]:
    """Dry-run the category's parser on a copy named like the final file."""
    cat = CATEGORIES[proposal.category]
    if not isinstance(cat, Source) or cat.parse is None:
        return None
    try:
        final = target_path(src, proposal, Path("raw"))
    except InboxError as e:
        return Preview(0, 0, None, None, [], pd.DataFrame(), error=str(e))
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / final.name
        shutil.copyfile(src, copy)
        try:
            # ndbc filters months itself; ask for all so the count below is honest
            df = cat.parse(copy, months=None) if cat.key == "ndbc" else cat.parse(copy)
        except Exception as e:
            return Preview(0, 0, None, None, [], pd.DataFrame(), error=f"parser failed: {e}")
    if df.empty:
        return Preview(0, 0, None, None, [], df, error="the parser found no rows")
    in_months = int(df["time_utc"].dt.month.isin(months).sum())
    return Preview(rows=len(df), rows_in_months=in_months,
                   first=str(df["time_utc"].min()), last=str(df["time_utc"].max()),
                   problems=schema.validate(df, cat.table), sample=df.head(5))


# --- confirm / reject ------------------------------------------------------------------

def confirm(src: Path, proposal: Proposal, is_sample: bool = False,
            raw_dir: Path = RAW_DIR) -> Path:
    """Move an inbox file to its place under data/weather/raw and record it in the manifest."""
    digest = sha256(src)
    dup = find_duplicate(src, digest, raw_dir)
    if dup:
        raise InboxError(f"identical file already stored as {dup}")
    dest = target_path(src, proposal, raw_dir)
    if dest.exists():
        raise InboxError(f"{dest.relative_to(raw_dir)} already exists; not overwriting")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), dest)

    manifest = load_manifest(raw_dir)
    manifest[dest.relative_to(raw_dir).as_posix()] = {
        "sha256": digest,
        "original_name": src.name,
        "category": proposal.category,
        "source_id": proposal.source_id,
        "period": proposal.period,
        "is_sample": bool(is_sample),
        "classified_by": proposal.method,
        "confidence": proposal.confidence,
        "confirmed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    _save_manifest(manifest, raw_dir)
    return dest


def reject(src: Path, inbox: Path = INBOX_DIR) -> Path:
    """Keep rejected files out of the way (never deleted automatically)."""
    dest_dir = inbox / ".rejected"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.move(str(src), dest)
    return dest


def proposal_dict(p: Proposal) -> dict:
    return asdict(p)
