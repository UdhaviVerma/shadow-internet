import os
from uuid import uuid4

import pytest
from redis import Redis
from sqlalchemy import create_engine, text


@pytest.mark.skipif(not os.getenv("INTEGRATION_DATABASE_URL"), reason="Requires explicit integration PostgreSQL")
def test_real_postgresql_transaction_and_schema():
    engine = create_engine(os.environ["INTEGRATION_DATABASE_URL"])
    try:
        with engine.begin() as connection:
            assert connection.execute(text("SELECT version()")).scalar().startswith("PostgreSQL")
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001_scans"
            tables = set(
                connection.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                ).scalars()
            )
            assert {"scans", "monitors"}.issubset(tables)
    finally:
        engine.dispose()


@pytest.mark.skipif(not os.getenv("INTEGRATION_REDIS_URL"), reason="Requires explicit integration Redis")
def test_real_redis_cache_expiry_and_admission_counter():
    redis = Redis.from_url(os.environ["INTEGRATION_REDIS_URL"])
    key = f"shadow-integration-{uuid4()}"
    try:
        assert redis.setex(key, 30, "evidence")
        assert redis.get(key) == b"evidence"
        assert 0 < redis.ttl(key) <= 30
        assert redis.incr(key + "-rate") == 1
        assert redis.incr(key + "-rate") == 2
    finally:
        redis.delete(key, key + "-rate")
