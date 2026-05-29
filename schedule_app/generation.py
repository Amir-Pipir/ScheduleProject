import logging
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

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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


class ScheduleGenerator:
    def __init__(self, academic_year_id: int):
        logger.info(f"Инициализация генератора для учебного года {academic_year_id}")
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

    def run(self):
        logger.info("=== НАЧАЛО ГЕНЕРАЦИИ ===")
        try:
            self._load_context()
            tasks = self._build_tasks()
            if not tasks:
                logger.warning("Нет задач для генерации (пустой учебный план?)")
                return self._result(0)

            logger.info(f"Создано {len(tasks)} задач (уроков)")
            tasks.sort(key=self._task_sort_key)
            solved = self._solve_with_fallback(tasks)

            if not solved:
                logger.warning("Не удалось разместить все уроки. Часть отложена.")
            else:
                logger.info(f"Успешно размещено {len(self.entries)} уроков.")

            with transaction.atomic():
                ScheduleEntry.objects.filter(
                    academic_year=self.academic_year,
                    class_group__school=self.school,
                    is_substitution=False,
                ).delete()
                ScheduleEntry.objects.bulk_create(self.entries)
                logger.info(f"Сохранено {len(self.entries)} записей в БД")

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
        logger.info("Загрузка классов...")
        self.class_groups = list(
            ClassGroup.objects.filter(academic_year=self.academic_year, school=self.school)
            .select_related("school", "academic_year")
            .order_by("grade_number", "name")
        )
        logger.info(f"Найдено классов: {len(self.class_groups)}")

        logger.info("Загрузка звонков...")
        bells = BellSchedule.objects.filter(school=self.school).order_by("shift_number", "period_number")
        for bell in bells:
            self.bells_by_shift[bell.shift_number].append(bell.period_number)
            self.max_period_by_shift[bell.shift_number] = max(
                self.max_period_by_shift.get(bell.shift_number, 0),
                bell.period_number,
            )
        logger.info(f"Звонки по сменам: {dict(self.bells_by_shift)}")

        logger.info("Загрузка СанПиН...")
        for limit in SanpinLimit.objects.all():
            max_periods = (
                limit.max_periods_5day
                if self.school.week_days_count == 5
                else limit.max_periods_6day
            )
            for grade in range(limit.grade_from, limit.grade_to + 1):
                self.sanpin_by_grade[grade] = max_periods
        logger.info(f"СанПиН по классам: {self.sanpin_by_grade}")

        logger.info("Загрузка учителей и их предметов...")
        teacher_school = TeacherSchool.objects.filter(school=self.school).select_related("teacher")
        school_teacher_ids = {item.teacher_id for item in teacher_school}
        self.teacher_max_hours = {
            item.teacher_id: int(item.weekly_hours_max or item.weekly_hours_norm or 10**6)
            for item in teacher_school
        }
        logger.info(f"Учителей в школе: {len(school_teacher_ids)}")

        for item in TeacherSubject.objects.filter(teacher_id__in=school_teacher_ids).select_related("teacher", "subject"):
            self.teacher_ids_by_subject[item.subject_id].append(item.teacher_id)
        logger.info(f"Предметов с учителями: {len(self.teacher_ids_by_subject)}")

        # Для каждого предмета покажем наличие учителей
        for subj_id, teachers in self.teacher_ids_by_subject.items():
            logger.debug(f"Предмет {subj_id}: {len(teachers)} учителей")

        logger.info("Загрузка кабинетов...")
        self.rooms = list(Room.objects.filter(school=self.school).order_by("-is_specialized", "number"))
        logger.info(f"Найдено кабинетов: {len(self.rooms)}")

        room_requirements = defaultdict(list)
        for requirement in SubjectRoomRequirement.objects.select_related("subject"):
            room_requirements[requirement.subject_id].append(requirement.required_room_type)

        all_room_ids = [room.id for room in self.rooms]
        for subject_id, required_types in room_requirements.items():
            self.subjects_with_room_requirements.add(subject_id)
            suitable_rooms = [room.id for room in self.rooms if room.type in required_types]
            if suitable_rooms:
                self.room_ids_by_subject[subject_id] = suitable_rooms
            else:
                logger.warning(f"Для предмета {subject_id} требуются типы {required_types}, но нет подходящих кабинетов!")
        self.default_room_ids = all_room_ids
        logger.info("Требования к кабинетам загружены.")

        logger.info("Загрузка периодов недоступности...")
        self._load_unavailability()
        logger.info(f"Недоступность учителей: {len(self.teacher_unavailable)} записей")
        logger.info(f"Недоступность кабинетов: {len(self.room_unavailable)} записей")

    def _load_unavailability(self):
        year_start = self.academic_year.start_date
        year_end = self.academic_year.end_date

        for item in TeacherUnavailability.objects.filter(date_from__lte=year_end, date_to__gte=year_start):
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
        plans = CurriculumPlan.objects.filter(class_group__in=self.class_groups).select_related(
            "class_group", "subject", "subject__difficulty_rank"
        )
        logger.info(f"Всего записей в CurriculumPlan: {plans.count()}")

        # Фильтрация: для каждой пары (класс, предмет) берём максимальные часы
        chosen = {}
        for plan in plans:
            key = (plan.class_group_id, plan.subject_id)
            current = chosen.get(key)
            if current is None:
                chosen[key] = plan
            elif plan.semester == "full_year":
                chosen[key] = plan
            elif current.semester != "full_year" and plan.hours_per_week > current.hours_per_week:
                chosen[key] = plan
        logger.info(f"Уникальных пар (класс, предмет) после фильтрации: {len(chosen)}")

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
                        subgroup_id=None,  # если есть подгруппы – нужно отдельно обработать
                    )
                )
        logger.info(f"Сформировано задач (уроков): {len(tasks)}")
        return tasks

    def _task_sort_key(self, task):
        # Чем сложнее предмет (мало учителей, мало кабинетов, мало слотов) – тем выше приоритет
        teacher_count = len(self.teacher_ids_by_subject.get(task.subject_id, []))
        room_count = len(self._room_ids_for_subject(task.subject_id))
        slot_count = len(self._slots_for_class(task))
        # Приоритет: сначала те, у кого меньше вариантов
        return (
            teacher_count or 10**6,
            room_count or 10**6,
            slot_count or 10**6,
            -task.grade_number,  # старшие классы выше
            task.difficulty_rank,
        )

    def _solve_with_fallback(self, tasks):
        """Рекурсивное назначение с откатом, но если не получается – задача откладывается."""
        self.entries = []
        self.unscheduled = []
        # Используем стек для backtracking
        stack = [(0, [])]  # (index, предыдущие назначения)
        # Чтобы не углубляться слишком сильно, ограничим максимальное число попыток
        max_attempts = 20000
        attempts = 0

        while stack and attempts < max_attempts:
            idx, prev_entries = stack.pop()
            if idx >= len(tasks):
                # Все задачи обработаны
                self.entries = prev_entries
                logger.info(f"Успешно размещено {len(prev_entries)} уроков из {len(tasks)}")
                return True

            task = tasks[idx]
            # Пытаемся найти кандидатов
            candidates = self._candidates_for(task, prev_entries)
            if not candidates:
                # Нет кандидатов – откладываем задачу
                self.unscheduled.append({
                    "class": task.class_group_name,
                    "subject": task.subject_name,
                    "reason": "no_candidates",
                })
                # Переходим к следующей задаче, не добавляя эту
                stack.append((idx + 1, prev_entries))
                continue

            # Для каждого кандидата (сортируем по score)
            for cand in candidates[:20]:  # рассматриваем до 20 вариантов
                # Создаём новое состояние (копируем предыдущие записи)
                new_entries = prev_entries + [self._make_entry(task, cand)]
                # Временно применяем изменения (для проверки занятости)
                if self._try_place(task, cand, new_entries):
                    stack.append((idx + 1, new_entries))
                    attempts += 1
                    break
            else:
                # Не удалось применить ни одного кандидата – откладываем задачу
                self.unscheduled.append({
                    "class": task.class_group_name,
                    "subject": task.subject_name,
                    "reason": "conflict_all_candidates",
                })
                stack.append((idx + 1, prev_entries))

        if attempts >= max_attempts:
            logger.error("Превышено максимальное количество попыток backtracking")
        return False

    def _candidates_for(self, task, existing_entries):
        """Генерирует список кандидатов, игнорируя уже занятые слоты в existing_entries."""
        candidates = []
        teacher_ids = self.teacher_ids_by_subject.get(task.subject_id, [])
        room_ids = self._room_ids_for_subject(task.subject_id)

        if not teacher_ids:
            logger.warning(f"Нет учителей для предмета {task.subject_name} (id={task.subject_id})")
            return []
        if not room_ids:
            logger.warning(f"Нет кабинетов для предмета {task.subject_name} (id={task.subject_id})")
            return []

        # Вычисляем занятость на основе existing_entries
        class_busy = set()
        teacher_busy = set()
        room_busy = set()
        class_day_load = defaultdict(int)
        teacher_load = defaultdict(int)
        teacher_day_periods = defaultdict(set)
        class_subject_days = defaultdict(set)

        for entry in existing_entries:
            class_busy.add((entry.class_group_id, entry.subgroup_id, entry.day_of_week, entry.period_number, entry.week_parity))
            teacher_busy.add((entry.teacher_id, entry.day_of_week, entry.period_number, entry.week_parity))
            room_busy.add((entry.room_id, entry.day_of_week, entry.period_number, entry.week_parity))
            class_day_load[(entry.class_group_id, entry.day_of_week)] += 1
            teacher_load[entry.teacher_id] += 1
            teacher_day_periods[(entry.teacher_id, entry.day_of_week)].add(entry.period_number)
            class_subject_days[(entry.class_group_id, entry.subject_id)].add(entry.day_of_week)

        max_periods = self._max_periods_for_grade(task.grade_number)
        for day, period in self._slots_for_class(task):
            if class_day_load[(task.class_group_id, day)] >= max_periods:
                continue
            if (task.class_group_id, task.subgroup_id, day, period, task.week_parity) in class_busy:
                continue

            for teacher_id in teacher_ids:
                if (teacher_id, day, period, task.week_parity) in teacher_busy:
                    continue
                if (teacher_id, day, period) in self.teacher_unavailable:
                    continue
                if teacher_load[teacher_id] >= self.teacher_max_hours.get(teacher_id, 10**6):
                    continue

                for room_id in room_ids:
                    if (room_id, day, period, task.week_parity) in room_busy:
                        continue
                    if (room_id, day, period) in self.room_unavailable:
                        continue
                    score = self._score_task(task, teacher_id, room_id, day, period,
                                             class_day_load, teacher_day_periods, class_subject_days, teacher_load)
                    candidates.append(Candidate(day, period, teacher_id, room_id, score))

        candidates.sort(key=lambda c: c.score)
        return candidates[:100]  # увеличили лимит

    def _score_task(self, task, teacher_id, room_id, day, period,
                    class_day_load, teacher_day_periods, class_subject_days, teacher_load):
        score = 0
        if period > 4 and task.difficulty_rank <= 3:
            score += 60
        if period > class_day_load[(task.class_group_id, day)] + 1:
            score += 80
        if day in class_subject_days[(task.class_group_id, task.subject_id)]:
            score += 45
        score += class_day_load[(task.class_group_id, day)] * 8
        teacher_periods = teacher_day_periods[(teacher_id, day)]
        if teacher_periods and period not in {min(teacher_periods) - 1, max(teacher_periods) + 1}:
            score += 35
        score += teacher_load[teacher_id] * 3
        score += self.room_load.get(room_id, 0)  # глобальная нагрузка
        return score

    def _make_entry(self, task, candidate):
        return ScheduleEntry(
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

    def _try_place(self, task, candidate, new_entries):
        """Проверяет, что назначение не конфликтует с existing_entries (не нужно, т.к. уже проверено в _candidates_for)"""
        # Здесь просто возвращаем True, т.к. кандидаты уже отфильтрованы
        return True

    def _slots_for_class(self, task):
        periods = self.bells_by_shift.get(task.shift_number)
        if not periods:
            periods = list(range(1, self._max_periods_for_grade(task.grade_number) + 1))
        max_periods = self._max_periods_for_grade(task.grade_number)
        return [(day, period) for day in self.days for period in periods if period <= max_periods]

    def _room_ids_for_subject(self, subject_id):
        if subject_id in self.subjects_with_room_requirements:
            return self.room_ids_by_subject.get(subject_id, [])
        # Если нет требований – любой кабинет
        return self.default_room_ids

    def _max_periods_for_grade(self, grade_number):
        default = max(self.max_period_by_shift.values()) if self.max_period_by_shift else 8
        return self.sanpin_by_grade.get(grade_number, default)

    def _result(self, generated_count):
        return {
            "detail": f"Расписание сгенерировано: {generated_count} уроков.",
            "academic_year_id": self.academic_year.id,
            "generated_count": generated_count,
            "unscheduled_count": len(self.unscheduled),
            "unscheduled": self.unscheduled[:20],
        }


def generate_schedule(academic_year_id: int):
    print("начинаю генерацию...")
    return ScheduleGenerator(academic_year_id).run()