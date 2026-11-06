"""The docs live in docs/ and must not rot when folders move again."""

import re

import pytest

from backend import paths
from backend.tests.test_paths import RETIRED_NAMES

DOCS = paths.ROOT / "docs"
STALE = (*RETIRED_NAMES, "frontend/frontend", "../backend")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _documents():
    return sorted([*DOCS.glob("*.md"), paths.ROOT / "README.md"])


def test_documentation_exists_where_it_should():
    names = {p.name for p in DOCS.glob("*.md")}
    assert {"README.md", "data.md", "frontend.md", "backend.md", "rag.md"} <= names
    for stray in ("README.md",):  # no per-package READMEs next to the code
        assert not any(p.name == stray for p in paths.SRC.rglob("*.md")), "documentation belongs in docs/"


@pytest.mark.parametrize("document", _documents(), ids=lambda p: p.name)
def test_relative_links_resolve(document):
    broken = [target for target in LINK.findall(document.read_text(encoding="utf-8"))
              if not target.startswith(("http://", "https://", "mailto:"))
              and not (document.parent / target).resolve().exists()]
    assert not broken, f"{document.name} links to missing files: {broken}"


@pytest.mark.parametrize("document", _documents(), ids=lambda p: p.name)
def test_no_retired_folder_names(document):
    text = document.read_text(encoding="utf-8")
    found = [name for name in STALE if name in text]
    assert not found, f"{document.name} still mentions {found}"
