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
)
from app.database import get_db
from app.models import TeachingAssignment, User
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