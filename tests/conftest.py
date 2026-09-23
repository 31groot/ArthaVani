import pytest

from config.settings import settings


@pytest.fixture(autouse=True)
def disable_postgres_for_unit_tests(request, monkeypatch):
    """Keep ordinary tests independent of the local PostgreSQL instance."""
    if request.node.get_closest_marker("postgres"):
        return

    monkeypatch.setattr(settings, "DATABASE_URL", None)