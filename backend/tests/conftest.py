import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main, worker
from app.auth import current_owner
from app.database import Base, get_db


@pytest.fixture
def workspace_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(main.settings, "queue_mode", "inline")
    monkeypatch.setattr(main.settings, "redis_url", None)
    monkeypatch.setattr(main.settings, "auth_mode", "demo")
    monkeypatch.setattr(main.settings, "openai_api_key", None)
    monkeypatch.setattr(main.settings, "scan_limit_per_hour", 10)
    owner = {"id": "test-owner"}

    def override_db():
        with factory() as session:
            yield session

    main.app.dependency_overrides[get_db] = override_db
    main.app.dependency_overrides[current_owner] = lambda: owner["id"]
    try:
        with TestClient(main.app) as client:
            yield client, factory, owner
    finally:
        main.app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
