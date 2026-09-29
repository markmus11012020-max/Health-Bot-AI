"""Centralized Streamlit CSS styles."""
from __future__ import annotations

CUSTOM_CSS = """
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #2E7D32;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .compliance-badge {
        background: #E8F5E9;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        text-align: center;
        font-size: 0.85rem;
        color: #2E7D32;
        margin-bottom: 2rem;
    }
    .block-client {
        background: #E3F2FD;
        border-left: 4px solid #2196F3;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .block-manager {
        background: #E8F5E9;
        border-left: 4px solid #4CAF50;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
</style>
"""

FOOTER_HTML = (
    "<p style='text-align: center; color: #999; font-size: 0.8rem;'>"
    "Health-Bot-AI © 2024 | OCX | Демонстрационный MVP"
    "</p>"
)