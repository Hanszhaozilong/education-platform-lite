"""Behavior and access-boundary tests; no production database is used."""
import unittest
from datetime import datetime

from werkzeug.security import generate_password_hash

from lite import Attendance, Classroom, Lead, Lesson, Notice, User, create_app, db


class LiteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-only-" * 8,
                               "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        for username, role, subjects in (("admin", "admin", ""), ("principal", "principal", ""),
                                         ("teacher", "teacher", "数学,英语"),
                                         ("other", "teacher", "语文"), ("student", "student", ""),
                                         ("second", "student", "")):
            db.session.add(User(username=username, name=username, role=role,
                                subjects=subjects, private_note="PRIVATE-NOTE",
                                password_hash=generate_password_hash("test-password-123")))
        db.session.add(Classroom(name="Test room"))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def user(self, username):
        return User.query.filter_by(username=username).one()

    def login(self, username):
        self.client.get("/login")
        with self.client.session_transaction() as current:
            token = current["csrf"]
        response = self.client.post("/login", data={"csrf": token, "username": username,
                                                   "password": "test-password-123"})
        self.assertEqual(response.status_code, 302)

    def post(self, url, **data):
        with self.client.session_transaction() as current:
            token = current["csrf"]
        return self.client.post(url, data={"csrf": token, **data})

    def lesson(self, teacher="teacher", start="2030-10-07T13:00", end="2030-10-07T15:00"):
        row = Lesson(subject="数学", teacher_id=self.user(teacher).id, students=[self.user("student"), self.user("second")],
                     starts_at=datetime.fromisoformat(start), ends_at=datetime.fromisoformat(end), classroom_id=1)
        db.session.add(row)
        db.session.commit()
        return row

    def new_lesson(self, **overrides):
        data = dict(subject="数学", teacher_id=str(self.user("teacher").id),
                    students=[str(self.user("student").id)], classroom_id="1",
                    starts_at="2030-10-07T13:00", ends_at="2030-10-07T15:00")
        data.update(overrides)
        return self.post("/schedule/new", **data)

    def test_all_manager_pages_render(self):
        self.login("admin")
        self.lesson()
        for path in ("/", "/people", "/people/new", "/schedule?date=2030-10-07", "/schedule/new",
                     "/schedule/1", "/classrooms", "/leads", "/notices", "/profile", "/support"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("泪见雪.".encode(), response.data)

    def test_support_is_public_and_contacts_match(self):
        response = self.client.get("/support")
        for value in ("NekoByte_Zzl", "2578783496", "http://154.36.185.225/", "support-wechat.jpg"):
            self.assertIn(value.encode(), response.data)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_csrf_required_for_changes(self):
        self.login("admin")
        self.assertEqual(self.client.post("/classrooms", data={"action": "create", "name": "Bad"}).status_code, 400)
        self.assertEqual(Classroom.query.count(), 1)

    def test_staff_permissions_and_note_privacy(self):
        self.login("teacher")
        for path in ("/people", "/people/new", "/leads", "/schedule/new"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.post("/notices", title="bad", body="bad").status_code, 403)
        for path in ("/", "/profile", "/classrooms", "/schedule"):
            self.assertNotIn(b"PRIVATE-NOTE", self.client.get(path).data)

    def test_principal_cannot_promote_or_edit_admin(self):
        self.login("principal")
        self.assertEqual(self.post("/people/new", role="admin", name="New", username="new",
                                   password="test-password-123").status_code, 403)
        self.assertEqual(self.client.get(f"/people/{self.user('admin').id}/edit").status_code, 403)

    def test_student_only_sees_own_attendance(self):
        row = self.lesson()
        other = self.user("other")
        self.login("other")
        self.assertEqual(self.client.get(f"/schedule/{row.id}").status_code, 403)
        self.assertEqual(self.post(f"/schedule/{row.id}/attendance").status_code, 403)
        self.login("student")
        response = self.client.get(f"/schedule/{row.id}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<strong>second</strong>", response.data)
        self.assertEqual(self.post(f"/schedule/{row.id}/attendance").status_code, 403)

    def test_teacher_subject_validation(self):
        self.login("admin")
        self.assertEqual(self.new_lesson(teacher_id=str(self.user("other").id)).status_code, 400)
        self.assertEqual(Lesson.query.count(), 0)
        self.assertEqual(self.new_lesson().status_code, 302)

    def test_teacher_room_and_student_conflicts(self):
        self.login("admin")
        self.assertEqual(self.new_lesson().status_code, 302)
        for overrides in ({}, {"subject": "语文", "teacher_id": str(self.user("other").id)},
                          {"subject": "语文", "teacher_id": str(self.user("other").id), "classroom_id": ""}):
            self.assertEqual(self.new_lesson(**overrides).status_code, 400)
        self.assertEqual(Lesson.query.count(), 1)
        self.assertEqual(self.new_lesson(starts_at="2030-10-07T15:00", ends_at="2030-10-07T17:00").status_code, 302)

    def test_closed_room_and_invalid_dates(self):
        self.login("admin")
        db.session.get(Classroom, 1).status = "maintenance"
        db.session.commit()
        self.assertEqual(self.new_lesson().status_code, 400)
        self.assertEqual(self.new_lesson(classroom_id="", ends_at="2030-10-07T12:00").status_code, 400)
        self.assertEqual(self.new_lesson(classroom_id="", students=[]).status_code, 400)

    def test_manual_attendance_rounding_and_upsert(self):
        row = self.lesson()
        self.login("teacher")
        first, second = self.user("student").id, self.user("second").id
        response = self.post(f"/schedule/{row.id}/attendance", **{f"minutes_{first}": "31",
                             f"present_{first}": "on", f"minutes_{second}": "120"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.query.filter_by(student_id=first).one().rounded_hours, 1)
        self.assertEqual(Attendance.query.filter_by(student_id=second).one().rounded_hours, 0)
        self.post(f"/schedule/{row.id}/attendance", **{f"minutes_{first}": "25",
                  f"present_{first}": "on", f"minutes_{second}": "120"})
        self.assertEqual(Attendance.query.count(), 2)
        self.assertEqual(Attendance.query.filter_by(student_id=first).one().rounded_hours, .5)
        self.login("admin")
        self.assertEqual(self.post(f"/schedule/{row.id}/delete").status_code, 400)

    def test_duplicate_phone_has_human_message(self):
        self.login("admin")
        data = dict(role="student", username="demo1", name="Demo", phone="19900000001", grade="7",
                    phone_owner="母亲", password="test-password-123")
        self.assertEqual(self.post("/people/new", **data).status_code, 302)
        data["username"] = "demo2"
        response = self.post("/people/new", **data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("已被其他账户占用".encode(), response.data)

    def test_classroom_notes_are_manager_only(self):
        room = db.session.get(Classroom, 1)
        room.note, room.status = "PRIVATE-OCCUPANT", "occupied"
        db.session.commit()
        self.login("teacher")
        self.assertNotIn(b"PRIVATE-OCCUPANT", self.client.get("/classrooms").data)
        self.assertEqual(self.post("/classrooms", room_id="1", status="free").status_code, 403)
        self.login("admin")
        self.assertIn(b"PRIVATE-OCCUPANT", self.client.get("/classrooms").data)

    def test_multi_trial_lost_restore_and_delete(self):
        self.login("admin")
        response = self.post("/leads", name="Demo", phone="19900000001", grade="8", note="Test",
                             trial_subject=["数学", "英语"],
                             trial_teacher=[str(self.user("teacher").id)] * 2,
                             trial_time=["2030-10-07T10:00", "2030-10-08T10:00"])
        self.assertEqual(response.status_code, 302)
        row = Lead.query.one()
        self.assertEqual(len(row.trials), 2)
        self.post(f"/leads/{row.id}/lost")
        self.assertEqual(row.status, "lost")
        self.assertEqual(self.post(f"/leads/{row.id}/convert", password="test-password-123").status_code, 400)
        self.post(f"/leads/{row.id}/restore")
        self.assertEqual(row.status, "trial")
        self.assertEqual(self.post(f"/leads/{row.id}/delete").status_code, 302)
        self.assertEqual(Lead.query.count(), 0)

    def test_conversion_preserves_history(self):
        self.login("admin")
        self.post("/leads", name="Demo", phone="19900000001", grade="10", note="PRIVATE-LEAD")
        row = Lead.query.one()
        self.assertEqual(self.post(f"/leads/{row.id}/convert", password="test-password-123").status_code, 302)
        self.assertEqual(row.status, "converted")
        student = db.session.get(User, row.student_id)
        self.assertEqual(student.grade, 10)
        self.assertEqual(student.private_note, "PRIVATE-LEAD")
        self.assertEqual(self.post(f"/leads/{row.id}/delete").status_code, 400)

    def test_xss_is_escaped(self):
        db.session.add(Notice(title="<script>alert(1)</script>", body="<img src=x onerror=alert(1)>"))
        db.session.commit()
        self.login("student")
        data = self.client.get("/notices").data
        self.assertIn(b"&lt;script&gt;", data)
        self.assertNotIn(b"<img src=x", data)

    def test_login_throttling_survives_new_session(self):
        for _ in range(5):
            self.client = self.app.test_client()
            self.client.get("/login")
            self.post("/login", username="admin", password="wrong")
        self.client = self.app.test_client()
        self.client.get("/login")
        self.assertEqual(self.post("/login", username="admin", password="test-password-123").status_code, 429)

    def test_password_change_invalidates_other_sessions(self):
        self.login("teacher")
        other_client = self.app.test_client()
        with other_client.session_transaction() as current:
            current.update(user_id=self.user("teacher").id, version=0, csrf="test-token")
        self.assertEqual(other_client.get("/profile").status_code, 200)
        self.assertEqual(self.post("/profile", old_password="test-password-123", password="new-password-123").status_code, 302)
        self.assertEqual(other_client.get("/profile").status_code, 302)

    def test_advanced_modules_are_not_shipped(self):
        self.login("admin")
        for path in ("/finance/", "/billing/", "/mini-api/v1/home", "/chat/", "/payroll/rates", "/course/qr_checkin"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_initialization_never_resets_existing_data(self):
        result = self.app.test_cli_runner().invoke(args=["init-db", "--username", "new-admin",
                                                       "--password", "test-password-123"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(User.query.count(), 6)
        self.assertEqual(Classroom.query.count(), 1)
        self.assertIsNone(User.query.filter_by(username="new-admin").first())

    def test_new_install_requires_own_admin_password(self):
        User.query.delete()
        db.session.commit()
        runner = self.app.test_cli_runner()
        bad = runner.invoke(args=["init-db", "--username", "owner", "--password", "short"])
        self.assertNotEqual(bad.exit_code, 0)
        self.assertEqual(User.query.count(), 0)
        good = runner.invoke(args=["init-db", "--username", "owner", "--password", "owner-password-123"])
        self.assertEqual(good.exit_code, 0)
        self.assertEqual(self.user("owner").role, "admin")


if __name__ == "__main__":
    unittest.main()
