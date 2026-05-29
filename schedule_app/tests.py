from datetime import date, time

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AcademicYear,
    BellSchedule,
    ClassGroup,
    CurriculumPlan,
    Room,
    SanpinLimit,
    ScheduleEntry,
    School,
    Subject,
    Teacher,
    TeacherSchool,
    TeacherSubject,
)


class GenerateScheduleTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", password="pass12345", is_staff=True)
        token = RefreshToken.for_user(self.admin).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.school = School.objects.create(name="School", week_days_count=5, shift_count=1)
        self.year = AcademicYear.objects.create(
            school=self.school,
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            total_weeks=34,
        )
        for period in range(1, 5):
            BellSchedule.objects.create(
                school=self.school,
                shift_number=1,
                period_number=period,
                start_time=time(8 + period, 0),
                end_time=time(8 + period, 45),
            )
        SanpinLimit.objects.create(
            grade_from=1,
            grade_to=11,
            max_periods_5day=4,
            max_periods_6day=5,
            lesson_duration_max=45,
        )

        self.class_group = ClassGroup.objects.create(
            school=self.school,
            academic_year=self.year,
            name="5A",
            grade_number=5,
            shift_number=1,
        )
        self.room = Room.objects.create(school=self.school, number="101")
        self.math = Subject.objects.create(name="Math")
        self.russian = Subject.objects.create(name="Russian")
        self.math_teacher = Teacher.objects.create(full_name="Math Teacher")
        self.russian_teacher = Teacher.objects.create(full_name="Russian Teacher")
        for teacher in [self.math_teacher, self.russian_teacher]:
            TeacherSchool.objects.create(
                teacher=teacher,
                school=self.school,
                weekly_hours_norm=2,
                weekly_hours_max=10,
            )
        TeacherSubject.objects.create(teacher=self.math_teacher, subject=self.math, is_primary=True)
        TeacherSubject.objects.create(teacher=self.russian_teacher, subject=self.russian, is_primary=True)
        CurriculumPlan.objects.create(
            class_group=self.class_group,
            subject=self.math,
            hours_per_week=2,
            semester="full_year",
        )
        CurriculumPlan.objects.create(
            class_group=self.class_group,
            subject=self.russian,
            hours_per_week=1,
            semester="full_year",
        )

    def test_generate_creates_frontend_schedule_entries(self):
        response = self.client.post(
            reverse("schedule-generate"),
            {"academic_year_id": self.year.id},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["generated_count"], 3)
        self.assertEqual(response.data["unscheduled_count"], 0)

        entries = ScheduleEntry.objects.filter(academic_year=self.year)
        self.assertEqual(entries.count(), 3)
        self.assertEqual(entries.filter(class_group=self.class_group, subject=self.math).count(), 2)
        self.assertTrue(entries.filter(class_group=self.class_group, subject=self.russian).exists())

        list_response = self.client.get("/api/schedule/", {"academic_year": self.year.id})
        self.assertEqual(list_response.status_code, 200)
        results = list_response.data["results"]
        self.assertEqual(len(results), 3)
        self.assertIn("class_group", results[0])
        self.assertIn("subject", results[0])
        self.assertIn("teacher", results[0])
        self.assertIn("room", results[0])
