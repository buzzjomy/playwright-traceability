from backend.db import normalize_database_url


def test_bare_postgres_scheme_is_normalized_to_psycopg():
    # Fly.io (and Heroku-style platforms before it) hand out postgres://
    # URLs - SQLAlchemy 2.0 needs an explicit driver in the scheme.
    assert (
        normalize_database_url("postgres://user:pass@host:5432/dbname")
        == "postgresql+psycopg://user:pass@host:5432/dbname"
    )


def test_plain_postgresql_scheme_is_normalized_to_psycopg():
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/dbname")
        == "postgresql+psycopg://user:pass@host:5432/dbname"
    )


def test_already_explicit_driver_scheme_is_left_unchanged():
    assert (
        normalize_database_url("postgresql+psycopg://user:pass@host:5432/dbname")
        == "postgresql+psycopg://user:pass@host:5432/dbname"
    )


def test_sqlite_url_is_left_unchanged():
    assert normalize_database_url("sqlite:///./somewhere.db") == "sqlite:///./somewhere.db"
