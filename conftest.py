"""Make the repository root importable regardless of how pytest is invoked.

`pytest.ini` sets `pythonpath = .`, but that option needs pytest >= 7. This
conftest is version-independent belt-and-braces so `import client` works even
under a bare `pytest` invocation on a fresh CI runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
