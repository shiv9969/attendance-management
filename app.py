            old=StudentRoster.query.filter_by(college_id=current_user.college_id,student_id=sid).first()
            if old: continue
            db.session.add(StudentRoster(college_id=current_user.college_id,student_id=sid,name=name,email=email,department=(row.get("department") or "").strip(),year=(row.get("year") or "").strip(),division=(row.get("division") or "").strip())); count+=1
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
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); code=request.form.get("college_code","").strip().upper()
        college=college_from_code(code)
        if not college or not name or not email or len(password)<8: flash("Enter valid details and an approved College Code.","error"); return redirect(url_for("teacher_signup"))
        if User.query.filter_by(email=email).first(): flash("This email is already registered.","error"); return redirect(url_for("login"))
        teacher=User(name=name,email=email,role="teacher",college_id=college.id,account_status="pending",active=False); teacher.set_password(password); db.session.add(teacher); db.session.commit(); log("teacher_signup_pending",email); flash("Teacher request submitted. Your college admin must approve it before login.","success"); return redirect(url_for("login"))
    return render_template("teacher_signup.html")

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
    with app.app_context():
        db.create_all()
        # Lightweight compatibility migration for databases created before
        # the multi-college fields were added to the User model.
        # PostgreSQL is used on Heroku; SQLite is supported for local runs.
        if db.engine.dialect.name == "postgresql":
            with db.engine.begin() as conn:
                conn.exec_driver_sql(
                    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS college_id INTEGER'
                )
                conn.exec_driver_sql(
                    "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) NOT NULL DEFAULT 'active'"
                )
        elif db.engine.dialect.name == "sqlite":
            from sqlalchemy import inspect
            columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
            with db.engine.begin() as conn:
                if "college_id" not in columns:
                    conn.exec_driver_sql('ALTER TABLE "user" ADD COLUMN college_id INTEGER')
                if "account_status" not in columns:
                    conn.exec_driver_sql(
                        "ALTER TABLE \"user\" ADD COLUMN account_status VARCHAR(20) NOT NULL DEFAULT 'active'"
                    )
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

