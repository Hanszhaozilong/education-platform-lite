"""Independent, single-campus community edition of the education platform."""

import functools
import hmac
import math
import os
import secrets
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import click
from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
ROLES = {"admin": "超级管理员", "principal": "校长", "teacher": "教师", "student": "学生"}
SUBJECTS = ("语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "政治")
GRADES = {i: f"小学{i}年级" for i in range(1, 7)} | {
    7: "初一", 8: "初二", 9: "初三", 10: "高一", 11: "高二", 12: "高三",
}
LEAD_STATES = {"new": "待跟进", "trial": "已约试听", "lost": "已流失", "converted": "已转正式学员"}
ROOM_STATES = {"free": "空闲", "occupied": "占用", "maintenance": "维修中"}


@event.listens_for(Engine, "connect")
def enable_foreign_keys(connection, _):
    if connection.__class__.__module__.startswith("sqlite3"):
        connection.execute("PRAGMA foreign_keys=ON")


enrolments = db.Table(
    "enrolments",
    db.Column("lesson_id", db.Integer, db.ForeignKey("lesson.id"), primary_key=True),
    db.Column("student_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(11), unique=True)
    phone_owner = db.Column(db.String(10), nullable=False, default="本人")
    subjects = db.Column(db.String(200), nullable=False, default="")
    grade = db.Column(db.Integer)
    private_note = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=0)

    @property
    def subject_list(self):
        return [value for value in self.subjects.split(",") if value]


class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default="free")
    note = db.Column(db.String(200), nullable=False, default="")


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classroom.id"))
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=False)
    note = db.Column(db.String(300), nullable=False, default="")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    classroom = db.relationship("Classroom")
    students = db.relationship("User", secondary=enrolments)
    attendances = db.relationship("Attendance", back_populates="lesson", cascade="all, delete-orphan")


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    minutes = db.Column(db.Integer, nullable=False)
    present = db.Column(db.Boolean, nullable=False)
    recorder_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lesson = db.relationship("Lesson", back_populates="attendances")
    student = db.relationship("User", foreign_keys=[student_id])
    __table_args__ = (db.UniqueConstraint("lesson_id", "student_id"),)

    @property
    def rounded_hours(self):
        return math.ceil(self.minutes / 30) / 2 if self.present else 0


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(11), nullable=False)
    grade = db.Column(db.Integer)
    note = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="new")
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    trials = db.relationship("Trial", back_populates="lead", cascade="all, delete-orphan")


class Trial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=False)
    subject = db.Column(db.String(20), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    starts_at = db.Column(db.DateTime)
    lead = db.relationship("Lead", back_populates="trials")
    teacher = db.relationship("User")


class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: now())


class LoginThrottle(db.Model):
    address = db.Column(db.String(64), primary_key=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    window_started = db.Column(db.Float, nullable=False, default=time.time)
    blocked_until = db.Column(db.Float, nullable=False, default=0)


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def require_roles(*roles):
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for("login"))
            if roles and g.user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def bounded(value, label, maximum, required=True):
    value = (value or "").strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError(f"{label}不能为空且最多 {maximum} 个字符。")
    return value


def parse_phone(value):
    value = (value or "").strip()
    if value and (len(value) != 11 or not value.isascii() or not value.isdigit() or value[0] != "1"):
        raise ValueError("请输入有效的 11 位手机号。")
    return value or None


def parse_grade(value):
    if not value:
        return None
    if not str(value).isdigit() or int(value) not in GRADES:
        raise ValueError("请选择有效的年级。")
    return int(value)


def selected_teacher(value, subject, optional=False):
    if not value and optional:
        return None
    teacher = db.session.get(User, int(value)) if str(value).isdigit() else None
    if not teacher or teacher.role != "teacher" or not teacher.active:
        raise ValueError("请选择有效的任课教师。")
    if subject not in teacher.subject_list:
        raise ValueError("教师未登记教授这个科目，请重新选择。")
    return teacher


def visible_lessons():
    query = Lesson.query
    if g.user.role == "teacher":
        query = query.filter(Lesson.teacher_id == g.user.id)
    elif g.user.role == "student":
        query = query.filter(Lesson.students.any(User.id == g.user.id))
    return query


def can_see(lesson):
    return g.user.role in ("admin", "principal") or (
        g.user.role == "teacher" and lesson.teacher_id == g.user.id
    ) or (g.user.role == "student" and g.user in lesson.students)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///lite.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=256 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("请在 .env 中设置至少 32 个字符的随机 SECRET_KEY。")
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    @app.before_request
    def load_identity_and_check_csrf():
        g.user = db.session.get(User, session["user_id"]) if session.get("user_id") else None
        if g.user and (not g.user.active or session.get("version") != g.user.session_version):
            session.clear()
            g.user = None
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method == "POST":
            if not hmac.compare_digest(session["csrf"], request.form.get("csrf", "")):
                abort(400, description="表单已过期，请刷新页面后重试。")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def common():
        return dict(roles=ROLES, subjects=SUBJECTS, grades=GRADES, lead_states=LEAD_STATES,
                    room_states=ROOM_STATES, manager=g.user and g.user.role in ("admin", "principal"))

    @app.errorhandler(ValueError)
    def validation_error(error):
        db.session.rollback()
        return render_template("error.html", message=str(error), code=400), 400

    @app.errorhandler(IntegrityError)
    def duplicate_error(_):
        db.session.rollback()
        return render_template("error.html", message="账号、手机号、教室名称或考勤记录重复，请核对后重试。", code=409), 409

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def http_error(error):
        messages = {400: "请求无效，请核对表单后重试。", 403: "你没有权限进行此操作。",
                    404: "内容不存在或已被删除。", 413: "提交内容过大。"}
        return render_template("error.html", message=messages.get(error.code), code=error.code), error.code

    @app.cli.command("init-db")
    @click.option("--username", prompt="管理员用户名", default="admin")
    @click.option("--password", prompt="管理员密码（至少 12 位）", hide_input=True, confirmation_prompt=True)
    def init_db(username, password):
        """Create empty tables and the first administrator; never reset existing data."""
        if len(password) < 12:
            raise click.ClickException("管理员密码至少 12 位。")
        username = bounded(username, "用户名", 80)
        db.create_all()
        if User.query.filter_by(role="admin").first():
            raise click.ClickException("已存在管理员，不会覆盖已有数据库。")
        db.session.add(User(username=username, name="管理员", role="admin",
                            password_hash=generate_password_hash(password)))
        db.session.commit()
        click.echo("初始化完成。请登录后创建教师、学生和教室。")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            address = request.remote_addr or "unknown"
            throttle = db.session.get(LoginThrottle, address)
            if throttle and time.time() < throttle.blocked_until:
                flash("尝试次数过多，请在 5 分钟后再试。", "error")
                return render_template("login.html"), 429
            account = request.form.get("username", "").strip()
            user = User.query.filter((User.username == account) | (User.phone == account)).first()
            if user and user.active and check_password_hash(user.password_hash, request.form.get("password", "")):
                session.clear()
                if throttle:
                    db.session.delete(throttle)
                    db.session.commit()
                session.update(user_id=user.id, version=user.session_version, csrf=secrets.token_urlsafe(32))
                session.permanent = True
                return redirect(url_for("home"))
            if not throttle:
                throttle = LoginThrottle(address=address, failures=0, window_started=time.time())
                db.session.add(throttle)
            if time.time() - throttle.window_started > 300:
                throttle.failures, throttle.window_started = 0, time.time()
            throttle.failures += 1
            if throttle.failures >= 5:
                throttle.blocked_until = time.time() + 300
            db.session.commit()
            flash("账号或密码错误。", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @require_roles()
    def home():
        today = now().date()
        lessons = visible_lessons().filter(Lesson.starts_at >= datetime.combine(today, datetime.min.time()),
                                           Lesson.starts_at < datetime.combine(today + timedelta(days=1), datetime.min.time())).order_by(Lesson.starts_at).all()
        return render_template("home.html", lessons=lessons, today=today,
                               notices=Notice.query.order_by(Notice.created_at.desc()).limit(3).all(),
                               student_count=User.query.filter_by(role="student", active=True).count(),
                               teacher_count=User.query.filter_by(role="teacher", active=True).count(),
                               free_rooms=Classroom.query.filter_by(status="free").count())

    @app.get("/people")
    @require_roles("admin", "principal")
    def people():
        role = request.args.get("role", "student")
        if role not in ROLES:
            abort(400)
        query = User.query.filter_by(role=role)
        search = request.args.get("q", "").strip()[:80]
        if search:
            query = query.filter(db.or_(User.name.contains(search, autoescape=True),
                                       User.username.contains(search, autoescape=True)))
        return render_template("people.html", users=query.order_by(User.id.desc()).all(), role=role, search=search)

    @app.route("/people/new", methods=["GET", "POST"])
    @app.route("/people/<int:user_id>/edit", methods=["GET", "POST"])
    @require_roles("admin", "principal")
    def edit_person(user_id=None):
        person = db.get_or_404(User, user_id) if user_id else None
        if person and person.role in ("admin", "principal") and g.user.role != "admin":
            abort(403)
        if request.method == "POST":
            role = request.form.get("role")
            if role not in ROLES or (g.user.role != "admin" and role not in ("teacher", "student")):
                abort(403)
            username = bounded(request.form.get("username"), "用户名", 80)
            phone = parse_phone(request.form.get("phone"))
            collision = User.query.filter(db.or_(User.username.in_([username, phone or username]),
                                                  User.phone.in_([username, phone or username])))
            if person:
                collision = collision.filter(User.id != person.id)
            if collision.first():
                raise ValueError("该用户名或手机号已被其他账户占用。")
            if person and person.role != role:
                raise ValueError("已有账号的角色不可修改，请单独创建账号。")
            name = bounded(request.form.get("name"), "姓名", 80)
            subjects = request.form.getlist("subjects")
            if any(subject not in SUBJECTS for subject in subjects):
                raise ValueError("请选择有效的科目。")
            if role == "teacher" and not subjects:
                raise ValueError("请为教师选择至少一个授教科目。")
            owner = request.form.get("phone_owner", "本人")
            if owner not in ("本人", "父亲", "母亲"):
                raise ValueError("请选择有效的号码归属。")
            password = request.form.get("password", "")
            if (not person or password) and len(password) < 12:
                raise ValueError("密码至少需要 12 位。")
            if not person:
                person = User(role=role)
                db.session.add(person)
            person.username, person.name, person.phone = username, name, phone
            person.phone_owner = owner
            person.subjects = ",".join(dict.fromkeys(subjects)) if role == "teacher" else ""
            person.grade = parse_grade(request.form.get("grade")) if role == "student" else None
            person.private_note = bounded(request.form.get("private_note"), "管理备注", 2000, False)
            if password:
                person.password_hash = generate_password_hash(password)
                person.session_version = (person.session_version or 0) + 1
            db.session.commit()
            flash("账户已保存。", "success")
            return redirect(url_for("people", role=role))
        return render_template("person_form.html", person=person, selected_role=person.role if person else request.args.get("role", "student"))

    @app.get("/schedule")
    @require_roles()
    def schedule():
        try:
            selected = date.fromisoformat(request.args.get("date", now().date().isoformat()))
        except ValueError:
            raise ValueError("请选择有效日期。")
        monday = selected - timedelta(days=selected.weekday())
        end = monday + timedelta(days=7)
        lessons = visible_lessons().filter(Lesson.starts_at >= datetime.combine(monday, datetime.min.time()),
                                           Lesson.starts_at < datetime.combine(end, datetime.min.time())).order_by(Lesson.starts_at).all()
        return render_template("schedule.html", lessons=lessons, monday=monday,
                               days=[monday + timedelta(days=i) for i in range(7)],
                               previous=(monday-timedelta(days=7)).isoformat(), following=end.isoformat())

    @app.route("/schedule/new", methods=["GET", "POST"])
    @require_roles("admin", "principal")
    def new_lesson():
        teachers = User.query.filter_by(role="teacher", active=True).order_by(User.name).all()
        students = User.query.filter_by(role="student", active=True).order_by(User.name).all()
        rooms = Classroom.query.order_by(Classroom.id).all()
        if request.method == "POST":
            subject = request.form.get("subject")
            if subject not in SUBJECTS:
                raise ValueError("请选择有效的科目。")
            teacher = selected_teacher(request.form.get("teacher_id"), subject)
            try:
                start = datetime.fromisoformat(request.form.get("starts_at", ""))
                end = datetime.fromisoformat(request.form.get("ends_at", ""))
            except ValueError:
                raise ValueError("请输入有效的上课、下课时间。")
            if start.tzinfo or end.tzinfo or end <= start or start.date() != end.date():
                raise ValueError("下课时间须晚于上课时间，且须在同一天。")
            chosen_ids = request.form.getlist("students")
            if not chosen_ids or any(not value.isdigit() for value in chosen_ids):
                raise ValueError("请至少选择一名学生。")
            chosen = User.query.filter(User.id.in_([int(value) for value in chosen_ids]), User.role == "student", User.active.is_(True)).all()
            if len(chosen) != len(set(chosen_ids)):
                raise ValueError("选择的学生无效。")
            room_id = request.form.get("classroom_id", "")
            room = db.session.get(Classroom, int(room_id)) if room_id.isdigit() else None
            if room_id and (not room or room.status != "free"):
                raise ValueError("教室不存在、正在使用或维修中。")
            overlaps = Lesson.query.filter(Lesson.starts_at < end, Lesson.ends_at > start).all()
            for existing in overlaps:
                if existing.teacher_id == teacher.id:
                    raise ValueError("该教师在这个时段已有排课。")
                if room and existing.classroom_id == room.id:
                    raise ValueError("该教室在这个时段已有排课。")
                if set(student.id for student in existing.students) & set(student.id for student in chosen):
                    raise ValueError("所选学生在这个时段已有排课。")
            lesson = Lesson(subject=subject, teacher=teacher, classroom=room, students=chosen,
                            starts_at=start, ends_at=end,
                            note=bounded(request.form.get("note"), "排课备注", 300, False))
            db.session.add(lesson)
            db.session.commit()
            flash("排课已创建。", "success")
            return redirect(url_for("lesson_detail", lesson_id=lesson.id))
        return render_template("lesson_form.html", teachers=teachers, students=students, rooms=rooms)

    @app.get("/schedule/<int:lesson_id>")
    @require_roles()
    def lesson_detail(lesson_id):
        lesson = db.get_or_404(Lesson, lesson_id)
        if not can_see(lesson):
            abort(403)
        records = {record.student_id: record for record in lesson.attendances}
        return render_template("lesson_detail.html", lesson=lesson, records=records,
                               can_record=g.user.role in ("admin", "principal", "teacher"))

    @app.post("/schedule/<int:lesson_id>/attendance")
    @require_roles("admin", "principal", "teacher")
    def attendance(lesson_id):
        lesson = db.get_or_404(Lesson, lesson_id)
        if not can_see(lesson):
            abort(403)
        values = []
        for student in lesson.students:
            raw = request.form.get(f"minutes_{student.id}", "")
            if not raw.isdigit() or not 1 <= int(raw) <= 1440:
                raise ValueError("授课分钟数必须是 1 至 1440 的整数。")
            values.append((student, int(raw), request.form.get(f"present_{student.id}") == "on"))
        for student, minutes, present in values:
            record = Attendance.query.filter_by(lesson_id=lesson.id, student_id=student.id).first()
            if not record:
                record = Attendance(lesson_id=lesson.id, student_id=student.id)
                db.session.add(record)
            record.minutes, record.present, record.recorder_id = minutes, present, g.user.id
        db.session.commit()
        flash("考勤已保存，实际时长按半小时向上折算。", "success")
        return redirect(url_for("lesson_detail", lesson_id=lesson.id))

    @app.post("/schedule/<int:lesson_id>/delete")
    @require_roles("admin", "principal")
    def delete_lesson(lesson_id):
        lesson = db.get_or_404(Lesson, lesson_id)
        if lesson.attendances:
            raise ValueError("该排课已有考勤记录，请保留记录，不可删除。")
        db.session.delete(lesson)
        db.session.commit()
        flash("排课已删除。", "success")
        return redirect(url_for("schedule"))

    @app.route("/classrooms", methods=["GET", "POST"])
    @require_roles()
    def classrooms():
        if request.method == "POST":
            if g.user.role not in ("admin", "principal"):
                abort(403)
            if request.form.get("action") == "create":
                db.session.add(Classroom(name=bounded(request.form.get("name"), "教室名称", 50)))
            else:
                raw = request.form.get("room_id", "")
                room = db.get_or_404(Classroom, int(raw)) if raw.isdigit() else abort(400)
                status = request.form.get("status")
                if status not in ROOM_STATES:
                    raise ValueError("请选择有效的教室状态。")
                room.status, room.note = status, bounded(request.form.get("note"), "状态备注", 200, False)
            db.session.commit()
            flash("教室状态已更新。", "success")
            return redirect(url_for("classrooms"))
        return render_template("classrooms.html", rooms=Classroom.query.order_by(Classroom.id).all())

    @app.route("/leads", methods=["GET", "POST"])
    @require_roles("admin", "principal")
    def leads():
        if request.method == "POST":
            phone = parse_phone(request.form.get("phone"))
            if not phone:
                raise ValueError("请填写联系电话。")
            lead = Lead(name=bounded(request.form.get("name"), "姓名", 80), phone=phone,
                        grade=parse_grade(request.form.get("grade")),
                        note=bounded(request.form.get("note"), "跟进备注", 2000, False))
            trial_subjects = request.form.getlist("trial_subject")
            trial_teachers = request.form.getlist("trial_teacher")
            trial_times = request.form.getlist("trial_time")
            if len(trial_subjects) > 20 or not len(trial_subjects) == len(trial_teachers) == len(trial_times):
                raise ValueError("试听课数据不完整，一次最多 20 节。")
            for subject, teacher_id, starts_at in zip(trial_subjects, trial_teachers, trial_times):
                if not subject and not teacher_id and not starts_at:
                    continue
                if subject not in SUBJECTS:
                    raise ValueError("请为每节试听课选择科目。")
                teacher = selected_teacher(teacher_id, subject, optional=True)
                try:
                    trial_time = datetime.fromisoformat(starts_at) if starts_at else None
                except ValueError:
                    raise ValueError("试听时间无效。")
                if trial_time and trial_time.tzinfo:
                    raise ValueError("试听时间请使用当地时间。")
                lead.trials.append(Trial(subject=subject, teacher=teacher, starts_at=trial_time))
            if lead.trials:
                lead.status = "trial"
            db.session.add(lead)
            db.session.commit()
            flash("意向学员已录入。", "success")
            return redirect(url_for("leads"))
        return render_template("leads.html", leads=Lead.query.order_by(Lead.id.desc()).all(),
                               teachers=User.query.filter_by(role="teacher", active=True).order_by(User.name).all())

    @app.post("/leads/<int:lead_id>/<action>")
    @require_roles("admin", "principal")
    def lead_action(lead_id, action):
        lead = db.get_or_404(Lead, lead_id)
        if lead.status == "converted":
            raise ValueError("已转化学员须在学生管理中维护，不可流失或删除线索。")
        if action == "lost":
            lead.status = "lost"
        elif action == "restore":
            lead.status = "trial" if lead.trials else "new"
        elif action == "delete":
            db.session.delete(lead)
        elif action == "convert":
            if lead.status == "lost":
                raise ValueError("请先恢复跟进，再转化为正式学员。")
            password = request.form.get("password", "")
            if len(password) < 12:
                raise ValueError("请为新账户设置至少 12 位密码。")
            if User.query.filter(db.or_(User.username == lead.phone, User.phone == lead.phone)).first():
                raise ValueError("该手机号已被账户使用，无法重复创建。")
            student = User(username=lead.phone, phone=lead.phone, name=lead.name, role="student",
                           grade=lead.grade, private_note=lead.note,
                           password_hash=generate_password_hash(password))
            db.session.add(student)
            db.session.flush()
            lead.student_id, lead.status = student.id, "converted"
        else:
            abort(404)
        db.session.commit()
        flash("线索已更新。", "success")
        return redirect(url_for("leads"))

    @app.route("/notices", methods=["GET", "POST"])
    @require_roles()
    def notices():
        if request.method == "POST":
            if g.user.role not in ("admin", "principal"):
                abort(403)
            db.session.add(Notice(title=bounded(request.form.get("title"), "标题", 120),
                                  body=bounded(request.form.get("body"), "公告内容", 4000)))
            db.session.commit()
            flash("公告已发布。", "success")
            return redirect(url_for("notices"))
        return render_template("notices.html", notices=Notice.query.order_by(Notice.created_at.desc()).all())

    @app.route("/profile", methods=["GET", "POST"])
    @require_roles()
    def profile():
        if request.method == "POST":
            if not check_password_hash(g.user.password_hash, request.form.get("old_password", "")):
                raise ValueError("原密码不正确。")
            password = request.form.get("password", "")
            if len(password) < 12:
                raise ValueError("新密码至少需要 12 位。")
            g.user.password_hash = generate_password_hash(password)
            g.user.session_version += 1
            db.session.commit()
            session.clear()
            flash("密码已修改，请重新登录。", "success")
            return redirect(url_for("login"))
        return render_template("profile.html")

    @app.get("/support")
    def support():
        return render_template("support.html")

    return app
