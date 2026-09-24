from fastapi import Cookie, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
import jwt

from app.auth import ALGORITHM, SECRET_KEY, create_access_token, get_user_by_username, verify_password, password_hash
from app.database import Base, engine, get_db
from app.models import Assignment, Group, ScheduleEntry, Subject, TeachingAssignment, User

app = FastAPI(title="Портал колледжа")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates", context_processors=[lambda request: {"user": getattr(request.state, "user", None)}])

@app.on_event("startup")
def ensure_database_schema():
    Base.metadata.create_all(bind=engine)

@app.middleware("http")
async def load_current_user(request: Request, call_next):
    db = next(get_db())
    try:
        request.state.user = get_current_user(request.cookies.get("access_token"), db)
        return await call_next(request)
    finally:
        db.close()

def template_context(request: Request, **extra):
    context = {"user": getattr(request.state, "user", None)}
    context.update(extra)
    return context

def get_current_user(access_token: str | None, db: Session):
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
        user = db.scalars(select(User).where(User.username == username)).first()
        return user if user and user.is_active else None
    except jwt.PyJWTError:
        return None

def require_admin(access_token: str | None, db: Session):
    user = get_current_user(access_token, db)
    return user if user and user.role == "admin" else None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="index.html", context={"user": get_current_user(access_token, db)})

@app.head("/")
async def home_health():
    return Response(status_code=200)

@app.get("/healthz", response_class=HTMLResponse)
async def healthz():
    return "ok"

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_by_username(db, username)
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return RedirectResponse(url="/login?error=1", status_code=303)
    token = create_access_token(username=user.username, role=user.role)
    response = RedirectResponse(url={"student": "/student", "teacher": "/teacher", "admin": "/admin"}.get(user.role, "/"), status_code=303)
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", path="/")
    return response

@app.get("/student", response_class=HTMLResponse)
async def student_dashboard(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user or user.role != "student":
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="student.html", context={"user": user})

@app.get("/teacher/assignments/new", response_class=HTMLResponse)
async def teacher_assignment_new(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user or user.role != "teacher":
        return RedirectResponse(url="/login", status_code=303)
    assignments = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == user.id, TeachingAssignment.is_active.is_(True)).options(joinedload(TeachingAssignment.subject), joinedload(TeachingAssignment.group)).order_by(TeachingAssignment.id)).all()
    return templates.TemplateResponse(request=request, name="teacher_assignment_new.html", context=template_context(request, assignments=assignments))

@app.post("/teacher/assignments/create")
async def teacher_assignment_create(title: str = Form(...), description: str = Form(default=""), due_date: str = Form(default=""), teaching_assignment_id: int = Form(...), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user or user.role != "teacher":
        return RedirectResponse(url="/login", status_code=303)
    teaching = db.scalars(select(TeachingAssignment).where(TeachingAssignment.id == teaching_assignment_id, TeachingAssignment.teacher_id == user.id, TeachingAssignment.is_active.is_(True))).first()
    if not teaching or not title.strip():
        return RedirectResponse(url="/teacher/assignments/new?error=invalid", status_code=303)
    db.add(Assignment(title=title.strip(), description=description.strip() or None, due_date=due_date.strip() or None, teacher_id=user.id, subject_id=teaching.subject_id, group_id=teaching.group_id, is_active=True))
    db.commit()
    return RedirectResponse(url="/assignments?created=1", status_code=303)

@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user or user.role != "teacher":
        return RedirectResponse(url="/login", status_code=303)
    assignments = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == user.id, TeachingAssignment.is_active.is_(True)).options(joinedload(TeachingAssignment.subject), joinedload(TeachingAssignment.group)).order_by(TeachingAssignment.id)).all()
    return templates.TemplateResponse(request=request, name="teacher.html", context={"user": user, "assignments": assignments})

@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    query = select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True)).options(joinedload(ScheduleEntry.subject), joinedload(ScheduleEntry.group), joinedload(ScheduleEntry.teacher)).order_by(ScheduleEntry.day_of_week, ScheduleEntry.start_time)
    if user.role == "student":
        entries = db.scalars(query.where(ScheduleEntry.group_id == user.group_id)).all() if user.group_id else []
    elif user.role == "teacher":
        entries = db.scalars(query.where(ScheduleEntry.teacher_id == user.id)).all()
    else:
        entries = db.scalars(query).all()
    days = [(0, "Понедельник"), (1, "Вторник"), (2, "Среда"), (3, "Четверг"), (4, "Пятница")]
    schedule_by_day = {day_id: [] for day_id, _ in days}
    for entry in entries:
        schedule_by_day[entry.day_of_week].append(entry)
    return templates.TemplateResponse(request=request, name="schedule.html", context=template_context(request, days=days, schedule_by_day=schedule_by_day, schedule_entries=entries))

@app.get("/assignments", response_class=HTMLResponse)
async def assignments_page(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    query = select(Assignment).where(Assignment.is_active.is_(True)).options(joinedload(Assignment.subject), joinedload(Assignment.group), joinedload(Assignment.teacher)).order_by(Assignment.id.desc())
    if user.role == "student":
        assignments = db.scalars(query.where(Assignment.group_id == user.group_id)).all() if user.group_id else []
    elif user.role == "teacher":
        assignments = db.scalars(query.where(Assignment.teacher_id == user.id)).all()
    else:
        assignments = db.scalars(query).all()
    return templates.TemplateResponse(request=request, name="assignments.html", context=template_context(request, assignments=assignments))

@app.get("/grades", response_class=HTMLResponse)
async def grades_page(request: Request):
    return templates.TemplateResponse(request=request, name="grades.html", context=template_context(request))

@app.get("/attendance", response_class=HTMLResponse)
async def attendance_page(request: Request):
    return templates.TemplateResponse(request=request, name="attendance.html", context=template_context(request))

@app.get("/materials", response_class=HTMLResponse)
async def materials_page(request: Request):
    return templates.TemplateResponse(request=request, name="materials.html", context=template_context(request))

@app.get("/announcements", response_class=HTMLResponse)
async def announcements_page(request: Request):
    return templates.TemplateResponse(request=request, name="announcements.html", context=template_context(request))

@app.get("/freshman", response_class=HTMLResponse)
async def freshman_page(request: Request):
    return templates.TemplateResponse(request=request, name="freshman.html", context=template_context(request))

@app.get("/certificates", response_class=HTMLResponse)
async def certificates_page(request: Request):
    return templates.TemplateResponse(request=request, name="certificates.html", context=template_context(request))

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    student_count = len(db.scalars(select(User.id).where(User.role == "student", User.is_active.is_(True))).all())
    group_count = len(db.scalars(select(Group.id).where(Group.is_active.is_(True))).all())
    schedule_count = len(db.scalars(select(ScheduleEntry.id).where(ScheduleEntry.is_active.is_(True))).all())
    return templates.TemplateResponse(request=request, name="admin.html", context={"user": user, "student_count": student_count, "group_count": group_count, "schedule_count": schedule_count})

@app.get("/admin/students", response_class=HTMLResponse)
async def admin_students(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    students = db.scalars(select(User).where(User.role == "student").options(joinedload(User.group)).order_by(User.full_name)).all()
    groups = db.scalars(select(Group).where(Group.is_active.is_(True)).order_by(Group.name)).all()
    return templates.TemplateResponse(request=request, name="admin_students.html", context={"user": user, "students": students, "groups": groups})

@app.post("/admin/students/create")
async def admin_create_student(full_name: str = Form(...), username: str = Form(...), password: str = Form(...), group_id: int | None = Form(default=None), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if db.scalars(select(User).where(User.username == username)).first():
        return RedirectResponse(url="/admin/students?error=username", status_code=303)
    db.add(User(username=username, password_hash=password_hash.hash(password), full_name=full_name, role="student", group_id=group_id, is_active=True))
    db.commit()
    return RedirectResponse(url="/admin/students", status_code=303)

@app.get("/admin/academic", response_class=HTMLResponse)
async def admin_academic(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    groups = db.scalars(select(Group).where(Group.is_active.is_(True)).order_by(Group.name)).all()
    subjects = db.scalars(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.name)).all()
    teachers = db.scalars(select(User).where(User.role == "teacher", User.is_active.is_(True)).order_by(User.full_name)).all()
    assignments = db.scalars(select(TeachingAssignment).where(TeachingAssignment.is_active.is_(True)).options(joinedload(TeachingAssignment.teacher), joinedload(TeachingAssignment.subject), joinedload(TeachingAssignment.group)).order_by(TeachingAssignment.id.desc())).all()
    return templates.TemplateResponse(request=request, name="admin_academic.html", context={"user": user, "groups": groups, "subjects": subjects, "teachers": teachers, "assignments": assignments})

@app.post("/admin/academic/group")
async def admin_create_group(name: str = Form(...), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    name = name.strip()
    if name and not db.scalars(select(Group).where(Group.name == name)).first():
        db.add(Group(name=name, is_active=True))
        db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/subject")
async def admin_create_subject(name: str = Form(...), code: str = Form(default=""), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    name, code = name.strip(), code.strip() or None
    if name and not db.scalars(select(Subject).where(Subject.name == name)).first():
        db.add(Subject(name=name, code=code, is_active=True))
        db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/teacher")
async def admin_create_teacher(full_name: str = Form(...), username: str = Form(...), password: str = Form(...), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    username = username.strip()
    if not db.scalars(select(User).where(User.username == username)).first():
        db.add(User(full_name=full_name.strip(), username=username, password_hash=password_hash.hash(password), role="teacher", is_active=True))
        db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/assignment")
async def admin_create_assignment(teacher_id: int = Form(...), subject_id: int = Form(...), group_id: int = Form(...), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    teacher, subject, group = db.get(User, teacher_id), db.get(Subject, subject_id), db.get(Group, group_id)
    if teacher and teacher.role == "teacher" and subject and group:
        exists = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == teacher_id, TeachingAssignment.subject_id == subject_id, TeachingAssignment.group_id == group_id, TeachingAssignment.is_active.is_(True))).first()
        if not exists:
            db.add(TeachingAssignment(teacher_id=teacher_id, subject_id=subject_id, group_id=group_id, is_active=True))
            db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/group/{group_id}/remove")
async def admin_remove_group(group_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    group = db.get(Group, group_id)
    if group:
        group.is_active = False
        db.query(TeachingAssignment).filter(TeachingAssignment.group_id == group_id).update({TeachingAssignment.is_active: False})
    db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/subject/{subject_id}/remove")
async def admin_remove_subject(subject_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    subject = db.get(Subject, subject_id)
    if subject:
        subject.is_active = False
        db.query(TeachingAssignment).filter(TeachingAssignment.subject_id == subject_id).update({TeachingAssignment.is_active: False})
    db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/teacher/{teacher_id}/remove")
async def admin_remove_teacher(teacher_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    teacher = db.get(User, teacher_id)
    if teacher and teacher.role == "teacher":
        teacher.is_active = False
        db.query(TeachingAssignment).filter(TeachingAssignment.teacher_id == teacher_id).update({TeachingAssignment.is_active: False})
    db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.post("/admin/academic/assignment/{assignment_id}/remove")
async def admin_remove_assignment(assignment_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    assignment = db.get(TeachingAssignment, assignment_id)
    if assignment:
        assignment.is_active = False
    db.commit()
    return RedirectResponse(url="/admin/academic", status_code=303)

@app.get("/admin/schedule", response_class=HTMLResponse)
async def admin_schedule(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    groups = db.scalars(select(Group).where(Group.is_active.is_(True)).order_by(Group.name)).all()
    subjects = db.scalars(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.name)).all()
    teachers = db.scalars(select(User).where(User.role == "teacher", User.is_active.is_(True)).order_by(User.full_name)).all()
    entries = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True)).options(joinedload(ScheduleEntry.subject), joinedload(ScheduleEntry.group), joinedload(ScheduleEntry.teacher)).order_by(ScheduleEntry.day_of_week, ScheduleEntry.start_time)).all()
    return templates.TemplateResponse(request=request, name="admin_schedule.html", context={"user": user, "groups": groups, "subjects": subjects, "teachers": teachers, "entries": entries})

@app.post("/admin/schedule/create")
async def admin_create_schedule(group_id: int = Form(...), subject_id: int = Form(...), teacher_id: int = Form(...), day_of_week: int = Form(...), start_time: str = Form(...), end_time: str = Form(...), room: str = Form(default=""), lesson_type: str = Form(default="Занятие"), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if day_of_week not in range(5) or len(start_time) != 5 or len(end_time) != 5 or start_time >= end_time:
        return RedirectResponse(url="/admin/schedule?error=time", status_code=303)
    group, subject, teacher = db.get(Group, group_id), db.get(Subject, subject_id), db.get(User, teacher_id)
    if not group or not subject or not teacher or teacher.role != "teacher":
        return RedirectResponse(url="/admin/schedule?error=not_found", status_code=303)
    assignment = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == teacher_id, TeachingAssignment.subject_id == subject_id, TeachingAssignment.group_id == group_id, TeachingAssignment.is_active.is_(True))).first()
    if not assignment:
        return RedirectResponse(url="/admin/schedule?error=assignment", status_code=303)
    conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True), ScheduleEntry.group_id == group_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.start_time < end_time, ScheduleEntry.end_time > start_time)).first()
    if conflict:
        return RedirectResponse(url="/admin/schedule?error=group_conflict", status_code=303)
    teacher_conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True), ScheduleEntry.teacher_id == teacher_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.start_time < end_time, ScheduleEntry.end_time > start_time)).first()
    if teacher_conflict:
        return RedirectResponse(url="/admin/schedule?error=teacher_conflict", status_code=303)
    db.add(ScheduleEntry(group_id=group_id, subject_id=subject_id, teacher_id=teacher_id, teaching_assignment_id=assignment.id, day_of_week=day_of_week, start_time=start_time, end_time=end_time, room=room.strip() or None, lesson_type=lesson_type.strip() or "Занятие", is_active=True))
    db.commit()
    return RedirectResponse(url="/admin/schedule?created=1", status_code=303)

@app.get("/admin/schedule/{entry_id}/edit", response_class=HTMLResponse)
async def admin_edit_schedule(request: Request, entry_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    entry = db.scalars(select(ScheduleEntry).where(ScheduleEntry.id == entry_id, ScheduleEntry.is_active.is_(True)).options(joinedload(ScheduleEntry.subject), joinedload(ScheduleEntry.group), joinedload(ScheduleEntry.teacher))).first()
    if not entry:
        return RedirectResponse(url="/admin/schedule?error=not_found", status_code=303)
    groups = db.scalars(select(Group).where(Group.is_active.is_(True)).order_by(Group.name)).all()
    subjects = db.scalars(select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.name)).all()
    teachers = db.scalars(select(User).where(User.role == "teacher", User.is_active.is_(True)).order_by(User.full_name)).all()
    return templates.TemplateResponse(request=request, name="admin_schedule_edit.html", context={"user": user, "entry": entry, "groups": groups, "subjects": subjects, "teachers": teachers})

@app.post("/admin/schedule/{entry_id}/edit")
async def admin_update_schedule(entry_id: int, group_id: int = Form(...), subject_id: int = Form(...), teacher_id: int = Form(...), day_of_week: int = Form(...), start_time: str = Form(...), end_time: str = Form(...), room: str = Form(default=""), lesson_type: str = Form(default="Занятие"), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    entry = db.get(ScheduleEntry, entry_id)
    if not entry or not entry.is_active:
        return RedirectResponse(url="/admin/schedule?error=not_found", status_code=303)
    if day_of_week not in range(5) or len(start_time) != 5 or len(end_time) != 5 or start_time >= end_time:
        return RedirectResponse(url=f"/admin/schedule/{entry_id}/edit?error=time", status_code=303)
    group, subject, teacher = db.get(Group, group_id), db.get(Subject, subject_id), db.get(User, teacher_id)
    if not group or not group.is_active or not subject or not subject.is_active or not teacher or teacher.role != "teacher" or not teacher.is_active:
        return RedirectResponse(url=f"/admin/schedule/{entry_id}/edit?error=not_found", status_code=303)
    assignment = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == teacher_id, TeachingAssignment.subject_id == subject_id, TeachingAssignment.group_id == group_id, TeachingAssignment.is_active.is_(True))).first()
    if not assignment:
        return RedirectResponse(url=f"/admin/schedule/{entry_id}/edit?error=assignment", status_code=303)
    group_conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.id != entry_id, ScheduleEntry.is_active.is_(True), ScheduleEntry.group_id == group_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.start_time < end_time, ScheduleEntry.end_time > start_time)).first()
    if group_conflict:
        return RedirectResponse(url=f"/admin/schedule/{entry_id}/edit?error=group_conflict", status_code=303)
    teacher_conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.id != entry_id, ScheduleEntry.is_active.is_(True), ScheduleEntry.teacher_id == teacher_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.start_time < end_time, ScheduleEntry.end_time > start_time)).first()
    if teacher_conflict:
        return RedirectResponse(url=f"/admin/schedule/{entry_id}/edit?error=teacher_conflict", status_code=303)
    entry.group_id = group_id
    entry.subject_id = subject_id
    entry.teacher_id = teacher_id
    entry.teaching_assignment_id = assignment.id
    entry.day_of_week = day_of_week
    entry.start_time = start_time
    entry.end_time = end_time
    entry.room = room.strip() or None
    entry.lesson_type = lesson_type.strip() or "Занятие"
    db.commit()
    return RedirectResponse(url="/admin/schedule?updated=1", status_code=303)

@app.post("/admin/schedule/{entry_id}/delete")
async def admin_delete_schedule(entry_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    entry = db.get(ScheduleEntry, entry_id)
    if entry:
        entry.is_active = False
        db.commit()
    return RedirectResponse(url="/admin/schedule", status_code=303)

@app.post("/admin/students/{student_id}/delete")
async def admin_delete_student(student_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    student = db.scalars(select(User).where(User.id == student_id, User.role == "student")).first()
    if not student:
        return RedirectResponse(url="/admin/students?error=not_found", status_code=303)
    db.delete(student)
    db.commit()
    return RedirectResponse(url="/admin/students", status_code=303)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="access_token", path="/")
    return response
