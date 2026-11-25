from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend.data import dashboard_queries


def test_demo_pages_render_without_postgres(monkeypatch):
    monkeypatch.setenv("INVENTORY_DEMO", "1")

    def unexpected_connection():
        pytest.fail("Demo analytics attempted a PostgreSQL connection")

    monkeypatch.setattr(dashboard_queries, "get_connection", unexpected_connection)
    app_path = Path(__file__).resolve().parents[2] / "frontend" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=30).run()
    assert not app.exception
    assert not app.error
    assert app.metric[0].label == "Total Units Sold"

    for page in ("Sales Analytics", "Product Analytics", "Inventory Analytics", "Invoice Scanner"):
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
        assert not app.error, page
    assert app.header[0].value == "📄 Invoice Scanner"
