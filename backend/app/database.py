from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from backend.app.config import settings


@lru_cache(maxsize=1)
def _get_engine():
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


def get_session():
    engine = _get_engine()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


Base = declarative_base()


def init_db():
    from backend.app import db_models
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)


def _get_seed_wallets():
    wallets = {}
    if settings.alice_onchain_address:
        wallets["ALICE"] = settings.alice_onchain_address
    if settings.bob_onchain_address:
        wallets["BOB"] = settings.bob_onchain_address
    return wallets


def seed_db():
    from backend.app.db_models import Account, Wallet
    session = get_session()
    try:
        if session.query(Account).count() == 0:
            alice = Account(client_id="ALICE", available=100_000, reserved=0)
            bob = Account(client_id="BOB", available=0, reserved=0)
            session.add_all([alice, bob])

        for cid, addr in _get_seed_wallets().items():
            existing = session.get(Wallet, cid)
            if existing is None:
                session.add(Wallet(client_id=cid, onchain_address=addr))

        session.commit()
    finally:
        session.close()


def load_wallets():
    from backend.app.db_models import Wallet
    session = get_session()
    try:
        rows = session.query(Wallet).all()
        return {row.client_id: row.onchain_address for row in rows}
    finally:
        session.close()
