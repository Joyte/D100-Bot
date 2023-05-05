import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
from os import environ as ENV

load_dotenv()

engine = create_engine(ENV.get("DATABASE_URL"))
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


class RollHistories(Base):
    __tablename__ = "rollhistories"

    id = sqlalchemy.Column(
        sqlalchemy.Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    userid = sqlalchemy.Column(
        sqlalchemy.BigInteger,
        index=True,
        autoincrement=False,
        nullable=False,
    )
    dice = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    result = sqlalchemy.Column(sqlalchemy.Integer, nullable=False)
    time = sqlalchemy.Column(
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.sql.func.now(),
    )

    def __init__(self, userid: int, dice: int, result: int):
        self.userid = userid
        self.dice = dice
        self.result = result

    def __repr__(self):
        return f"<RollHistories {self.id=}>"


Base.metadata.create_all(engine)
