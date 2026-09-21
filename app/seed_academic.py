from app.database import SessionLocal
from app.models import Group, Subject, TeachingAssignment, User


def seed_academic_data():
    with SessionLocal() as db:
        teacher = (
            db.query(User)
            .filter(User.username == "teacher")
            .first()
        )

        if not teacher:
            print("Преподаватель teacher не найден.")
            return

        group = (
            db.query(Group)
            .filter(Group.name == "ИС-11")
            .first()
        )

        if not group:
            group = Group(
                name="ИС-11",
                is_active=True,
            )
            db.add(group)
            db.flush()

        subject = (
            db.query(Subject)
            .filter(Subject.code == "PY-01")
            .first()
        )

        if not subject:
            subject = Subject(
                name="Программирование",
                code="PY-01",
                is_active=True,
            )
            db.add(subject)
            db.flush()

        assignment = (
            db.query(TeachingAssignment)
            .filter(
                TeachingAssignment.teacher_id == teacher.id,
                TeachingAssignment.subject_id == subject.id,
                TeachingAssignment.group_id == group.id,
            )
            .first()
        )

        if not assignment:
            assignment = TeachingAssignment(
                teacher_id=teacher.id,
                subject_id=subject.id,
                group_id=group.id,
                is_active=True,
            )
            db.add(assignment)

        db.commit()

        print("Учебные тестовые данные добавлены.")


if __name__ == "__main__":
    seed_academic_data()