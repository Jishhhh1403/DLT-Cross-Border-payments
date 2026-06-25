import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.db_models import Account


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    alice = Account(client_id="ALICE", available=100_000, reserved=0)
    bob = Account(client_id="BOB", available=0, reserved=0)
    db.add_all([alice, bob])
    db.commit()
    try:
        yield db
    finally:
        db.close()
