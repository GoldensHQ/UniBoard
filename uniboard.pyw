# -*- coding: utf-8 -*-
"""UniBoard entry point (no console window — for everyday launching)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.app import main  # noqa: E402

main()
