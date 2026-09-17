"""
Root app.py — entry point for Render / HF Spaces (Gradio SDK).
Delegates to gradio_app/app.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gradio_app"))

from app import demo, _load_data, _theme

_load_data()
demo.launch(
    server_name="0.0.0.0",
    server_port=int(os.environ.get("PORT", 7860)),
    show_error=True,
    theme=_theme,
)
