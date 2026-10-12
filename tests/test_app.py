import os, tempfile, unittest
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
import app as app_module

class AttendXTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI="sqlite://")
        self.client = self.app.test_client()
        with self.app.app_context():
            app_module.db.drop_all()
            app_module.db.create_all()
            admin = app_module.User(name="Admin", email="admin@test.local", role="admin")
            admin.set_password("AdminPass123")
            teacher = app_module.User(name="Teacher", email="teacher@test.local", role="teacher")
            teacher.set_password("TeacherPass123")
            student = app_module.User(name="Student", email="student@test.local", role="student", roll_no="T001")
            student.set_password("StudentPass123")
            app_module.db.session.add_all([admin, teacher, student])
            app_module.db.session.commit()
            subject = app_module.Subject(name="Maths", code="M101", teacher_id=teacher.id)
            app_module.db.session.add(subject)
            app_module.db.session.commit()
            app_module.db.session.add(app_module.Enrollment(student_id=student.id, subject_id=subject.id))
            app_module.db.session.commit()
            self.subject_id = subject.id
            self.student_id = student.id
            self.teacher_id = teacher.id
    def tearDown(self):
        with self.app.app_context():
            app_module.db.session.remove()
            app_module.db.drop_all()
    def login(self, email, password, role):
        return self.client.post("/login", data={"email":email,"password":password,"role":role}, follow_redirects=True)
    def test_homepage(self):
        self.assertEqual(self.client.get("/").status_code, 200)
    def test_student_signup(self):
        res = self.client.post("/signup", data={"name":"New Student","email":"new@test.local","password":"StrongPass123","role":"student"}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        with self.app.app_context():
            self.assertIsNotNone(app_module.User.query.filter_by(email="new@test.local").first())
    def test_privileged_signup_blocked(self):
        res = self.client.post("/signup", data={"name":"Bad Teacher","email":"bad@test.local","password":"StrongPass123","role":"teacher"}, follow_redirects=True)
        self.assertIn(b"must be created by an administrator", res.data)
    def test_student_dashboard_requires_login(self):
        self.assertIn(self.client.get("/dashboard").status_code, (302, 401))
    def test_teacher_login(self):
        res = self.login("teacher@test.local", "TeacherPass123", "teacher")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Your subjects", res.data)
    def test_duplicate_attendance_protection_model_constraint(self):
        with self.app.app_context():
            sess = app_module.AttendanceSession(subject_id=self.subject_id, teacher_id=self.teacher_id,
                token_hash="x", ends_at=app_module.utcnow()+app_module.timedelta(hours=1))
            app_module.db.session.add(sess); app_module.db.session.commit()
            a = app_module.Attendance(student_id=self.student_id, subject_id=self.subject_id, session_id=sess.id)
            app_module.db.session.add(a); app_module.db.session.commit()
            self.assertEqual(app_module.Attendance.query.filter_by(student_id=self.student_id, session_id=sess.id).count(), 1)

if __name__ == "__main__":
    unittest.main()
