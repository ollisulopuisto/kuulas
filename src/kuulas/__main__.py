"""``python -m kuulas``: the entry point of the app bundle (see ``bundle.py``)."""

import sys

from .bundle import main

sys.exit(main())
