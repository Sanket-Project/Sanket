"""Backend application package.

The API reuses a few lightweight, pure-Python helpers from the sibling
``backend/ml/sanket_ml`` package. In local development that package is not
installed into the API virtualenv, so expose the source tree on Python's
import path before routers import those helpers lazily.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ML_SRC = Path(__file__).resolve().parents[1] / "ml"
if _ML_SRC.is_dir():
    _ml_src_str = str(_ML_SRC)
    if _ml_src_str not in sys.path:
        sys.path.insert(0, _ml_src_str)
