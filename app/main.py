from datetime import date
import json

from fastapi import Cookie, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
import jwt

from app.auth import ALGORITHM, SECRET_KEY, create_access_token, get_user_by_username, verify_password, password_hash
from app.database import Base, engine, get_db
from app.models import Assignment, Group, Notification, ScheduleEntry, Subject, TeachingAssignment, User

app = FastAPI(title="Портал колледжа")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates", context_processors=[lambda request: {"user": getattr(request.state, "user", None)}])

@app.on_event("startup")
def ensure_database_schema():
    Base.metadata.create_all(bind=engine)

@app.middleware("http")
async def load_current_user(request: Request, call_next):
    # Monitoring probes must not depend on the database.
    if request.method == "HEAD" and request.url.path == "/":
        return Response(status_code=200, headers={"Cache-Control": "no-store"})
    if request.url.path == "/healthz":
        return Response(status_code=200, content="ok", media_type="text/plain", headers={"Cache-Control": "no-store"})
    if request.method == "OPTIONS" and request.url.path in {"/", "/healthz"}:
        return Response(status_code=204, headers={"Allow": "GET, HEAD, OPTIONS"})
    db = next(get_db())
    try:
        request.state.user = get_current_user(request.cookies.get("access_token"), db)
        request.state.unread_notifications = 0
        if request.state.user:
            request.state.unread_notifications = len(
                db.scalars(
                    select(Notification.id).where(
                        Notification.user_id == request.state.user.id,
                        Notification.is_read.is_(False),
                    )
                ).all()
            )
        return await call_next(request)
    finally:
        db.close()

def template_context(request: Request, **extra):
    context = {
        "user": getattr(request.state, "user", None),
        "unread_notifications": getattr(request.state, "unread_notifications", 0),
    }
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

def create_notification(db: Session, user_id: int, title: str, body: str | None = None, href: str = "/notifications"):
    db.add(Notification(user_id=user_id, title=title, body=body, href=href, is_read=False))

def require_admin(access_token: str | None, db: Session):
    user = get_current_user(access_token, db)
    return user if user and user.role == "admin" else None

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="index.html", context={"user": get_current_user(access_token, db)})

@app.head("/")
async def home_health():
    return Response(status_code=200)

@app.api_route("/healthz", methods=["GET", "HEAD", "OPTIONS"])
async def healthz(request: Request):
    return Response(
        content="" if request.method != "GET" else "ok",
        status_code=200 if request.method != "OPTIONS" else 204,
        media_type="text/plain",
        headers={"Cache-Control": "no-store", "Allow": "GET, HEAD, OPTIONS"},
    )

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
    assignment = Assignment(title=title.strip(), description=description.strip() or None, due_date=due_date.strip() or None, teacher_id=user.id, subject_id=teaching.subject_id, group_id=teaching.group_id, is_active=True)
    db.add(assignment)
    students = db.scalars(select(User).where(User.role == "student", User.group_id == teaching.group_id, User.is_active.is_(True))).all()
    for student in students:
        create_notification(db, student.id, "Новое задание", assignment.title, "/assignments")
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
    try:
        selected_course = max(1, min(4, int(request.query_params.get("course", "1"))))
        selected_day = max(0, min(4, int(request.query_params.get("day", "0"))))
    except ValueError:
        selected_course, selected_day = 1, 0
    groups = db.scalars(select(Group).where(Group.is_active.is_(True), Group.course == selected_course).order_by(Group.name)).all()
    group_ids = [group.id for group in groups]
    entries = []
    if group_ids:
        entries = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True), ScheduleEntry.day_of_week == selected_day, ScheduleEntry.lesson_number.between(1, 6), ScheduleEntry.group_id.in_(group_ids)).options(joinedload(ScheduleEntry.subject), joinedload(ScheduleEntry.group), joinedload(ScheduleEntry.teacher)).order_by(ScheduleEntry.lesson_number)).all()
    cells = {(entry.lesson_number, entry.group_id): entry for entry in entries}
    days = [(0, "Понедельник"), (1, "Вторник"), (2, "Среда"), (3, "Четверг"), (4, "Пятница")]
    return templates.TemplateResponse(request=request, name="schedule.html", context=template_context(request, groups=groups, cells=cells, days=days, selected_course=selected_course, selected_day=selected_day))
@app.get("/assignments", response_class=HTMLResponse)
async def assignments_page(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    today = date.today().isoformat()
    query = select(Assignment).where(Assignment.is_active.is_(True), (Assignment.due_date.is_(None)) | (Assignment.due_date >= today)).options(joinedload(Assignment.subject), joinedload(Assignment.group), joinedload(Assignment.teacher)).order_by(Assignment.id.desc())
    if user.role == "student":
        assignments = db.scalars(query.where(Assignment.group_id == user.group_id)).all() if user.group_id else []
    elif user.role == "teacher":
        assignments = db.scalars(query.where(Assignment.teacher_id == user.id)).all()
    else:
        assignments = db.scalars(query).all()
    return templates.TemplateResponse(request=request, name="assignments.html", context=template_context(request, assignments=assignments))

@app.post("/teacher/assignments/{assignment_id}/delete")
async def teacher_delete_assignment(assignment_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user or user.role != "teacher":
        return RedirectResponse(url="/login", status_code=303)
    assignment = db.scalars(select(Assignment).where(Assignment.id == assignment_id, Assignment.teacher_id == user.id, Assignment.is_active.is_(True))).first()
    if assignment:
        assignment.is_active = False
        db.commit()
    return RedirectResponse(url="/assignments?deleted=1", status_code=303)

@app.get("/grades", response_class=HTMLResponse)
async def grades_page(request: Request):
    return templates.TemplateResponse(request=request, name="grades.html", context=template_context(request))

@app.get("/attendance", response_class=HTMLResponse)
async def attendance_page(request: Request):
    return templates.TemplateResponse(request=request, name="attendance.html", context=template_context(request))

@app.get("/materials", response_class=HTMLResponse)
async def materials_page(request: Request):
    return templates.TemplateResponse(request=request, name="materials.html", context=template_context(request))

@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    notifications = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.is_read, Notification.id.desc())).all()
    return templates.TemplateResponse(request=request, name="notifications.html", context=template_context(request, notifications=notifications))

@app.post("/notifications/{notification_id}/read")
async def notification_read(notification_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    item = db.scalars(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)).first()
    if item:
        item.is_read = True
        db.commit()
        return RedirectResponse(url=item.href or "/notifications", status_code=303)
    return RedirectResponse(url="/notifications", status_code=303)

@app.post("/notifications/{notification_id}/delete")
async def notification_delete(notification_id: int, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    item = db.scalars(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/notifications", status_code=303)

@app.get("/announcements", response_class=HTMLResponse)
async def announcements_page(request: Request, access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = get_current_user(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    notifications = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.href == "/announcements",
        ).order_by(Notification.is_read, Notification.id.desc())
    ).all()
    return templates.TemplateResponse(request=request, name="announcements.html", context=template_context(request, notifications=notifications))

@app.post("/admin/announcements/create")
async def admin_create_announcement(
    title: str = Form(...),
    body: str = Form(default=""),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    title = title.strip()
    body = body.strip()
    if not title:
        return RedirectResponse(url="/admin?announcement_error=title", status_code=303)
    recipients = db.scalars(select(User).where(User.is_active.is_(True), User.role.in_(["student", "teacher"]))).all()
    for recipient in recipients:
        create_notification(db, recipient.id, title, body, "/notifications")
    db.commit()
    return RedirectResponse(url="/admin?announcement_created=1", status_code=303)

@app.get("/freshman", response_class=HTMLResponse)
async def freshman_page(request: Request):
    return templates.TemplateResponse(request=request, name="freshman.html", context=template_context(request))

@app.get("/certificates", response_class=HTMLResponse)
async def certificates_page(request: Request):
    return templates.TemplateResponse(request=request, name="certificates.html", context=template_context(request))

@app.post("/admin/import")
async def admin_import(
    backup: UploadFile = File(...),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if not backup.filename or not backup.filename.lower().endswith(".json"):
        return RedirectResponse(url="/admin?import_error=format", status_code=303)

    try:
        raw = await backup.read()
        payload = json.loads(raw.decode("utf-8"))
        required = {"version", "groups", "subjects", "users", "teaching_assignments", "schedule_entries", "assignments"}
        if not required.issubset(payload) or payload["version"] != 1:
            return RedirectResponse(url="/admin?import_error=structure", status_code=303)

        # Keep the currently logged-in administrator, but replace the portal data.
        # This also removes soft-deleted rows left behind by the normal admin UI.
        db.query(Assignment).delete(synchronize_session=False)
        db.query(ScheduleEntry).delete(synchronize_session=False)
        db.query(TeachingAssignment).delete(synchronize_session=False)
        db.query(User).filter(User.role != "admin").delete(synchronize_session=False)
        db.query(Subject).delete(synchronize_session=False)
        db.query(Group).delete(synchronize_session=False)
        db.flush()

        for item in payload["groups"]:
            db.add(Group(id=item["id"], name=item["name"], course=item.get("course", 1), is_active=item.get("is_active", True)))
        for item in payload["subjects"]:
            db.add(Subject(id=item["id"], name=item["name"], code=item.get("code"), is_active=item.get("is_active", True)))
        db.flush()

        for item in payload["users"]:
            if item.get("role") == "admin":
                continue
            db.add(User(
                id=item["id"],
                username=item["username"],
                password_hash="!IMPORT_PASSWORD_RESET!",
                full_name=item["full_name"],
                role=item["role"],
                group_id=item.get("group_id"),
                is_active=item.get("is_active", True),
            ))
        db.flush()

        for item in payload["teaching_assignments"]:
            db.add(TeachingAssignment(
                id=item["id"],
                teacher_id=item["teacher_id"],
                subject_id=item["subject_id"],
                group_id=item["group_id"],
                is_active=item.get("is_active", True),
            ))
        db.flush()

        for item in payload["schedule_entries"]:
            db.add(ScheduleEntry(
                id=item["id"],
                group_id=item["group_id"],
                subject_id=item["subject_id"],
                teacher_id=item["teacher_id"],
                teaching_assignment_id=item.get("teaching_assignment_id"),
                day_of_week=item["day_of_week"],
                lesson_number=item.get("lesson_number", 1),
                start_time=item.get("start_time", ""),
                end_time=item.get("end_time", ""),
                room=item.get("room"),
                lesson_type=item.get("lesson_type", "Занятие"),
                is_active=item.get("is_active", True),
            ))

        for item in payload["assignments"]:
            db.add(Assignment(
                id=item["id"],
                title=item["title"],
                description=item.get("description"),
                due_date=item.get("due_date"),
                teacher_id=item["teacher_id"],
                subject_id=item["subject_id"],
                group_id=item["group_id"],
                is_active=item.get("is_active", True),
            ))

        db.commit()
        return RedirectResponse(url="/admin?imported=1", status_code=303)
    except UnicodeDecodeError:
        db.rollback()
        return RedirectResponse(url="/admin?import_error=encoding", status_code=303)
    except json.JSONDecodeError:
        db.rollback()
        return RedirectResponse(url="/admin?import_error=json", status_code=303)
    except Exception:
        db.rollback()
        return RedirectResponse(url="/admin?import_error=invalid", status_code=303)

@app.get("/admin/export", response_class=Response)
async def admin_export(access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    payload = {
        "version": 1,
        "exported_at": date.today().isoformat(),
        "groups": [
            {"id": x.id, "name": x.name, "course": x.course, "is_active": x.is_active}
            for x in db.scalars(select(Group)).all()
        ],
        "subjects": [
            {"id": x.id, "name": x.name, "code": x.code, "is_active": x.is_active}
            for x in db.scalars(select(Subject)).all()
        ],
        "users": [
            {"id": x.id, "username": x.username, "full_name": x.full_name, "role": x.role, "group_id": x.group_id, "is_active": x.is_active}
            for x in db.scalars(select(User)).all()
        ],
        "teaching_assignments": [
            {"id": x.id, "teacher_id": x.teacher_id, "subject_id": x.subject_id, "group_id": x.group_id, "is_active": x.is_active}
            for x in db.scalars(select(TeachingAssignment)).all()
        ],
        "schedule_entries": [
            {"id": x.id, "group_id": x.group_id, "subject_id": x.subject_id, "teacher_id": x.teacher_id, "teaching_assignment_id": x.teaching_assignment_id, "day_of_week": x.day_of_week, "lesson_number": x.lesson_number, "start_time": x.start_time, "end_time": x.end_time, "room": x.room, "lesson_type": x.lesson_type, "is_active": x.is_active}
            for x in db.scalars(select(ScheduleEntry)).all()
        ],
        "assignments": [
            {"id": x.id, "title": x.title, "description": x.description, "due_date": x.due_date, "teacher_id": x.teacher_id, "subject_id": x.subject_id, "group_id": x.group_id, "is_active": x.is_active}
            for x in db.scalars(select(Assignment)).all()
        ],
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="collegeportal-backup.json"'},
    )

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
async def admin_create_group(name: str = Form(...), course: int = Form(...), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not require_admin(access_token, db):
        return RedirectResponse(url="/login", status_code=303)
    name = name.strip()
    if name and course in range(1, 5) and not db.scalars(select(Group).where(Group.name == name)).first():
        db.add(Group(name=name, course=course, is_active=True))
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
async def admin_create_schedule(group_id: int = Form(...), subject_id: int = Form(...), teacher_id: int = Form(...), day_of_week: int = Form(...), lesson_number: int = Form(...), start_time: str = Form(default=""), end_time: str = Form(default=""), room: str = Form(default=""), lesson_type: str = Form(default="Занятие"), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if day_of_week not in range(5) or lesson_number not in range(1, 7):
        return RedirectResponse(url="/admin/schedule?error=time", status_code=303)
    group, subject, teacher = db.get(Group, group_id), db.get(Subject, subject_id), db.get(User, teacher_id)
    if not group or not subject or not teacher or teacher.role != "teacher":
        return RedirectResponse(url="/admin/schedule?error=not_found", status_code=303)
    assignment = db.scalars(select(TeachingAssignment).where(TeachingAssignment.teacher_id == teacher_id, TeachingAssignment.subject_id == subject_id, TeachingAssignment.group_id == group_id, TeachingAssignment.is_active.is_(True))).first()
    if not assignment:
        return RedirectResponse(url="/admin/schedule?error=assignment", status_code=303)
    conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True), ScheduleEntry.group_id == group_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.lesson_number == lesson_number)).first()
    if conflict:
        return RedirectResponse(url="/admin/schedule?error=group_conflict", status_code=303)
    teacher_conflict = db.scalars(select(ScheduleEntry).where(ScheduleEntry.is_active.is_(True), ScheduleEntry.teacher_id == teacher_id, ScheduleEntry.day_of_week == day_of_week, ScheduleEntry.lesson_number == lesson_number)).first()
    if teacher_conflict:
        return RedirectResponse(url="/admin/schedule?error=teacher_conflict", status_code=303)
    entry = ScheduleEntry(group_id=group_id, subject_id=subject_id, teacher_id=teacher_id, teaching_assignment_id=assignment.id, day_of_week=day_of_week, lesson_number=lesson_number, start_time=start_time, end_time=end_time, room=room.strip() or None, lesson_type=lesson_type.strip() or "Занятие", is_active=True)
    db.add(entry)
    students = db.scalars(select(User).where(User.role == "student", User.group_id == group_id, User.is_active.is_(True))).all()
    day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]
    room_text = f" · каб. {entry.room}" if entry.room else ""
    message = f"{day_names[day_of_week]}, {lesson_number} пара · {subject.name}{room_text}"
    for student in students:
        create_notification(db, student.id, "Расписание изменено", message, "/schedule")
    create_notification(db, teacher.id, "Вам добавили занятие", message, "/schedule")
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
async def admin_update_schedule(entry_id: int, group_id: int = Form(...), subject_id: int = Form(...), teacher_id: int = Form(...), day_of_week: int = Form(...), lesson_number: int = Form(...), start_time: str = Form(...), end_time: str = Form(...), room: str = Form(default=""), lesson_type: str = Form(default="Занятие"), access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    user = require_admin(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    entry = db.get(ScheduleEntry, entry_id)
    if not entry or not entry.is_active:
        return RedirectResponse(url="/admin/schedule?error=not_found", status_code=303)
    if day_of_week not in range(5) or lesson_number not in range(1, 7) or len(start_time) != 5 or len(end_time) != 5 or start_time >= end_time:
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
    entry.lesson_number = lesson_number
    entry.start_time = start_time
    entry.end_time = end_time
    entry.room = room.strip() or None
    entry.lesson_type = lesson_type.strip() or "Занятие"
    students = db.scalars(select(User).where(User.role == "student", User.group_id == group_id, User.is_active.is_(True))).all()
    day_names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]
    room_text = f" · каб. {entry.room}" if entry.room else ""
    message = f"{day_names[day_of_week]}, {lesson_number} пара · {subject.name}{room_text}"
    for student in students:
        create_notification(db, student.id, "Расписание изменено", message, "/schedule")
    create_notification(db, teacher.id, "Расписание изменено", message, "/schedule")
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
        students = db.scalars(select(User).where(User.role == "student", User.group_id == entry.group_id, User.is_active.is_(True))).all()
        subject = db.get(Subject, entry.subject_id)
        body = f"{entry.lesson_number} пара · {subject.name if subject else 'Занятие'}"
        for student in students:
            create_notification(db, student.id, "Занятие отменено", body, "/schedule")
        teacher = db.get(User, entry.teacher_id)
        if teacher:
            create_notification(db, teacher.id, "Занятие отменено", body, "/schedule")
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
