from django.contrib import admin
from .models import (
    School, BellSchedule, AcademicYear, VacationType, VacationPeriod,
    Room, RoomUnavailability, Teacher, TeacherUnavailability, TeacherSchool,
    ClassSpecialisation, ClassGroup, ClassSubgroup, DifficultyLevel,
    Subject, SubjectRoomRequirement, CurriculumPlan, TeacherSubject,
    SanpinLimit, ScheduleEntry,
)


# ── Inlines ────────────────────────────────────────────────────────────────────

class BellScheduleInline(admin.TabularInline):
    model = BellSchedule
    extra = 1
    ordering = ["shift_number", "period_number"]


class AcademicYearInline(admin.TabularInline):
    model = AcademicYear
    extra = 0


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0


class TeacherSchoolInline(admin.TabularInline):
    model = TeacherSchool
    extra = 0


class VacationPeriodInline(admin.TabularInline):
    model = VacationPeriod
    extra = 0


class ClassGroupInline(admin.TabularInline):
    model = ClassGroup
    extra = 0
    show_change_link = True


class ClassSubgroupInline(admin.TabularInline):
    model = ClassSubgroup
    extra = 0


class SubjectRoomRequirementInline(admin.TabularInline):
    model = SubjectRoomRequirement
    extra = 0


class TeacherSubjectInline(admin.TabularInline):
    model = TeacherSubject
    extra = 0


class TeacherUnavailabilityInline(admin.TabularInline):
    model = TeacherUnavailability
    extra = 0


class RoomUnavailabilityInline(admin.TabularInline):
    model = RoomUnavailability
    extra = 0


class CurriculumPlanInline(admin.TabularInline):
    model = CurriculumPlan
    extra = 0


# ── Admin classes ──────────────────────────────────────────────────────────────

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ["name", "week_days_count", "shift_count"]
    search_fields = ["name"]
    inlines = [BellScheduleInline, AcademicYearInline, RoomInline]


@admin.register(BellSchedule)
class BellScheduleAdmin(admin.ModelAdmin):
    list_display = ["school", "shift_number", "period_number", "start_time", "end_time", "break_after_minutes"]
    list_filter = ["school", "shift_number"]
    ordering = ["school", "shift_number", "period_number"]


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["school", "start_date", "end_date", "total_weeks"]
    list_filter = ["school"]
    inlines = [VacationPeriodInline, ClassGroupInline]


@admin.register(VacationType)
class VacationTypeAdmin(admin.ModelAdmin):
    list_display = ["title"]
    search_fields = ["title"]


@admin.register(VacationPeriod)
class VacationPeriodAdmin(admin.ModelAdmin):
    list_display = ["academic_year", "vacation_type", "start_date", "end_date", "is_extra"]
    list_filter = ["vacation_type", "is_extra", "academic_year"]


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["school", "number", "type", "is_specialized"]
    list_filter = ["school", "is_specialized", "type"]
    search_fields = ["number"]
    inlines = [RoomUnavailabilityInline]


@admin.register(RoomUnavailability)
class RoomUnavailabilityAdmin(admin.ModelAdmin):
    list_display = ["room", "date_from", "date_to", "reason"]
    list_filter = ["room__school"]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ["full_name", "category"]
    search_fields = ["full_name"]
    list_filter = ["category"]
    inlines = [TeacherSubjectInline, TeacherSchoolInline, TeacherUnavailabilityInline]


@admin.register(TeacherUnavailability)
class TeacherUnavailabilityAdmin(admin.ModelAdmin):
    list_display = ["teacher", "day_of_week", "period_number", "date_from", "date_to", "unavailability_type"]
    list_filter = ["unavailability_type"]
    search_fields = ["teacher__full_name"]


@admin.register(TeacherSchool)
class TeacherSchoolAdmin(admin.ModelAdmin):
    list_display = ["teacher", "school", "weekly_hours_norm", "weekly_hours_max"]
    list_filter = ["school"]
    search_fields = ["teacher__full_name"]


@admin.register(ClassSpecialisation)
class ClassSpecialisationAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "grade_number", "school", "academic_year", "shift_number", "class_specialisation"]
    list_filter = ["school", "academic_year", "grade_number", "shift_number"]
    search_fields = ["name"]
    inlines = [ClassSubgroupInline, CurriculumPlanInline]


@admin.register(ClassSubgroup)
class ClassSubgroupAdmin(admin.ModelAdmin):
    list_display = ["name", "class_group", "size"]
    list_filter = ["class_group__school"]
    search_fields = ["name", "class_group__name"]


@admin.register(DifficultyLevel)
class DifficultyLevelAdmin(admin.ModelAdmin):
    list_display = ["rank", "tabel", "description"]
    ordering = ["rank"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "fgos_area", "difficulty_rank", "is_elective"]
    list_filter = ["is_elective", "difficulty_rank"]
    search_fields = ["name", "fgos_area"]
    inlines = [SubjectRoomRequirementInline]


@admin.register(SubjectRoomRequirement)
class SubjectRoomRequirementAdmin(admin.ModelAdmin):
    list_display = ["subject", "required_room_type"]
    list_filter = ["required_room_type"]


@admin.register(CurriculumPlan)
class CurriculumPlanAdmin(admin.ModelAdmin):
    list_display = ["class_group", "subject", "hours_per_week", "is_mandatory", "semester"]
    list_filter = ["semester", "is_mandatory", "class_group__school", "class_group__academic_year"]
    search_fields = ["class_group__name", "subject__name"]


@admin.register(TeacherSubject)
class TeacherSubjectAdmin(admin.ModelAdmin):
    list_display = ["teacher", "subject", "is_primary"]
    list_filter = ["is_primary"]
    search_fields = ["teacher__full_name", "subject__name"]


@admin.register(SanpinLimit)
class SanpinLimitAdmin(admin.ModelAdmin):
    list_display = ["grade_from", "grade_to", "max_periods_5day", "max_periods_6day", "lesson_duration_max"]
    ordering = ["grade_from"]


@admin.register(ScheduleEntry)
class ScheduleEntryAdmin(admin.ModelAdmin):
    list_display = [
        "class_group", "subgroup", "day_of_week", "period_number",
        "subject", "teacher", "room", "week_parity", "is_substitution"
    ]
    list_filter = [
        "class_group__school",
        "academic_year",
        "day_of_week",
        "week_parity",
        "is_substitution",
    ]
    search_fields = [
        "class_group__name",
        "teacher__full_name",
        "subject__name",
    ]
    autocomplete_fields = ["class_group", "subject", "teacher", "room"]
    list_select_related = ["class_group", "subject", "teacher", "room", "subgroup"]
