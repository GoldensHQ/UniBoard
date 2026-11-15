# -*- coding: utf-8 -*-
"""Точка входа UniBoard (с консолью — удобно для отладки)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import main  # noqa: E402

if __name__ == "__main__":
    main()
