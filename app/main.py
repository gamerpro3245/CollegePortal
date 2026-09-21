from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

import jwt

from app.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_user_by_username,
    verify_password,
    password_hash,
)
from app.database import get_db
from app.models import TeachingAssignment, User, Group
app = FastAPI(title="Портал колледжа")


app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")

def get_current_user(
    access_token: str | None,
    db: Session,
):
    if not access_token:
        return None

    try:
        payload = jwt.decode(
            access_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        username = payload.get("sub")

        if not username:
            return None

        user = db.scalars(
            select(User).where(User.username == username)
        ).first()

        if not user or not user.is_active:
            return None

        return user

    except jwt.PyJWTError:
        return None

def require_admin(
    access_token: str | None,
    db: Session,
):
    user = get_current_user(access_token, db)

    if not user or user.role != "admin":
        return None

    return user


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = get_current_user(access_token, db)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
        },
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )


@app.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_user_by_username(db, username)

    if (
        not user
        or not user.is_active
        or not verify_password(
            password,
            user.password_hash,
        )
    ):
        return RedirectResponse(
            url="/login?error=1",
            status_code=303,
        )

    token = create_access_token(
        username=user.username,
        role=user.role,
    )

    if user.role == "student":
        redirect_url = "/student"
    elif user.role == "teacher":
        redirect_url = "/teacher"
    elif user.role == "admin":
        redirect_url = "/admin"
    else:
        redirect_url = "/"

    response = RedirectResponse(
        url=redirect_url,
        status_code=303,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
    )

    return response

@app.get("/student", response_class=HTMLResponse)
async def student_dashboard(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = get_current_user(access_token, db)

    if not user or user.role != "student":
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="student.html",
        context={
            "user": user,
        },
    )

@app.post("/admin/students/{student_id}/delete")
async def admin_delete_student(
    student_id: int,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    student = db.scalars(
        select(User).where(
            User.id == student_id,
            User.role == "student",
        )
    ).first()

    if not student:
        return RedirectResponse(
            url="/admin/students?error=not_found",
            status_code=303,
        )

    db.delete(student)
    db.commit()

    return RedirectResponse(
        url="/admin/students",
        status_code=303,
    )
@app.get("/teacher", response_class=HTMLResponse)
async def teacher_dashboard(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = get_current_user(access_token, db)

    if not user or user.role != "teacher":
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    assignments = db.scalars(
        select(TeachingAssignment)
        .where(
            TeachingAssignment.teacher_id == user.id,
            TeachingAssignment.is_active.is_(True),
        )
        .order_by(TeachingAssignment.id)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="teacher.html",
        context={
            "user": user,
            "assignments": assignments,
        },
    )
@app.get("/schedule", response_class=HTMLResponse)
async def schedule_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Расписание",
            "page_description": "Здесь будет расписание занятий групп.",
        },
    )


@app.get("/assignments", response_class=HTMLResponse)
async def assignments_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Задания",
            "page_description": "Здесь будут учебные задания и сроки их выполнения.",
        },
    )


@app.get("/grades", response_class=HTMLResponse)
async def grades_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Оценки",
            "page_description": "Здесь будут оценки студентов.",
        },
    )


@app.get("/attendance", response_class=HTMLResponse)
async def attendance_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Посещаемость",
            "page_description": "Здесь будет учёт посещаемости.",
        },
    )


@app.get("/materials", response_class=HTMLResponse)
async def materials_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Материалы",
            "page_description": "Здесь будут учебные материалы.",
        },
    )


@app.get("/announcements", response_class=HTMLResponse)
async def announcements_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Объявления",
            "page_description": "Здесь будут новости и объявления колледжа.",
        },
    )


@app.get("/freshman", response_class=HTMLResponse)
async def freshman_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="placeholder.html",
        context={
            "page_title": "Первокурснику",
            "page_description": "Полезная информация для студентов первого курса.",
        },
    )

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
        },
    )

@app.get("/admin/students", response_class=HTMLResponse)
async def admin_students(
    request: Request,
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    students = db.scalars(
        select(User)
        .where(User.role == "student")
        .order_by(User.full_name)
    ).all()

    groups = db.scalars(
        select(Group)
        .where(Group.is_active.is_(True))
        .order_by(Group.name)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_students.html",
        context={
            "user": user,
            "students": students,
            "groups": groups,
        },
    )

@app.post("/admin/students/create")
async def admin_create_student(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    group_id: int | None = Form(default=None),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    user = require_admin(access_token, db)

    if not user:
        return RedirectResponse(
            url="/login",
            status_code=303,
        )

    existing_user = db.scalars(
        select(User).where(User.username == username)
    ).first()

    if existing_user:
        return RedirectResponse(
            url="/admin/students?error=username",
            status_code=303,
        )

    student = User(
        username=username,
        password_hash=password_hash.hash(password),
        full_name=full_name,
        role="student",
        group_id=group_id,
        is_active=True,
    )

    db.add(student)
    db.commit()

    return RedirectResponse(
        url="/admin/students",
        status_code=303,
    )