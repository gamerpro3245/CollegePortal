from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    group: Mapped["Group | None"] = relationship(back_populates="students")
    teaching_assignments: Mapped[list["TeachingAssignment"]] = relationship(back_populates="teacher")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    course: Mapped[int] = mapped_column(default=1)
    is_active: Mapped[bool] = mapped_column(default=True)

    students: Mapped[list["User"]] = relationship(back_populates="group")
    teaching_assignments: Mapped[list["TeachingAssignment"]] = relationship(back_populates="group")
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(back_populates="group")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    code: Mapped[str | None] = mapped_column(String(30), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    teaching_assignments: Mapped[list["TeachingAssignment"]] = relationship(back_populates="subject")
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(back_populates="subject")


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

    teacher: Mapped["User"] = relationship(back_populates="teaching_assignments")
    subject: Mapped["Subject"] = relationship(back_populates="teaching_assignments")
    group: Mapped["Group"] = relationship(back_populates="teaching_assignments")
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(back_populates="teaching_assignment")


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    teaching_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("teaching_assignments.id"), nullable=True
    )
    day_of_week: Mapped[int] = mapped_column(nullable=False, index=True)
    lesson_number: Mapped[int] = mapped_column(default=1, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    room: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lesson_type: Mapped[str] = mapped_column(String(30), default="Занятие")
    is_active: Mapped[bool] = mapped_column(default=True)

    group: Mapped["Group"] = relationship(back_populates="schedule_entries")
    subject: Mapped["Subject"] = relationship(back_populates="schedule_entries")
    teacher: Mapped["User"] = relationship()
    teaching_assignment: Mapped["TeachingAssignment | None"] = relationship(
        back_populates="schedule_entries"
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    teacher: Mapped["User"] = relationship()
    subject: Mapped["Subject"] = relationship()
    group: Mapped["Group"] = relationship()
