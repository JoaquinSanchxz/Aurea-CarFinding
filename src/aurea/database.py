from sqlmodel import SQLModel, create_engine, Session
from aurea.config import load_settings

settings = load_settings()
engine = create_engine(
    settings.database.url,
    connect_args={"check_same_thread": False} if settings.database.url.startswith("sqlite") else {}
)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session() -> Session:
    return Session(engine)
