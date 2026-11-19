"""Train the oxygen-drop model from the repository root: `python ml/train.py`.

The code lives in backend/app/ml (it is used by the API and the pipeline too); this file just runs it.
"""

import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from app.ml.train import main  # noqa: E402

if __name__ == "__main__":
    main()
