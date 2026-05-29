from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class School(models.Model):
    name = models.CharField(max_length=255)
    week_days_count = models.IntegerField(
        validators=[MinValueValidator(5), MaxValueValidator(6)]
    )
    shift_count = models.IntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["name"]
        verbose_name = "Школа"
        verbose_name_plural = "Школы"

    def __str__(self):
        return self.name


class BellSchedule(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="bell_schedules",
        verbose_name="Школа"
    )
    shift_number = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Номер смены"
    )
    period_number = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Номер урока"
    )
    start_time = models.TimeField(verbose_name="Начало")
    end_time = models.TimeField(verbose_name="Конец")
    break_after_minutes = models.IntegerField(
        default=0, validators=[MinValueValidator(0)],
        verbose_name="Перемена после (мин)"
    )

    class Meta:
        verbose_name = "Звонок"
        verbose_name_plural = "Звонки"
        ordering = ["shift_number", "period_number"]

    def __str__(self):
        return f"{self.school} | Смена {self.shift_number} | Урок {self.period_number}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("Время начала должно быть меньше времени конца.")


class AcademicYear(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="academic_years",
        verbose_name="Школа"
    )
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата конца")
    total_weeks = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Всего недель"
    )

    class Meta:
        verbose_name = "Учебный год"
        verbose_name_plural = "Учебные годы"
        ordering = ["school", "start_date"]

    def __str__(self):
        return f"{self.school} | {self.start_date.year}–{self.end_date.year}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Дата начала должна быть раньше даты конца.")


class VacationType(models.Model):
    title = models.CharField(max_length=255, unique=True, verbose_name="Название")

    class Meta:
        ordering = ["title"]
        verbose_name = "Тип каникул"
        verbose_name_plural = "Типы каникул"

    def __str__(self):
        return self.title


class VacationPeriod(models.Model):
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="vacation_periods",
        verbose_name="Учебный год"
    )
    start_date = models.DateField(verbose_name="Дата начала")
    end_date = models.DateField(verbose_name="Дата конца")
    vacation_type = models.ForeignKey(
        VacationType, on_delete=models.CASCADE, verbose_name="Тип каникул"
    )
    is_extra = models.BooleanField(default=False, verbose_name="Дополнительные")

    class Meta:
        ordering = ["academic_year", "start_date"]
        verbose_name = "Каникулы"
        verbose_name_plural = "Каникулы"

    def __str__(self):
        return f"{self.vacation_type} | {self.start_date} – {self.end_date}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Дата начала должна быть раньше даты конца.")


class Room(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="rooms",
        verbose_name="Школа"
    )
    number = models.CharField(max_length=50, verbose_name="Номер/название")
    type = models.CharField(max_length=100, blank=True, null=True, verbose_name="Тип")
    is_specialized = models.BooleanField(default=False, verbose_name="Специализированный")

    class Meta:
        ordering = ["school", "number"]
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"

    def __str__(self):
        return f"{self.school} | {self.number}"


class RoomUnavailability(models.Model):
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="unavailabilities",
        verbose_name="Кабинет"
    )
    date_from = models.DateField(verbose_name="С")
    date_to = models.DateField(verbose_name="По")
    reason = models.CharField(max_length=255, blank=True, null=True, verbose_name="Причина")

    class Meta:
        ordering = ["room", "date_from"]
        verbose_name = "Недоступность кабинета"
        verbose_name_plural = "Недоступность кабинетов"

    def __str__(self):
        return f"{self.room} | {self.date_from} – {self.date_to}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("Дата начала не может быть позже даты конца.")


class Teacher(models.Model):
    full_name = models.CharField(max_length=255, verbose_name="ФИО")
    category = models.CharField(max_length=100, blank=True, null=True, verbose_name="Категория")

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Учитель"
        verbose_name_plural = "Учителя"

    def __str__(self):
        return self.full_name


class TeacherUnavailability(models.Model):
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="unavailabilities",
        verbose_name="Учитель"
    )
    day_of_week = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        verbose_name="День недели (1=Пн)"
    )
    period_number = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Номер урока"
    )
    date_from = models.DateField(verbose_name="С")
    date_to = models.DateField(verbose_name="По")
    unavailability_type = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Тип"
    )
    reason = models.CharField(max_length=255, blank=True, null=True, verbose_name="Причина")

    class Meta:
        ordering = ["teacher", "date_from"]
        verbose_name = "Недоступность учителя"
        verbose_name_plural = "Недоступность учителей"

    def __str__(self):
        return f"{self.teacher} | {self.date_from} – {self.date_to}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("Дата начала не может быть позже даты конца.")


class TeacherSchool(models.Model):
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="school_assignments",
        verbose_name="Учитель"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="teacher_assignments",
        verbose_name="Школа"
    )
    weekly_hours_norm = models.FloatField(
        default=0, validators=[MinValueValidator(0)],
        verbose_name="Норма часов/неделю"
    )
    weekly_hours_max = models.FloatField(
        default=0, validators=[MinValueValidator(0)],
        verbose_name="Макс. часов/неделю"
    )

    class Meta:
        ordering = ["school", "teacher"]
        verbose_name = "Учитель в школе"
        verbose_name_plural = "Учителя в школах"
        unique_together = [("teacher", "school")]

    def __str__(self):
        return f"{self.teacher} → {self.school}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if (self.weekly_hours_max is not None and
                self.weekly_hours_norm is not None and
                self.weekly_hours_max < self.weekly_hours_norm):
            raise ValidationError("Макс. часы не могут быть меньше нормы.")


class ClassSpecialisation(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название")

    class Meta:
        ordering = ["name"]
        verbose_name = "Специализация класса"
        verbose_name_plural = "Специализации классов"

    def __str__(self):
        return self.name


class ClassGroup(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="class_groups",
        verbose_name="Школа"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="class_groups",
        verbose_name="Учебный год"
    )
    name = models.CharField(max_length=50, verbose_name="Название (напр. 9А)")
    grade_number = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(11)],
        verbose_name="Номер класса"
    )
    education_level = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Уровень образования"
    )
    shift_number = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Смена"
    )
    class_specialisation = models.ForeignKey(
        ClassSpecialisation, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Специализация"
    )

    class Meta:
        ordering = ["school", "academic_year", "grade_number", "name"]
        verbose_name = "Класс"
        verbose_name_plural = "Классы"

    def __str__(self):
        return f"{self.school} | {self.name} ({self.academic_year})"


class ClassSubgroup(models.Model):
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="subgroups",
        verbose_name="Класс"
    )
    name = models.CharField(max_length=50, verbose_name="Название")
    size = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Кол-во учеников"
    )

    class Meta:
        ordering = ["class_group", "name"]
        verbose_name = "Подгруппа"
        verbose_name_plural = "Подгруппы"

    def __str__(self):
        return f"{self.class_group} | {self.name}"


class DifficultyLevel(models.Model):
    rank = models.IntegerField(
        primary_key=True, validators=[MinValueValidator(1)],
        verbose_name="Ранг"
    )
    tabel = models.CharField(max_length=100, blank=True, null=True, verbose_name="Таблица")
    description = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Описание"
    )

    class Meta:
        verbose_name = "Уровень сложности"
        verbose_name_plural = "Уровни сложности"
        ordering = ["rank"]

    def __str__(self):
        return f"Ранг {self.rank}"


class Subject(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    fgos_area = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="Область ФГОС"
    )
    difficulty_rank = models.ForeignKey(
        DifficultyLevel, on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="difficulty_rank",
        verbose_name="Уровень сложности"
    )
    is_elective = models.BooleanField(default=False, verbose_name="Элективный")

    class Meta:
        ordering = ["name"]
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"

    def __str__(self):
        return self.name


class SubjectRoomRequirement(models.Model):
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="room_requirements",
        verbose_name="Предмет"
    )
    required_room_type = models.CharField(
        max_length=100, verbose_name="Требуемый тип кабинета"
    )

    class Meta:
        ordering = ["subject", "required_room_type"]
        verbose_name = "Требование к кабинету"
        verbose_name_plural = "Требования к кабинетам"

    def __str__(self):
        return f"{self.subject} → {self.required_room_type}"


class CurriculumPlan(models.Model):
    SEMESTER_CHOICES = [
        ("autumn", "Осень"),
        ("spring", "Весна"),
        ("full_year", "Весь год"),
    ]

    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="curriculum_plans",
        verbose_name="Класс"
    )

    subgroup = models.ForeignKey(ClassSubgroup, on_delete=models.CASCADE, null=True, blank=True,
                                 related_name="curriculum_plans", verbose_name="Подгруппа")

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="curriculum_plans",
        verbose_name="Предмет"
    )
    hours_per_week = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Часов в неделю"
    )
    is_mandatory = models.BooleanField(default=True, verbose_name="Обязательный")
    semester = models.CharField(
        max_length=10, choices=SEMESTER_CHOICES, verbose_name="Семестр"
    )

    class Meta:
        ordering = ["class_group", "subject", "semester"]
        verbose_name = "Учебный план"
        verbose_name_plural = "Учебные планы"
        unique_together = [("class_group", "subgroup", "subject", "semester")]

    def __str__(self):
        return f"{self.class_group} | {self.subject} | {self.get_semester_display()}"


class TeacherSubject(models.Model):
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="subjects",
        verbose_name="Учитель"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="teachers",
        verbose_name="Предмет"
    )
    is_primary = models.BooleanField(default=False, verbose_name="Основной предмет")

    class Meta:
        ordering = ["teacher", "subject"]
        verbose_name = "Предмет учителя"
        verbose_name_plural = "Предметы учителей"
        unique_together = [("teacher", "subject")]

    def __str__(self):
        return f"{self.teacher} → {self.subject}"


class SanpinLimit(models.Model):
    grade_from = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(11)],
        verbose_name="Класс от"
    )
    grade_to = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(11)],
        verbose_name="Класс до"
    )
    max_periods_5day = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Макс. уроков (5-дн.)"
    )
    max_periods_6day = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Макс. уроков (6-дн.)"
    )
    lesson_duration_max = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Макс. длит. урока (мин)"
    )

    class Meta:
        ordering = ["grade_from"]
        verbose_name = "Ограничение СанПиН"
        verbose_name_plural = "Ограничения СанПиН"

    def __str__(self):
        return f"Классы {self.grade_from}–{self.grade_to}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.grade_from and self.grade_to and self.grade_from > self.grade_to:
            raise ValidationError("grade_from не может быть больше grade_to.")


class ScheduleEntry(models.Model):
    WEEK_PARITY_CHOICES = [
        (0, "Обе недели"),
        (1, "Нечётная"),
        (2, "Чётная"),
    ]

    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="schedule_entries",
        verbose_name="Класс"
    )
    subgroup = models.ForeignKey(
        ClassSubgroup, on_delete=models.CASCADE,
        null=True, blank=True, related_name="schedule_entries",
        verbose_name="Подгруппа"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="schedule_entries",
        verbose_name="Предмет"
    )
    teacher = models.ForeignKey(
        Teacher, on_delete=models.CASCADE, related_name="schedule_entries",
        verbose_name="Учитель"
    )
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="schedule_entries",
        verbose_name="Кабинет"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="schedule_entries",
        verbose_name="Учебный год"
    )
    day_of_week = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        verbose_name="День недели (1=Пн)"
    )
    period_number = models.IntegerField(
        validators=[MinValueValidator(1)], verbose_name="Номер урока"
    )
    week_parity = models.IntegerField(
        choices=WEEK_PARITY_CHOICES, default=0, verbose_name="Чётность недели"
    )
    valid_from = models.DateField(auto_now_add=True, verbose_name="Действует с")
    valid_to = models.DateField(null=True, blank=True, verbose_name="Действует по")
    is_substitution = models.BooleanField(default=False, verbose_name="Замена")

    class Meta:
        ordering = ["academic_year", "class_group", "day_of_week", "period_number"]
        verbose_name = "Урок в расписании"
        verbose_name_plural = "Расписание"
        unique_together = [
            ("class_group", "subgroup", "day_of_week", "period_number",
             "week_parity", "academic_year")
        ]

    def __str__(self):
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day = day_names[self.day_of_week - 1] if 1 <= self.day_of_week <= 7 else "?"
        return (
            f"{self.class_group} | {day} | Урок {self.period_number} | "
            f"{self.subject} | {self.teacher}"
        )

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValidationError("valid_from не может быть позже valid_to.")
