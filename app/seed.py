from app.database import SessionLocal
from app.models import User
from app.auth import password_hash


def seed_users():
    with SessionLocal() as db:
        existing_users = db.query(User).count()

        if existing_users > 0:
            print("Пользователи уже существуют. Ничего не добавляем.")
            return

        student = User(
            username="student",
            password_hash=password_hash.hash("student123"),
            full_name="Тестовый студент",
            role="student",
            is_active=True,
        )

        teacher = User(
            username="teacher",
            password_hash=password_hash.hash("teacher123"),
            full_name="Тестовый преподаватель",
            role="teacher",
            is_active=True,
        )

        db.add_all([student, teacher])
        db.commit()

        print("Тестовые пользователи добавлены.")


if __name__ == "__main__":
    seed_users()