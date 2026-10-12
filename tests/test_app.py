import os, unittest
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
import app as app_module

class AttendXTests(unittest.TestCase):
    def setUp(self):
        self.app=app_module.app; self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
        self.client=self.app.test_client()
        with self.app.app_context():
            app_module.db.drop_all(); app_module.db.create_all()
            admin=app_module.User(name="Super Admin",email="root@test.local",role="admin"); admin.set_password("RootPass123")
            self.college=app_module.College(name="Example College",official_email="college@test.local",address="Test Road",code="ATX-ABC123",status="approved")
            app_module.db.session.add_all([admin,self.college]); app_module.db.session.flush()
            teacher=app_module.User(name="Teacher",email="teacher@test.local",role="teacher",college_id=self.college.id,account_status="active"); teacher.set_password("TeacherPass123")
            app_module.db.session.add(teacher)
            app_module.db.session.add(app_module.StudentRoster(college_id=self.college.id,student_id="S001",name="Student One",email="student@test.local",department="CS",year="2"))
            app_module.db.session.commit(); self.college_id=self.college.id
    def tearDown(self):
        with self.app.app_context(): app_module.db.session.remove(); app_module.db.drop_all()
    def test_homepage_and_college_registration_form(self):
        self.assertEqual(self.client.get("/").status_code,200)
        self.assertEqual(self.client.get("/college/register").status_code,200)
    def test_role_is_database_driven(self):
        response=self.client.post("/login",data={"email":"teacher@test.local","password":"TeacherPass123","college_code":"ATX-ABC123"},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertIn(b"Your subjects",response.data)
    def test_wrong_college_code_denied(self):
        response=self.client.post("/login",data={"email":"teacher@test.local","password":"TeacherPass123","college_code":"ATX-WRONG"},follow_redirects=True)
        self.assertIn(b"Enter the approved College Code",response.data)
    def test_student_signup_requires_roster_match_and_otp(self):
        original=app_module.issue_otp; app_module.issue_otp=lambda *args: True
        try:
            response=self.client.post("/signup",data={"name":"Student One","email":"student@test.local","password":"StudentPass123","college_code":"ATX-ABC123","roll_no":"S001"},follow_redirects=True)
            self.assertEqual(response.status_code,200)
            self.assertIn(b"6-digit verification code",response.data)
            with self.app.app_context(): self.assertIsNone(app_module.User.query.filter_by(email="student@test.local").first())
        finally: app_module.issue_otp=original
    def test_teacher_signup_is_pending_and_cannot_login(self):
        self.client.post("/teacher/signup",data={"name":"Pending Teacher","email":"pending@test.local","password":"TeacherPass123","college_code":"ATX-ABC123"})
        with self.app.app_context():
            u=app_module.User.query.filter_by(email="pending@test.local").first(); self.assertIsNotNone(u); self.assertEqual(u.account_status,"pending"); self.assertFalse(u.active)
    def test_duplicate_attendance_constraint(self):
        with self.app.app_context():
            teacher=app_module.User.query.filter_by(email="teacher@test.local").first()
            subject=app_module.Subject(name="Maths",code="M101",teacher_id=teacher.id,college_id=self.college_id); app_module.db.session.add(subject); app_module.db.session.commit()
            sess=app_module.AttendanceSession(subject_id=subject.id,teacher_id=teacher.id,token_hash="x",ends_at=app_module.utcnow()+app_module.timedelta(hours=1)); app_module.db.session.add(sess); app_module.db.session.commit()
            student=app_module.User(name="Student One",email="s2@test.local",password_hash="x",role="student",college_id=self.college_id,account_status="active"); app_module.db.session.add(student); app_module.db.session.commit()
            app_module.db.session.add(app_module.Attendance(student_id=student.id,subject_id=subject.id,session_id=sess.id)); app_module.db.session.commit()
            self.assertEqual(app_module.Attendance.query.filter_by(student_id=student.id,session_id=sess.id).count(),1)

if __name__=="__main__": unittest.main()
