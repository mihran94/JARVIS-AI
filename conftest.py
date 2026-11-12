"""Repository level pytest configuration.

This file is imported by pytest before any test module, so it is the right
place to prepare the environment the tests need.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.qt_runtime import ensure_egl_runtime, missing_message

if not ensure_egl_runtime():
    raise RuntimeError(missing_message())
