"""
Root app.py — HF Spaces entry point (Gradio SDK).
Delegates to gradio_app/app.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gradio_app"))

from app import demo, _load_data, _theme

_load_data()
demo.launch(
    server_name="0.0.0.0",
    server_port=7860,
    show_error=True,
    theme=_theme,
)
