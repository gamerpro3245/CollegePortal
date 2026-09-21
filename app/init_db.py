from app.database import Base, engine
from app import models


def init_db():
    Base.metadata.create_all(bind=engine)
    print("База данных успешно создана.")


if __name__ == "__main__":
    init_db()