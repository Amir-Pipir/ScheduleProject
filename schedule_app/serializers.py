from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    School, BellSchedule, AcademicYear, VacationType, VacationPeriod,
    Room, Teacher, ClassGroup, ClassSubgroup, Subject,
    CurriculumPlan, TeacherSubject, ScheduleEntry,
)


# ── Auth ───────────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label="Подтверждение пароля")

    class Meta:
        model = User
        fields = ["username", "email", "password", "password2"]

    def validate(self, data):
        if data["password"] != data["password2"]:
            raise serializers.ValidationError({"password2": "Пароли не совпадают."})
        return data

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create_user(**validated_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff"]


# ── Schedule (read) ────────────────────────────────────────────────────────────

class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = "__all__"


class BellScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BellSchedule
        fields = "__all__"


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = "__all__"


class VacationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = VacationType
        fields = "__all__"


class VacationPeriodSerializer(serializers.ModelSerializer):
    vacation_type_display = serializers.StringRelatedField(source="vacation_type")

    class Meta:
        model = VacationPeriod
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = "__all__"


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = "__all__"


class ClassSubgroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassSubgroup
        fields = "__all__"


class ClassGroupSerializer(serializers.ModelSerializer):
    subgroups = ClassSubgroupSerializer(many=True, read_only=True)

    class Meta:
        model = ClassGroup
        fields = "__all__"


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = "__all__"


class CurriculumPlanSerializer(serializers.ModelSerializer):
    subject_name = serializers.StringRelatedField(source="subject")
    class_group_name = serializers.StringRelatedField(source="class_group")

    class Meta:
        model = CurriculumPlan
        fields = "__all__"


# ── Schedule entry (nested read) ───────────────────────────────────────────────

class ScheduleEntryReadSerializer(serializers.ModelSerializer):
    """Детальный сериализатор для фронта — подтягивает связанные объекты."""
    class_group = ClassGroupSerializer(read_only=True)
    subgroup = ClassSubgroupSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    room = RoomSerializer(read_only=True)
    week_parity_display = serializers.CharField(
        source="get_week_parity_display", read_only=True
    )
    day_of_week_display = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleEntry
        fields = "__all__"

    @extend_schema_field(serializers.CharField())
    def get_day_of_week_display(self, obj):
        days = {1: "Понедельник", 2: "Вторник", 3: "Среда",
                4: "Четверг", 5: "Пятница", 6: "Суббота", 7: "Воскресенье"}
        return days.get(obj.day_of_week, "")


class ScheduleEntryWriteSerializer(serializers.ModelSerializer):
    """Сериализатор для создания/обновления записей расписания (только для админов)."""

    class Meta:
        model = ScheduleEntry
        fields = "__all__"

    def validate(self, data):
        # Проверка пересечений учителя
        qs = ScheduleEntry.objects.filter(
            teacher=data.get("teacher"),
            day_of_week=data.get("day_of_week"),
            period_number=data.get("period_number"),
            academic_year=data.get("academic_year"),
        )
        # При обновлении исключаем текущую запись
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        # week_parity: если 0 — пересекается со всеми
        week_parity = data.get("week_parity", 0)
        if week_parity == 0:
            pass  # может пересечься с любой записью
        else:
            qs = qs.filter(week_parity__in=[0, week_parity])

        if qs.exists():
            raise serializers.ValidationError(
                "Учитель уже занят в это время."
            )

        # Проверка пересечений кабинета
        room_qs = ScheduleEntry.objects.filter(
            room=data.get("room"),
            day_of_week=data.get("day_of_week"),
            period_number=data.get("period_number"),
            academic_year=data.get("academic_year"),
        )
        if self.instance:
            room_qs = room_qs.exclude(pk=self.instance.pk)
        if week_parity != 0:
            room_qs = room_qs.filter(week_parity__in=[0, week_parity])

        if room_qs.exists():
            raise serializers.ValidationError(
                "Кабинет уже занят в это время."
            )

        return data
