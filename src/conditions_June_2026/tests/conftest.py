import sys
from pathlib import Path

import pytest

# Make `import ingest` work when pytest is run from any directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
