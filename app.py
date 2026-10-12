import os, io, csv, secrets, hashlib
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import or_
import info

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", info.SECRET_KEY)
db_url = os.getenv("DATABASE_URL", info.DATABASE_URL)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "1" if info.COOKIE_SECURE else "0") == "1"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    roll_no = db.Column(db.String(50))
    department = db.Column(db.String(100))
    year = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=utcnow)
    active = db.Column(db.Boolean, default=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    teacher = db.relationship("User", backref="subjects")
    created_at = db.Column(db.DateTime, default=utcnow)

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    student = db.relationship("User", backref="enrollments")
    subject = db.relationship("Subject", backref="enrollments")
    __table_args__ = (db.UniqueConstraint("student_id", "subject_id", name="uq_enrollment"),)

class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    teacher_id = db.Integer
    token_hash = db.Column(db.String(64), nullable=False, index=True)
    started_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    active = db.Column(db.Boolean, default=True)
    subject = db.relationship("Subject")
    def is_valid(self):
        return self.active and utcnow() < self.ends_at

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("attendance_session.id"), nullable=False)
    marked_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(20), default="Present")
    student = db.relationship("User", backref="attendance_records")
    subject = db.relationship("Subject")
    session = db.relationship("AttendanceSession")
    __table_args__ = (db.UniqueConstraint("student_id", "session_id", name="uq_student_session"),)

class CorrectionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    attendance_id = db.Column(db.Integer, db.ForeignKey("attendance.id"))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    created_at = db.Column(db.DateTime, default=utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewer_id = db.Column(db.Integer)
    student = db.relationship("User")
    subject = db.relationship("Subject")
    attendance = db.relationship("Attendance")

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def log(action, detail=""):
    db.session.add(AuditLog(actor_id=current_user.id if current_user.is_authenticated else None,
                            action=action, detail=detail[:500]))
    db.session.commit()

def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator

def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def make_qr_token(session_id):
    return serializer.dumps({"sid": session_id, "nonce": secrets.token_urlsafe(18)})

def find_session(token):
    try:
        payload = serializer.loads(token, max_age=20)
        session = db.session.get(AttendanceSession, int(payload["sid"]))
        if not session or not session.is_valid():
            return None
        if not secrets.compare_digest(session.token_hash, token_digest(token)):
            return None
        return session
    except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
        return None

@app.context_processor
def inject_globals():
    return {"now": utcnow()}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        roll_no = request.form.get("roll_no", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("year", "").strip()
        # Public signup may create students only. Teachers/admins are provisioned securely.
        if role != "student":
            flash("Teacher accounts must be created by an administrator.", "error")
            return redirect(url_for("signup"))
        if not name or not email or len(password) < 8:
            flash("Name, email and a password of at least 8 characters are required.", "error")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("This email is already registered. Please log in.", "error")
            return redirect(url_for("login"))
        user = User(name=name, email=email, role="student", roll_no=roll_no, department=department, year=year)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log("signup", f"Student account created: {email}")
        login_user(user)
        flash("Account created. Enroll in your subjects or ask your teacher/admin to enroll you.", "success")
        return redirect(url_for("dashboard"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        user = User.query.filter_by(email=email, active=True).first()
        if not user or not user.check_password(password) or user.role != role:
            flash("Email, password or account type is incorrect.", "error")
            return redirect(url_for("login"))
        login_user(user)
        log("login", f"Logged in as {role}")
        token = request.form.get("scan_token", "").strip()
        if role == "student" and token:
            return redirect(url_for("scan", token=token))
        return redirect(url_for("dashboard"))
    scan_token = request.args.get("token", "")
    return render_template("login.html", scan_token=scan_token)

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    log("logout", "User logged out")
    logout_user()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "student":
        records = Attendance.query.filter_by(student_id=current_user.id).order_by(Attendance.marked_at.desc()).limit(10).all()
        total = Attendance.query.filter_by(student_id=current_user.id).count()
        enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
        subjects = []
        for en in enrollments:
            total_sessions = AttendanceSession.query.filter_by(subject_id=en.subject_id).count()
            present = Attendance.query.filter_by(student_id=current_user.id, subject_id=en.subject_id).count()
            pct = round((present / total_sessions) * 100) if total_sessions else 0
            subjects.append({"subject": en.subject, "present": present, "total": total_sessions, "pct": pct})
        corrections = CorrectionRequest.query.filter_by(student_id=current_user.id).order_by(CorrectionRequest.created_at.desc()).limit(5).all()
        return render_template("student_dashboard.html", records=records, total=total, subjects=subjects, corrections=corrections)
    if current_user.role == "teacher":
        subjects = Subject.query.filter_by(teacher_id=current_user.id).all()
        return render_template("teacher_dashboard.html", subjects=subjects)
    return redirect(url_for("admin_dashboard"))

@app.route("/teacher/subject", methods=["POST"])
@role_required("teacher", "admin")
def create_subject():
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    if not name or not code:
        flash("Subject name and code are required.", "error")
    else:
        db.session.add(Subject(name=name, code=code, teacher_id=current_user.id))
        db.session.commit()
        log("subject_created", f"{code}: {name}")
        flash("Subject created.", "success")
    return redirect(url_for("dashboard"))

@app.route("/teacher/subject/<int:subject_id>/enroll", methods=["POST"])
@role_required("teacher", "admin")
def enroll_student(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
        abort(404)
    email = request.form.get("email", "").strip().lower()
    student = User.query.filter_by(email=email, role="student").first()
    if not student:
        flash("Student email was not found in the registered database.", "error")
    elif Enrollment.query.filter_by(student_id=student.id, subject_id=subject.id).first():
        flash("Student is already enrolled in this subject.", "error")
    else:
        db.session.add(Enrollment(student_id=student.id, subject_id=subject.id))
        db.session.commit()
        log("student_enrolled", f"{email} enrolled in {subject.code}")
        flash("Student enrolled successfully.", "success")
    return redirect(url_for("dashboard"))

@app.route("/teacher/subject/<int:subject_id>/qr")
@role_required("teacher", "admin")
def qr_page(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
        abort(404)
    active = AttendanceSession.query.filter_by(subject_id=subject.id, active=True).first()
    if not active or not active.is_valid():
        if active:
            active.active = False
        active = AttendanceSession(subject_id=subject.id, teacher_id=current_user.id,
                                   token_hash="pending", ends_at=utcnow() + timedelta(hours=3))
        db.session.add(active)
        db.session.flush()
        token = make_qr_token(active.id)
        active.token_hash = token_digest(token)
        db.session.commit()
    return render_template("qr.html", subject=subject, session=active)

@app.route("/api/teacher/subject/<int:subject_id>/qr-token")
@role_required("teacher", "admin")
def qr_token(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
        abort(404)
    active = AttendanceSession.query.filter_by(subject_id=subject.id, active=True).first()
    if not active or not active.is_valid():
        if active:
            active.active = False
        active = AttendanceSession(subject_id=subject.id, teacher_id=current_user.id,
                                   token_hash="pending", ends_at=utcnow() + timedelta(hours=3))
        db.session.add(active)
        db.session.flush()
    token = make_qr_token(active.id)
    active.token_hash = token_digest(token)
    active.ends_at = min(active.ends_at, utcnow() + timedelta(seconds=20))
    db.session.commit()
    return jsonify({"url": url_for("scan", token=token, _external=True), "expires_in": 20})

@app.route("/scan")
def scan():
    token = request.args.get("token", "").strip()
    session = find_session(token)
    if not session:
        return render_template("scan_result.html", success=False,
                               message="This QR code has expired. Please scan the latest QR displayed by your teacher."), 410
    if not current_user.is_authenticated:
        return redirect(url_for("login", token=token))
    if current_user.role != "student":
        return render_template("scan_result.html", success=False, message="Only student accounts can mark attendance."), 403
    enrolled = Enrollment.query.filter_by(student_id=current_user.id, subject_id=session.subject_id).first()
    if not enrolled:
        return render_template("scan_result.html", success=False,
                               message="We couldn't find your enrollment for this subject. Check that you signed up with your registered college email and ask your teacher to enroll you."), 403
    existing = Attendance.query.filter_by(student_id=current_user.id, session_id=session.id).first()
    if existing:
        return render_template("scan_result.html", success=True, message="Your attendance is already marked for this session.")
    db.session.add(Attendance(student_id=current_user.id, subject_id=session.subject_id, session_id=session.id))
    db.session.commit()
    log("attendance_marked", f"{current_user.email} present for {session.subject.code}")
    return render_template("scan_result.html", success=True, message=f"Present marked for {session.subject.name}.")

@app.route("/attendance")
@role_required("student")
def attendance_report():
    subject_id = request.args.get("subject_id", type=int)
    query = Attendance.query.filter_by(student_id=current_user.id)
    if subject_id:
        query = query.filter_by(subject_id=subject_id)
    records = query.order_by(Attendance.marked_at.desc()).all()
    subjects = [en.subject for en in Enrollment.query.filter_by(student_id=current_user.id).all()]
    return render_template("attendance.html", records=records, subjects=subjects, selected=subject_id)

@app.route("/teacher/students")
@role_required("teacher", "admin")
def student_lookup():
    q = request.args.get("q", "").strip()
    students = []
    if q:
        query = User.query.filter_by(role="student").filter(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
        if current_user.role == "teacher":
            subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
            enrolled_ids = [e.student_id for e in Enrollment.query.filter(Enrollment.subject_id.in_(subject_ids)).all()] if subject_ids else []
            query = query.filter(User.id.in_(enrolled_ids))
        students = query.order_by(User.name).limit(100).all()
    return render_template("student_lookup.html", students=students, q=q)

@app.route("/teacher/student/<int:student_id>")
@role_required("teacher", "admin")
def student_detail(student_id):
    student = db.session.get(User, student_id)
    if not student or student.role != "student":
        abort(404)
    if current_user.role == "teacher":
        subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
        if not Enrollment.query.filter(Enrollment.student_id == student.id, Enrollment.subject_id.in_(subject_ids)).first():
            abort(403)
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.marked_at.desc()).all()
    return render_template("student_detail.html", student=student, records=records)

@app.route("/corrections", methods=["GET", "POST"])
@role_required("student")
def corrections():
    if request.method == "POST":
        subject_id = request.form.get("subject_id", type=int)
        message = request.form.get("message", "").strip()
        if not message or not Enrollment.query.filter_by(student_id=current_user.id, subject_id=subject_id).first():
            flash("Choose an enrolled subject and explain the correction request.", "error")
        else:
            db.session.add(CorrectionRequest(student_id=current_user.id, subject_id=subject_id, message=message))
            db.session.commit()
            log("correction_requested", f"Subject {subject_id}")
            flash("Correction request submitted for review.", "success")
        return redirect(url_for("corrections"))
    items = CorrectionRequest.query.filter_by(student_id=current_user.id).order_by(CorrectionRequest.created_at.desc()).all()
    subjects = [en.subject for en in Enrollment.query.filter_by(student_id=current_user.id).all()]
    return render_template("corrections.html", items=items, subjects=subjects)

@app.route("/teacher/corrections")
@role_required("teacher", "admin")
def review_corrections():
    query = CorrectionRequest.query.order_by(CorrectionRequest.created_at.desc())
    if current_user.role == "teacher":
        subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
        query = query.filter(CorrectionRequest.subject_id.in_(subject_ids))
    return render_template("review_corrections.html", items=query.limit(200).all())

@app.route("/teacher/corrections/<int:req_id>/<decision>", methods=["POST"])
@role_required("teacher", "admin")
def decide_correction(req_id, decision):
    if decision not in ("approve", "reject"):
        abort(400)
    item = db.session.get(CorrectionRequest, req_id)
    if not item:
        abort(404)
    if current_user.role == "teacher" and item.subject.teacher_id != current_user.id:
        abort(403)
    item.status = "Approved" if decision == "approve" else "Rejected"
    item.reviewer_id = current_user.id
    item.reviewed_at = utcnow()
    if decision == "approve" and item.attendance_id:
        record = db.session.get(Attendance, item.attendance_id)
        if record:
            record.status = "Present"
    db.session.commit()
    log("correction_decided", f"Request {req_id}: {item.status}")
    flash(f"Correction request {item.status.lower()}.", "success")
    return redirect(url_for("review_corrections"))

@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    return render_template("admin.html", users=User.query.order_by(User.created_at.desc()).limit(100).all(),
                           subjects=Subject.query.order_by(Subject.id.desc()).limit(100).all(),
                           logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all())

@app.route("/admin/create-user", methods=["POST"])
@role_required("admin")
def admin_create_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "teacher")
    password = request.form.get("password", "")
    if role not in ("teacher", "admin", "student") or not name or not email or len(password) < 8:
        flash("Enter valid details and a password of at least 8 characters.", "error")
    elif User.query.filter_by(email=email).first():
        flash("That email is already registered.", "error")
    else:
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log("admin_user_created", f"{role}: {email}")
        flash(f"{role.title()} account created.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/export.csv")
@role_required("admin", "teacher")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student", "Email", "Roll number", "Subject", "Status", "Marked at"])
    query = Attendance.query.join(Subject)
    if current_user.role == "teacher":
        query = query.filter(Subject.teacher_id == current_user.id)
    for row in query.order_by(Attendance.marked_at.desc()).all():
        writer.writerow([row.student.name, row.student.email, row.student.roll_no or "",
                         row.subject.name, row.status, row.marked_at.isoformat()])
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name="attendx-attendance.csv")

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You don't have permission to access this page."), 403
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="We couldn't find that page."), 404

def bootstrap():
    with app.app_context():
        db.create_all()
        admin_email = os.getenv("ADMIN_EMAIL", info.ADMIN_EMAIL).strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", info.ADMIN_PASSWORD)
        if admin_password.startswith("CHANGE-ME") or app.config["SECRET_KEY"].startswith("CHANGE-ME"):
            print("WARNING: Edit info.py and replace the CHANGE-ME values before using this app beyond local testing.")
        if admin_email and admin_password and not User.query.filter_by(email=admin_email).first():
            admin = User(name="System Admin", email=admin_email, role="admin")
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()

bootstrap()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", str(info.PORT))), debug=os.getenv("FLASK_DEBUG", "1" if info.FLASK_DEBUG else "0") == "1")
