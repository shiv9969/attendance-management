import os, io, csv, secrets, hashlib, smtplib, time, base64
import qrcode
from qrcode.image.svg import SvgPathImage
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
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
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), index=True)
    account_status = db.Column(db.String(20), default="active", nullable=False)
    unique_code = db.Column(db.String(32), unique=True, index=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class College(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    official_email = db.Column(db.String(255), nullable=False, index=True)
    address = db.Column(db.String(300), default="")
    code = db.Column(db.String(24), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="approved", nullable=False) # pending, approved, rejected, suspended
    created_at = db.Column(db.DateTime, default=utcnow)

class CollegeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    college_name = db.Column(db.String(180), nullable=False)
    official_email = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(300), default="")
    contact_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    reviewed_at = db.Column(db.DateTime)

class StudentRoster(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
    student_id = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(100), default="")
    year = db.Column(db.String(30), default="")
    division = db.Column(db.String(30), default="")
    claimed = db.Column(db.Boolean, default=False, nullable=False)
    unique_code = db.Column(db.String(32), unique=True, index=True)
    __table_args__ = (db.UniqueConstraint("college_id", "student_id", name="uq_roster_college_student"), db.UniqueConstraint("college_id", "email", name="uq_roster_college_email"))

class TeacherInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

class EmailOTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    payload = db.Column(db.Text, nullable=False) # JSON serialized signup fields
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(30), nullable=False)
    college_id = db.Column(db.Integer, db.ForeignKey("college.id"), nullable=False, index=True)
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

def send_otp_email(email, otp):
    """SMTP is configured in info.py. If not configured, OTP is never exposed to the public response."""
    host = getattr(info, "SMTP_HOST", "")
    user = getattr(info, "SMTP_USER", "")
    password = getattr(info, "SMTP_PASSWORD", "")
    sender = getattr(info, "SMTP_FROM", user)
    port = int(getattr(info, "SMTP_PORT", 587))
    if not host or not sender:
        app.logger.error("Email OTP cannot be delivered: configure SMTP_HOST/SMTP_FROM in info.py")
        return False
    msg = EmailMessage(); msg["Subject"] = "Your AttendX verification code"; msg["From"] = sender; msg["To"] = email
    msg.set_content(f"Your AttendX verification code is {otp}. It expires in 10 minutes. If you did not request it, ignore this email.")
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            if user: server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        app.logger.exception("Unable to send AttendX OTP")
        return False

def otp_digest(email, purpose, otp):
    return hashlib.sha256(f"{app.config['SECRET_KEY']}:{email}:{purpose}:{otp}".encode()).hexdigest()

def issue_otp(email, purpose, payload):
    EmailOTP.query.filter_by(email=email, purpose=purpose, used=False).update({"used": True})
    otp = f"{secrets.randbelow(1000000):06d}"
    record = EmailOTP(email=email, purpose=purpose, code_hash=otp_digest(email, purpose, otp), payload=__import__('json').dumps(payload), expires_at=utcnow()+timedelta(minutes=10))
    db.session.add(record); db.session.commit()
    if not send_otp_email(email, otp):
        db.session.delete(record); db.session.commit(); return False
    return True

def generate_college_code():
    while True:
        code = "ATX-" + secrets.token_hex(3).upper()
        if not College.query.filter_by(code=code).first(): return code

def generate_unique_code(prefix):
    for _ in range(100):
        code = prefix + "-" + secrets.token_hex(3).upper()
        if not User.query.filter_by(unique_code=code).first() and not StudentRoster.query.filter_by(unique_code=code).first() and not TeacherInvite.query.filter_by(code=code).first():
            return code
    raise RuntimeError("Could not generate a unique code")

def college_from_code(code):
    return College.query.filter_by(code=code.strip().upper(), status="approved").first()

def same_college_or_404(obj):
    if current_user.role != "admin" and (not current_user.college_id or getattr(obj, "college_id", None) != current_user.college_id): abort(404)

@app.context_processor
def inject_globals():
    return {"now": utcnow()}

@app.route("/create-account")
def create_account_options():
    return render_template("create_account_choice.html")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name=request.form.get("name", "").strip(); email=request.form.get("email", "").strip().lower()
        password=request.form.get("password", ""); code=request.form.get("unique_code", "").strip().upper()
        student_id=request.form.get("roll_no", "").strip(); department=request.form.get("department", "").strip(); year=request.form.get("year", "").strip()
        if not name or not email or not code or len(password)<8:
            flash("Enter your unique student code, name, email and password (8+ characters).", "error"); return redirect(url_for("signup"))
        roster=StudentRoster.query.filter_by(unique_code=code, email=email, claimed=False).first()
        if not roster or roster.name.casefold()!=name.casefold():
            flash("Student details do not match an unclaimed record uploaded by your college.", "error"); return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("This email already has an account. Please log in.", "error"); return redirect(url_for("login"))
        payload={"name":name,"email":email,"password_hash":generate_password_hash(password),"college_id":roster.college_id,"roll_no":roster.student_id,"department":roster.department or department,"year":roster.year or year,"roster_id":roster.id}
        if not issue_otp(email,"student_signup",payload):
            flash("Email verification could not be sent. Please try later; the college must configure SMTP in info.py.", "error"); return redirect(url_for("signup"))
        flash("A 6-digit verification code was sent to your registered email.", "success")
        return redirect(url_for("verify_email", email=email, purpose="student_signup"))
    return render_template("signup.html")

@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    email=request.args.get("email", "").strip().lower()
    purpose=request.args.get("purpose", "student_signup")
    if request.method=="POST":
        email=request.form.get("email", "").strip().lower(); purpose=request.form.get("purpose", "student_signup"); otp=request.form.get("otp", "").strip()
        record=EmailOTP.query.filter_by(email=email,purpose=purpose,used=False).order_by(EmailOTP.created_at.desc()).first()
        if not record or record.expires_at<utcnow() or record.attempts>=5:
            flash("Verification code expired or unavailable. Please register again.","error"); return redirect(url_for("signup"))
        record.attempts += 1
        if not secrets.compare_digest(record.code_hash,otp_digest(email,purpose,otp)):
            db.session.commit(); flash("Incorrect verification code.","error"); return redirect(url_for("verify_email",email=email,purpose=purpose))
        payload=__import__('json').loads(record.payload)
        if purpose=="student_signup":
            if User.query.filter_by(email=email).first(): record.used=True; db.session.commit(); flash("Account already exists. Please log in.","error"); return redirect(url_for("login"))
            roster=db.session.get(StudentRoster,int(payload["roster_id"]))
            if not roster or roster.claimed or roster.college_id!=payload["college_id"]: abort(400)
            user=User(name=payload["name"],email=email,password_hash=payload["password_hash"],role="student",college_id=payload["college_id"],roll_no=payload["roll_no"],department=payload["department"],year=payload["year"],account_status="active",unique_code=roster.unique_code)
            roster.claimed=True; db.session.add(user); record.used=True; db.session.commit(); login_user(user); log("student_verified_signup",email); return redirect(url_for("dashboard"))
        flash("Unsupported verification flow.","error"); return redirect(url_for("login"))
    return render_template("verify_email.html", email=email, purpose=purpose)

@app.route("/college/register", methods=["GET", "POST"])
def college_register():
    if request.method=="POST":
        name=request.form.get("college_name","").strip(); email=request.form.get("official_email","").strip().lower(); address=request.form.get("address","").strip(); contact=request.form.get("contact_name","").strip(); password=request.form.get("password","")
        if not all([name,email,address,contact]) or len(password)<10:
            flash("Complete all fields and choose a password with at least 10 characters.","error"); return redirect(url_for("college_register"))
        if User.query.filter_by(email=email).first() or CollegeRequest.query.filter_by(official_email=email,status="pending").first() or College.query.filter_by(official_email=email).first():
            flash("A request or approved college already exists for this email.","error"); return redirect(url_for("college_register"))
        req=CollegeRequest(college_name=name,official_email=email,address=address,contact_name=contact,password_hash=generate_password_hash(password))
        db.session.add(req); db.session.commit(); flash("College request submitted. AttendX will review it before issuing a code.","success"); return redirect(url_for("login"))
    return render_template("college_register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        user=User.query.filter_by(email=email).first()
        if user is None:
            app.logger.warning("Login rejected: no account for submitted email")
            flash("Email or password is incorrect, or your account is not active.","error"); return redirect(url_for("login"))
        if not user.active or user.account_status != "active":
            app.logger.warning("Login rejected: account inactive (role=%s, status=%s)", user.role, user.account_status)
            flash("Your account is not active yet. College registrations and teacher accounts may need approval.","error"); return redirect(url_for("login"))
        if not user.check_password(password):
            app.logger.warning("Login rejected: password mismatch (role=%s)", user.role)
            flash("Email or password is incorrect, or your account is not active.","error"); return redirect(url_for("login"))
        login_user(user); log("login",f"Logged in as {user.role}")
        token=request.form.get("scan_token","").strip()
        if user.role=="student" and token: return redirect(url_for("scan",token=token))
        return redirect(url_for("dashboard"))
    return render_template("login.html",scan_token=request.args.get("token",""))

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
        subjects = Subject.query.filter_by(teacher_id=current_user.id, college_id=current_user.college_id).order_by(Subject.name).all()
        student_ids = {e.student_id for e in Enrollment.query.join(Subject, Enrollment.subject_id == Subject.id).filter(Subject.teacher_id == current_user.id).all()}
        active_sessions = AttendanceSession.query.join(Subject, AttendanceSession.subject_id == Subject.id).filter(Subject.teacher_id == current_user.id, AttendanceSession.active == True).count()
        return render_template("teacher_dashboard.html", subjects=subjects, student_count=len(student_ids), active_sessions=active_sessions, page="dashboard")
    if current_user.role == "college_admin": return redirect(url_for("college_admin_dashboard"))
    return redirect(url_for("admin_dashboard"))

@app.route("/teacher/<section>")
@role_required("teacher")
def teacher_section(section):
    if section not in ("subjects", "students", "reports", "profile"):
        abort(404)
    subjects = Subject.query.filter_by(teacher_id=current_user.id, college_id=current_user.college_id).order_by(Subject.name).all()
    student_ids = [e.student_id for e in Enrollment.query.join(Subject, Enrollment.subject_id == Subject.id).filter(Subject.teacher_id == current_user.id).all()]
    students = User.query.filter(User.id.in_(student_ids), User.role == "student").order_by(User.name).all() if student_ids else []
    records = Attendance.query.join(Subject, Attendance.subject_id == Subject.id).filter(Subject.teacher_id == current_user.id).order_by(Attendance.marked_at.desc()).limit(200).all()
    return render_template("teacher_section.html", page=section, subjects=subjects, students=students, records=records)

@app.route("/teacher/subject/<int:subject_id>/edit", methods=["POST"])
@role_required("teacher")
def edit_subject(subject_id):
    subject = Subject.query.filter_by(id=subject_id, teacher_id=current_user.id, college_id=current_user.college_id).first_or_404()
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    if not name or not code or len(name) > 120 or len(code) > 30:
        flash("Enter a valid subject name and code.", "error")
    else:
        subject.name, subject.code = name, code
        db.session.commit()
        log("subject_updated", f"{code}: {name}")
        flash("Subject updated.", "success")
    return redirect(url_for("teacher_section", section="subjects"))

@app.route("/teacher/subject", methods=["POST"])
@role_required("teacher", "college_admin")
def create_subject():
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().upper()
    if not name or not code:
        flash("Subject name and code are required.", "error")
    else:
        db.session.add(Subject(name=name, code=code, teacher_id=current_user.id, college_id=current_user.college_id))
        db.session.commit()
        log("subject_created", f"{code}: {name}")
        flash("Subject created.", "success")
    return redirect(url_for("dashboard"))

@app.route("/teacher/subject/<int:subject_id>/enroll", methods=["POST"])
@role_required("teacher", "college_admin")
def enroll_student(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role != "admin" and subject.college_id != current_user.college_id) or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
        abort(404)
    email = request.form.get("email", "").strip().lower()
    student = User.query.filter_by(email=email, role="student", college_id=current_user.college_id, account_status="active").first()
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
@role_required("teacher", "college_admin")
def qr_page(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role != "admin" and subject.college_id != current_user.college_id) or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
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

@app.route("/teacher/subject/<int:subject_id>/qr-stop", methods=["POST"])
@role_required("teacher", "college_admin")
def stop_qr_session(subject_id):
    subject=Subject.query.filter_by(id=subject_id,college_id=current_user.college_id).first_or_404()
    if current_user.role=="teacher" and subject.teacher_id!=current_user.id: abort(404)
    sessions=AttendanceSession.query.filter_by(subject_id=subject.id,active=True).all()
    for session in sessions: session.active=False
    db.session.commit(); log("attendance_session_stopped",subject.code); flash("Attendance session stopped.","success"); return redirect(url_for("dashboard"))

@app.route("/api/teacher/subject/<int:subject_id>/qr-token")
@role_required("teacher", "college_admin")
def qr_token(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject or (current_user.role != "admin" and subject.college_id != current_user.college_id) or (current_user.role == "teacher" and subject.teacher_id != current_user.id):
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
    # Keep the class session alive; only this QR token expires after 20 seconds.
    db.session.commit()
    scan_url = url_for("scan", token=token, _external=True)
    # Generate QR on the server so browser/CDN access is not required.
    qr_image = qrcode.make(scan_url, image_factory=SvgPathImage, box_size=8, border=3)
    qr_buffer = io.BytesIO()
    qr_image.save(qr_buffer)
    qr_svg = "data:image/svg+xml;base64," + base64.b64encode(qr_buffer.getvalue()).decode("ascii")
    return jsonify({"url": scan_url, "qr_svg": qr_svg, "expires_in": 20})

@app.route("/scan", methods=["GET", "POST"])
def scan():
    token = request.values.get("token", "").strip()
    session = find_session(token)
    if not session:
        return render_template("scan_result.html", success=False, message="We couldn't find an active QR session. Please scan the latest QR displayed by your teacher."), 410
    def mark_present(student):
        if student.role != "student" or student.college_id != session.subject.college_id:
            return render_template("scan_result.html", success=False, message="We couldn't find your registered student record. Please check your name and email."), 403
        enrolled = Enrollment.query.filter_by(student_id=student.id, subject_id=session.subject_id).first()
        if not enrolled:
            return render_template("scan_result.html", success=False, message="We couldn't find your enrollment for this subject. Please check with your teacher."), 403
        existing = Attendance.query.filter_by(student_id=student.id, session_id=session.id).first()
        if existing:
            return render_template("scan_result.html", success=True, message="Your attendance is already marked for this session.")
        db.session.add(Attendance(student_id=student.id, subject_id=session.subject_id, session_id=session.id))
        db.session.commit()
        log("attendance_marked", f"{student.email} present for {session.subject.code}")
        return render_template("scan_result.html", success=True, message=f"Present marked for {session.subject.name}.")
    if current_user.is_authenticated:
        if current_user.role != "student":
            return render_template("scan_result.html", success=False, message="Only student accounts can mark attendance."), 403
        return mark_present(current_user)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if not name or not email:
            return render_template("scan_identity.html", token=token, error="Enter your registered full name and college email.")
        student = User.query.filter_by(email=email, role="student", college_id=session.subject.college_id, account_status="active").first()
        if not student or student.name.strip().casefold() != name.casefold():
            return render_template("scan_identity.html", token=token, error="We couldn't find you in the registered student records. Please check your name and email.")
        return mark_present(student)
    return render_template("scan_identity.html", token=token, error=None, subject=session.subject)

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
@role_required("teacher", "college_admin")
def student_lookup():
    q = request.args.get("q", "").strip()
    students = []
    if q:
        query = User.query.filter_by(role="student", college_id=current_user.college_id, account_status="active").filter(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"), User.unique_code.ilike(f"%{q}%")))
        if current_user.role == "teacher":
            subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
            enrolled_ids = [e.student_id for e in Enrollment.query.filter(Enrollment.subject_id.in_(subject_ids)).all()] if subject_ids else []
            query = query.filter(User.id.in_(enrolled_ids))
        students = query.order_by(User.name).limit(100).all()
    return render_template("student_lookup.html", students=students, q=q)

@app.route("/teacher/student/<int:student_id>")
@role_required("teacher", "college_admin")
def student_detail(student_id):
    student = db.session.get(User, student_id)
    if not student or student.role != "student" or (current_user.role != "admin" and student.college_id != current_user.college_id):
        abort(404)
    if current_user.role == "teacher":
        subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
        if not Enrollment.query.filter(Enrollment.student_id == student.id, Enrollment.subject_id.in_(subject_ids)).first():
            abort(403)
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.marked_at.desc()).all()
    visible_subjects = Subject.query.filter(Subject.id.in_(subject_ids)).all() if current_user.role == "teacher" else Subject.query.filter_by(college_id=current_user.college_id).all()
    total_sessions = sum(AttendanceSession.query.filter_by(subject_id=sub.id).count() for sub in visible_subjects if Enrollment.query.filter_by(student_id=student.id, subject_id=sub.id).first())
    present_count = sum(1 for r in records if r.subject_id in {sub.id for sub in visible_subjects})
    pct = round(present_count / total_sessions * 100) if total_sessions else 0
    return render_template("student_detail.html", student=student, records=records, attendance_pct=min(pct, 100), present_count=present_count, total_sessions=total_sessions)

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
@role_required("teacher", "college_admin")
def review_corrections():
    query = CorrectionRequest.query.join(Subject, CorrectionRequest.subject_id == Subject.id).filter(Subject.college_id == current_user.college_id).order_by(CorrectionRequest.created_at.desc())
    if current_user.role == "teacher":
        subject_ids = [s.id for s in Subject.query.filter_by(teacher_id=current_user.id).all()]
        query = query.filter(CorrectionRequest.subject_id.in_(subject_ids))
    return render_template("review_corrections.html", items=query.limit(200).all())

@app.route("/teacher/corrections/<int:req_id>/<decision>", methods=["POST"])
@role_required("teacher", "college_admin")
def decide_correction(req_id, decision):
    if decision not in ("approve", "reject"):
        abort(400)
    item = db.session.get(CorrectionRequest, req_id)
    if not item:
        abort(404)
    if item.subject.college_id != current_user.college_id or (current_user.role == "teacher" and item.subject.teacher_id != current_user.id):
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

@app.route("/admin/college-requests")
@role_required("admin")
def college_requests():
    return render_template("college_requests.html", requests=CollegeRequest.query.order_by(CollegeRequest.created_at.desc()).all(), colleges=College.query.order_by(College.created_at.desc()).all())

@app.route("/admin/college-requests/<int:req_id>/<decision>", methods=["POST"])
@role_required("admin")
def decide_college_request(req_id, decision):
    if decision not in ("approve","reject"): abort(400)
    req=db.session.get(CollegeRequest,req_id)
    if not req or req.status!="pending": abort(404)
    req.status="approved" if decision=="approve" else "rejected"; req.reviewed_at=utcnow()
    if decision=="approve":
        college=College(name=req.college_name,official_email=req.official_email,address=req.address,code=generate_college_code(),status="approved")
        db.session.add(college); db.session.flush()
        admin=User(name=req.contact_name,email=req.official_email,password_hash=req.password_hash,role="college_admin",college_id=college.id,account_status="active")
        db.session.add(admin)
    db.session.commit(); log("college_request_"+decision, f"request={req_id}")
    flash("College approved and code generated." if decision=="approve" else "College request rejected.","success")
    return redirect(url_for("college_requests"))

@app.route("/college-admin")
@role_required("college_admin")
def college_admin_dashboard():
    college= db.session.get(College,current_user.college_id)
    return render_template("college_admin.html", college=college, users=User.query.filter_by(college_id=current_user.college_id).order_by(User.created_at.desc()).limit(200).all(), pending_teachers=User.query.filter_by(college_id=current_user.college_id,role="teacher",account_status="pending").all(), roster_count=StudentRoster.query.filter_by(college_id=current_user.college_id).count(), roster=StudentRoster.query.filter_by(college_id=current_user.college_id).order_by(StudentRoster.name).limit(300).all(), teacher_codes=TeacherInvite.query.filter_by(college_id=current_user.college_id,used=False).order_by(TeacherInvite.created_at.desc()).all(), subjects=Subject.query.filter_by(college_id=current_user.college_id).order_by(Subject.name).all(), approved_teachers=User.query.filter_by(college_id=current_user.college_id,role="teacher",account_status="active").order_by(User.name).all())

@app.route("/college-admin/subjects", methods=["POST"])
@role_required("college_admin")
def college_add_subject():
    name=request.form.get("name","").strip(); code=request.form.get("code","").strip().upper(); teacher_id=request.form.get("teacher_id",type=int)
    teacher=User.query.filter_by(id=teacher_id,college_id=current_user.college_id,role="teacher",account_status="active").first() if teacher_id else None
    if not name or not code or not teacher:
        flash("Enter a subject name, subject code and choose an approved teacher.","error")
    elif Subject.query.filter_by(college_id=current_user.college_id,code=code).first():
        flash("That subject code already exists in your college.","error")
    else:
        db.session.add(Subject(name=name,code=code,teacher_id=teacher.id,college_id=current_user.college_id)); db.session.commit(); log("college_subject_created",f"{code}: {name}"); flash("Subject added and assigned to teacher.","success")
    return redirect(url_for("college_admin_dashboard"))

@app.route("/college-admin/roster-add", methods=["POST"])
@role_required("college_admin")
def add_roster_student():
    """Add one student to the current college roster without requiring CSV upload."""
    sid = request.form.get("student_id", "").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    department = request.form.get("department", "").strip()
    year = request.form.get("year", "").strip()
    division = request.form.get("division", "").strip()
    return_to = request.form.get("return_to", "dashboard")
    redirect_target = "college_students_page" if return_to == "students" else "college_admin_dashboard"

    if not sid or not name or not email or "@" not in email or len(sid) > 80 or len(name) > 120 or len(email) > 255:
        flash("Student ID, full name and a valid email are required.", "error")
        return redirect(url_for(redirect_target))
    if StudentRoster.query.filter_by(college_id=current_user.college_id, student_id=sid).first():
        flash("That Student ID already exists in your college roster.", "error")
        return redirect(url_for(redirect_target))
    if StudentRoster.query.filter_by(college_id=current_user.college_id, email=email).first():
        flash("That email already exists in your college roster.", "error")
        return redirect(url_for(redirect_target))

    try:
        student = StudentRoster(
            college_id=current_user.college_id,
            student_id=sid,
            name=name,
            email=email,
            department=department,
            year=year,
            division=division,
            unique_code=generate_unique_code("STU"),
        )
        db.session.add(student)
        db.session.commit()
        log("roster_student_added", f"{sid}: {email}")
        flash(f"Student {name} added successfully. A unique registration code was generated.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Could not add this student because the Student ID or email already exists.", "error")
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to add individual student to roster")
        flash("Student could not be added right now. Please try again.", "error")
    return redirect(url_for(redirect_target))


@app.route("/college-admin/students")
@role_required("college_admin")
def college_students_page():
    return render_template(
        "college_students.html",
        roster=StudentRoster.query.filter_by(college_id=current_user.college_id).order_by(StudentRoster.name).limit(500).all(),
        roster_count=StudentRoster.query.filter_by(college_id=current_user.college_id).count(),
    )


@app.route("/college-admin/roster-upload", methods=["POST"])
@role_required("college_admin")
def upload_roster():
    f=request.files.get("roster")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Upload a CSV file with student_id,name,email,department,year,division columns.","error"); return redirect(url_for("college_admin_dashboard"))
    try:
        rows=csv.DictReader(io.StringIO(f.stream.read().decode("utf-8-sig")))
        required={"student_id","name","email"}
        if not required.issubset(set(rows.fieldnames or [])): raise ValueError("Missing required columns")
        count=0
        for row in rows:
            sid=(row.get("student_id") or "").strip(); name=(row.get("name") or "").strip(); email=(row.get("email") or "").strip().lower()
            if not sid or not name or not email: continue
            old=StudentRoster.query.filter_by(college_id=current_user.college_id,student_id=sid).first()
            if old: continue
            db.session.add(StudentRoster(college_id=current_user.college_id,student_id=sid,name=name,email=email,department=(row.get("department") or "").strip(),year=(row.get("year") or "").strip(),division=(row.get("division") or "").strip(),unique_code=generate_unique_code("STU"))); count+=1
        db.session.commit(); log("roster_uploaded",f"{count} records"); flash(f"Imported {count} student records.","success")
    except Exception:
        db.session.rollback(); flash("CSV could not be imported. Check UTF-8 encoding and required columns.","error")
    return redirect(url_for("college_admin_dashboard"))

@app.route("/college-admin/teacher/<int:user_id>/<decision>", methods=["POST"])
@role_required("college_admin")
def decide_teacher(user_id, decision):
    if decision not in ("approve","reject"): abort(400)
    teacher=User.query.filter_by(id=user_id,college_id=current_user.college_id,role="teacher",account_status="pending").first_or_404()
    teacher.account_status="active" if decision=="approve" else "rejected"; teacher.active=(decision=="approve"); db.session.commit(); log("teacher_"+decision,teacher.email); flash("Teacher request updated.","success"); return redirect(url_for("college_admin_dashboard"))

@app.route("/teacher/signup", methods=["GET","POST"])
def teacher_signup():
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); code=request.form.get("unique_code","").strip().upper()
        invite=TeacherInvite.query.filter_by(code=code,used=False).first()
        college=db.session.get(College,invite.college_id) if invite else None
        if not invite or not college or college.status!="approved" or not name or not email or len(password)<8:
            flash("Enter a valid teacher invitation code and complete all details.","error"); return redirect(url_for("teacher_signup"))
        if User.query.filter_by(email=email).first(): flash("This email is already registered.","error"); return redirect(url_for("login"))
        teacher=User(name=name,email=email,role="teacher",college_id=college.id,account_status="pending",active=False,unique_code=invite.code); teacher.set_password(password); invite.used=True; db.session.add(teacher); db.session.commit(); log("teacher_signup_pending",email); flash("Teacher registration successful. Your college admin must approve your account before login.","success"); return redirect(url_for("login"))
    return render_template("teacher_signup.html")

@app.route("/college-admin/teacher-code", methods=["POST"])
@role_required("college_admin")
def generate_teacher_code():
    code=generate_unique_code("TCH")
    db.session.add(TeacherInvite(college_id=current_user.college_id,code=code)); db.session.commit()
    flash(f"New teacher registration code generated: {code}","success")
    return redirect(url_for("college_admin_dashboard"))

@app.route("/college-admin/roster-codes.csv")
@role_required("college_admin")
def export_roster_codes():
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["student_id","name","email","unique_code","department","year","division","claimed"])
    rows=StudentRoster.query.filter_by(college_id=current_user.college_id).order_by(StudentRoster.name).all()
    for r in rows: writer.writerow([r.student_id,r.name,r.email,r.unique_code or "",r.department,r.year,r.division,"yes" if r.claimed else "no"])
    data=io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(data,mimetype="text/csv",as_attachment=True,download_name="attendx-student-codes.csv")

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
        user = User(name=name, email=email, role=role, unique_code=generate_unique_code("TCH" if role == "teacher" else "STU") if role in ("teacher", "student") else None)
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
    query = Attendance.query.join(Subject).join(User, Attendance.student_id == User.id)
    if current_user.role == "teacher":
        query = query.filter(Subject.teacher_id == current_user.id, Subject.college_id == current_user.college_id, User.college_id == current_user.college_id)
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
    # Gunicorn starts multiple workers; serialize schema creation and seeding
    # across those processes so two workers cannot CREATE the same table.
    try:
        import fcntl  # available on Heroku/Linux
    except ImportError:
        fcntl = None

    lock_file = open(os.path.join('/tmp', 'attendx-bootstrap.lock'), 'a+')
    try:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        with app.app_context():
            db.create_all()
            # Lightweight additive migration for existing SQLite/Postgres databases.
            from sqlalchemy import text, inspect
            inspector = inspect(db.engine)
            for table_name, column_name, ddl in [
                ("user", "unique_code", "VARCHAR(32)"),
                ("student_roster", "unique_code", "VARCHAR(32)"),
            ]:
                if table_name in inspector.get_table_names() and column_name not in [c["name"] for c in inspector.get_columns(table_name)]:
                    # Quote identifiers for PostgreSQL: `user` is a reserved keyword.
                    quoted_table = db.engine.dialect.identifier_preparer.quote(table_name)
                    quoted_column = db.engine.dialect.identifier_preparer.quote(column_name)
                    db.session.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {ddl}"))
            db.session.commit()
            # Backfill unique codes for records created before this update.
            for roster_row in StudentRoster.query.filter(StudentRoster.unique_code.is_(None)).all():
                roster_row.unique_code = generate_unique_code("STU")
            for account in User.query.filter(User.unique_code.is_(None), User.role.in_(["student", "teacher"])).all():
                account.unique_code = generate_unique_code("STU" if account.role == "student" else "TCH")
            db.session.commit()
            admin_email = os.getenv("ADMIN_EMAIL", info.ADMIN_EMAIL).strip().lower()
            admin_password = os.getenv("ADMIN_PASSWORD", info.ADMIN_PASSWORD)
            if admin_password.startswith("CHANGE-ME") or app.config["SECRET_KEY"].startswith("CHANGE-ME"):
                print("WARNING: Edit info.py and replace the CHANGE-ME values before using this app beyond local testing.")
            # Multiple Gunicorn workers can run bootstrap() simultaneously.
            # Re-check and gracefully handle the unique-email race instead of
            # crashing a worker when another worker creates the admin first.
            # Keep the configured super-admin account usable after credentials are
            # changed in the hosting dashboard. Never sync the placeholder password.
            if admin_email and admin_password and not admin_password.startswith("CHANGE-ME"):
                admin = User.query.filter_by(email=admin_email).first()
                if admin is None:
                    try:
                        admin = User(name="System Admin", email=admin_email, role="admin")
                        admin.set_password(admin_password)
                        db.session.add(admin)
                        db.session.commit()
                    except IntegrityError:
                        db.session.rollback()
                        admin = User.query.filter_by(email=admin_email).first()
                        if admin is None:
                            raise
                # Only update a matching admin account, never convert a college or
                # student account into an administrator because of an email collision.
                if admin.role == "admin":
                    admin.set_password(admin_password)
                    admin.active = True
                    admin.account_status = "active"
                    db.session.commit()
    finally:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()

bootstrap()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", str(info.PORT))), debug=os.getenv("FLASK_DEBUG", "1" if info.FLASK_DEBUG else "0") == "1")
