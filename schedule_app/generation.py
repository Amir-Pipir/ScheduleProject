from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction

from .models import (
    AcademicYear,
    BellSchedule,
    ClassGroup,
    CurriculumPlan,
    Room,
    RoomUnavailability,
    SanpinLimit,
    ScheduleEntry,
    SubjectRoomRequirement,
    TeacherSchool,
    TeacherSubject,
    TeacherUnavailability,
)


@dataclass(frozen=True)
class LessonTask:
    class_group_id: int
    class_group_name: str
    grade_number: int
    shift_number: int
    subject_id: int
    subject_name: str
    difficulty_rank: int
    subgroup_id: int | None = None
    week_parity: int = 0


@dataclass(frozen=True)
class Candidate:
    day: int
    period: int
    teacher_id: int
    room_id: int
    score: int


import logging

logger = logging.getLogger(__name__)


class ScheduleGenerator:
    def __init__(self, academic_year_id: int):
        self.academic_year = AcademicYear.objects.select_related("school").get(pk=academic_year_id)
        self.school = self.academic_year.school
        self.days = list(range(1, self.school.week_days_count + 1))
        self.entries: list[ScheduleEntry] = []
        self.unscheduled: list[dict] = []

        self.class_busy = set()
        self.teacher_busy = set()
        self.room_busy = set()
        self.class_day_load = defaultdict(int)
        self.teacher_load = defaultdict(int)
        self.teacher_day_periods = defaultdict(set)
        self.class_subject_days = defaultdict(set)
        self.room_load = defaultdict(int)

        self.class_groups = []
        self.bells_by_shift = defaultdict(list)
        self.max_period_by_shift = {}
        self.sanpin_by_grade = {}
        self.teacher_ids_by_subject = defaultdict(list)
        self.teacher_max_hours = {}
        self.rooms = []
        self.room_ids_by_subject = defaultdict(list)
        self.subjects_with_room_requirements = set()
        self.teacher_unavailable = set()
        self.room_unavailable = set()
        self.teacher_day_periods = defaultdict(set)

    def run(self):
        try:
            self._load_context()
            tasks = self._build_tasks()
            if not tasks:
                return self._result(0)

            tasks.sort(key=self._task_sort_key)
            solved = self._solve(tasks, 0)

            if not solved:
                self.entries = []
                if not self.unscheduled:
                    self.unscheduled.append(
                        {
                            "reason": "constraints_conflict",
                            "detail": "Не удалось разместить все уроки без нарушения ограничений.",
                        }
                    )
                return self._result(0)

            with transaction.atomic():
                ScheduleEntry.objects.filter(
                    academic_year=self.academic_year,
                    class_group__school=self.school,
                    is_substitution=False,
                ).delete()
                ScheduleEntry.objects.bulk_create(self.entries)

            return self._result(len(self.entries))
        except Exception as e:
            logger.exception("Ошибка в ScheduleGenerator.run")
            return {
                "detail": f"Ошибка генерации: {e}",
                "academic_year_id": self.academic_year.id,
                "generated_count": 0,
                "unscheduled_count": 1,
                "unscheduled": [{"reason": "exception", "detail": str(e)}],
            }

    def _load_context(self):
        self.class_groups = list(
            ClassGroup.objects.filter(academic_year=self.academic_year, school=self.school)
            .select_related("school", "academic_year")
            .order_by("grade_number", "name")
        )

        for bell in BellSchedule.objects.filter(school=self.school).order_by("shift_number", "period_number"):
            self.bells_by_shift[bell.shift_number].append(bell.period_number)
            self.max_period_by_shift[bell.shift_number] = max(
                self.max_period_by_shift.get(bell.shift_number, 0),
                bell.period_number,
            )

        for limit in SanpinLimit.objects.all():
            max_periods = (
                limit.max_periods_5day
                if self.school.week_days_count == 5
                else limit.max_periods_6day
            )
            for grade in range(limit.grade_from, limit.grade_to + 1):
                self.sanpin_by_grade[grade] = max_periods

        teacher_school = TeacherSchool.objects.filter(school=self.school).select_related("teacher")
        school_teacher_ids = {item.teacher_id for item in teacher_school}
        self.teacher_max_hours = {
            item.teacher_id: int(item.weekly_hours_max or item.weekly_hours_norm or 10**6)
            for item in teacher_school
        }

        for item in (
            TeacherSubject.objects.filter(teacher_id__in=school_teacher_ids)
            .select_related("teacher", "subject")
            .order_by("-is_primary", "teacher__full_name")
        ):
            self.teacher_ids_by_subject[item.subject_id].append(item.teacher_id)

        self.rooms = list(Room.objects.filter(school=self.school).order_by("-is_specialized", "number"))
        room_requirements = defaultdict(list)
        for requirement in SubjectRoomRequirement.objects.select_related("subject"):
            room_requirements[requirement.subject_id].append(requirement.required_room_type)

        all_room_ids = [room.id for room in self.rooms]
        for subject_id, required_types in room_requirements.items():
            self.subjects_with_room_requirements.add(subject_id)
            self.room_ids_by_subject[subject_id] = [
                room.id for room in self.rooms if room.type in required_types
            ]
        self.default_room_ids = all_room_ids

        self._load_unavailability()

    def _load_unavailability(self):
        year_start = self.academic_year.start_date
        year_end = self.academic_year.end_date

        for item in TeacherUnavailability.objects.filter(
            date_from__lte=year_end,
            date_to__gte=year_start,
        ):
            days = [item.day_of_week] if item.day_of_week else self.days
            periods = [item.period_number] if item.period_number else range(1, 20)
            for day in days:
                for period in periods:
                    self.teacher_unavailable.add((item.teacher_id, day, period))

        unavailable_room_ids = set(
            RoomUnavailability.objects.filter(
                room__school=self.school,
                date_from__lte=year_end,
                date_to__gte=year_start,
            ).values_list("room_id", flat=True)
        )
        for room_id in unavailable_room_ids:
            for day in self.days:
                for period in range(1, 20):
                    self.room_unavailable.add((room_id, day, period))

    def _build_tasks(self):
        plans = (
            CurriculumPlan.objects.filter(class_group__in=self.class_groups)
            .select_related("class_group", "subject", "subject__difficulty_rank")
            .order_by("class_group__grade_number", "class_group__name", "subject__name")
        )

        # Current ScheduleEntry has no semester field, so one weekly template cannot
        # represent different autumn/spring loads. Prefer full-year rows; otherwise
        # use the highest semester load for the subject.
        chosen = {}
        for plan in plans:
            key = (plan.class_group_id, plan.subject_id)
            current = chosen.get(key)
            if current is None:
                chosen[key] = plan
                continue
            if plan.semester == "full_year":
                chosen[key] = plan
            elif current.semester != "full_year" and plan.hours_per_week > current.hours_per_week:
                chosen[key] = plan

        tasks = []
        for plan in chosen.values():
            difficulty_rank = plan.subject.difficulty_rank_id or 5
            for _ in range(plan.hours_per_week):
                tasks.append(
                    LessonTask(
                        class_group_id=plan.class_group_id,
                        class_group_name=plan.class_group.name,
                        grade_number=plan.class_group.grade_number,
                        shift_number=plan.class_group.shift_number,
                        subject_id=plan.subject_id,
                        subject_name=plan.subject.name,
                        difficulty_rank=difficulty_rank,
                        subgroup_id=getattr(plan, "subgroup_id", None),
                    )
                )
        return tasks

    def _task_sort_key(self, task: LessonTask):
        teacher_count = len(self.teacher_ids_by_subject.get(task.subject_id, []))
        room_count = len(self._room_ids_for_subject(task.subject_id))
        slot_count = len(self._slots_for_class(task))
        return (
            teacher_count or 10**6,
            room_count or 10**6,
            slot_count or 10**6,
            task.difficulty_rank,
            -task.grade_number,
            task.class_group_name,
            task.subject_name,
        )

    def _solve(self, tasks, index):
        if index >= len(tasks):
            return True

        task = tasks[index]
        candidates = self._candidates_for(task)

        if not candidates:
            return False

        for candidate in candidates:
            self._place(task, candidate)
            if self._solve(tasks, index + 1):
                return True
            self._rollback(task, candidate)

        return False

    def _candidates_for(self, task: LessonTask):
        candidates = []
        teacher_ids = self.teacher_ids_by_subject.get(task.subject_id, [])
        room_ids = self._room_ids_for_subject(task.subject_id)

        for day, period in self._slots_for_class(task):
            if self.class_day_load[(task.class_group_id, day)] >= self._max_periods_for_grade(task.grade_number):
                continue
            if (task.class_group_id, task.subgroup_id, day, period, task.week_parity) in self.class_busy:
                continue

            for teacher_id in teacher_ids:
                if not self._teacher_available(teacher_id, day, period):
                    continue
                if self.teacher_load[teacher_id] >= self.teacher_max_hours.get(teacher_id, 10**6):
                    continue

                for room_id in room_ids:
                    if not self._room_available(room_id, day, period):
                        continue
                    candidates.append(
                        Candidate(
                            day=day,
                            period=period,
                            teacher_id=teacher_id,
                            room_id=room_id,
                            score=self._score(task, teacher_id, room_id, day, period),
                        )
                    )

        candidates.sort(key=lambda item: (item.score, item.day, item.period))
        return candidates[:40]

    def _slots_for_class(self, task: LessonTask):
        periods = self.bells_by_shift.get(task.shift_number)
        if not periods:
            periods = list(range(1, self._max_periods_for_grade(task.grade_number) + 1))
        max_periods = self._max_periods_for_grade(task.grade_number)
        return [
            (day, period)
            for day in self.days
            for period in periods
            if period <= max_periods
        ]

    def _room_ids_for_subject(self, subject_id):
        if subject_id in self.subjects_with_room_requirements:
            return self.room_ids_by_subject.get(subject_id, [])
        required_rooms = self.room_ids_by_subject.get(subject_id)
        return required_rooms if required_rooms else self.default_room_ids

    def _max_periods_for_grade(self, grade_number):
        return self.sanpin_by_grade.get(grade_number, max(self.max_period_by_shift.values() or [8]))

    def _teacher_available(self, teacher_id, day, period):
        return (
            (teacher_id, day, period, 0) not in self.teacher_busy
            and (teacher_id, day, period) not in self.teacher_unavailable
        )

    def _room_available(self, room_id, day, period):
        return (
            (room_id, day, period, 0) not in self.room_busy
            and (room_id, day, period) not in self.room_unavailable
        )

    def _score(self, task, teacher_id, room_id, day, period):
        score = 0

        # Prefer compact class days without late lessons.
        if period > 4 and task.difficulty_rank <= 3:
            score += 60
        if period > self.class_day_load[(task.class_group_id, day)] + 1:
            score += 80

        # Spread same subject across days.
        if day in self.class_subject_days[(task.class_group_id, task.subject_id)]:
            score += 45

        # Balance class load and reduce teacher windows.
        score += self.class_day_load[(task.class_group_id, day)] * 8
        teacher_periods = self.teacher_day_periods[(teacher_id, day)]
        if teacher_periods and period not in {min(teacher_periods) - 1, max(teacher_periods) + 1}:
            score += 35

        score += self.teacher_load[teacher_id] * 3
        score += self.room_load[room_id]
        return score

    def _place(self, task, candidate):
        self.entries.append(
            ScheduleEntry(
                class_group_id=task.class_group_id,
                subgroup_id=task.subgroup_id,
                subject_id=task.subject_id,
                teacher_id=candidate.teacher_id,
                room_id=candidate.room_id,
                academic_year=self.academic_year,
                day_of_week=candidate.day,
                period_number=candidate.period,
                week_parity=task.week_parity,
                is_substitution=False,
            )
        )
        self.class_busy.add((task.class_group_id, task.subgroup_id, candidate.day, candidate.period, task.week_parity))
        self.teacher_busy.add((candidate.teacher_id, candidate.day, candidate.period, task.week_parity))
        self.room_busy.add((candidate.room_id, candidate.day, candidate.period, task.week_parity))
        self.class_day_load[(task.class_group_id, candidate.day)] += 1
        self.teacher_load[candidate.teacher_id] += 1
        self.teacher_day_periods[(candidate.teacher_id, candidate.day)].add(candidate.period)
        self.class_subject_days[(task.class_group_id, task.subject_id)].add(candidate.day)
        self.room_load[candidate.room_id] += 1

    def _rollback(self, task, candidate):
        self.entries.pop()
        self.class_busy.remove((task.class_group_id, task.subgroup_id, candidate.day, candidate.period, task.week_parity))
        self.teacher_busy.remove((candidate.teacher_id, candidate.day, candidate.period, task.week_parity))
        self.room_busy.remove((candidate.room_id, candidate.day, candidate.period, task.week_parity))
        self.class_day_load[(task.class_group_id, candidate.day)] -= 1
        self.teacher_load[candidate.teacher_id] -= 1
        self.teacher_day_periods[(candidate.teacher_id, candidate.day)].discard(candidate.period)
        self.room_load[candidate.room_id] -= 1

        if not any(
            entry.class_group_id == task.class_group_id
            and entry.subject_id == task.subject_id
            and entry.day_of_week == candidate.day
            for entry in self.entries
        ):
            self.class_subject_days[(task.class_group_id, task.subject_id)].discard(candidate.day)

    def _result(self, generated_count):
        return {
            "detail": f"Расписание сгенерировано: {generated_count} уроков.",
            "academic_year_id": self.academic_year.id,
            "generated_count": generated_count,
            "unscheduled_count": len(self.unscheduled),
            "unscheduled": self.unscheduled[:20],
        }


def generate_schedule(academic_year_id: int):
    return ScheduleGenerator(academic_year_id).run()
