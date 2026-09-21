from app.database import SessionLocal
from app.models import User
from app.auth import password_hash


def create_user_if_missing(
    db,
    username: str,
    password: str,
    full_name: str,
    role: str,
):
    existing_user = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

    if existing_user:
        print(f"Пользователь {username} уже существует.")
        return

    user = User(
        username=username,
        password_hash=password_hash.hash(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )

    db.add(user)

    print(f"Пользователь {username} добавлен.")


def seed_users():
    with SessionLocal() as db:
        create_user_if_missing(
            db,
            username="admin",
            password="admin123",
            full_name="Администратор портала",
            role="admin",
        )

        create_user_if_missing(
            db,
            username="student",
            password="student123",
            full_name="Тестовый студент",
            role="student",
        )

        create_user_if_missing(
            db,
            username="teacher",
            password="teacher123",
            full_name="Тестовый преподаватель",
            role="teacher",
        )

        db.commit()

        print("Проверка пользователей завершена.")


if __name__ == "__main__":
    seed_users()

