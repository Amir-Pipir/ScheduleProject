import threading

from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers as drf_serializers
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404

from .models import (
    School, BellSchedule, AcademicYear, VacationType, VacationPeriod,
    Room, Teacher, ClassGroup, ClassSubgroup, Subject, ScheduleEntry,
)
from .generation import generate_schedule
from .serializers import (
    RegisterSerializer, UserSerializer,
    SchoolSerializer, BellScheduleSerializer, AcademicYearSerializer,
    VacationTypeSerializer, VacationPeriodSerializer, RoomSerializer,
    TeacherSerializer, ClassGroupSerializer, ClassSubgroupSerializer,
    SubjectSerializer, ScheduleEntryReadSerializer, ScheduleEntryWriteSerializer,
)


# ── Auth ───────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — регистрация нового пользователя."""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer  # добавь эту строку

    @extend_schema(responses=UserSerializer)  # и этот декоратор
    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ── Read-only справочники (доступны всем авторизованным) ──────────────────────

class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


class BellScheduleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BellSchedule.objects.select_related("school").all()
    serializer_class = BellScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["school", "shift_number"]


class AcademicYearViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AcademicYear.objects.select_related("school").all()
    serializer_class = AcademicYearSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["school"]


class VacationTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VacationType.objects.all()
    serializer_class = VacationTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class VacationPeriodViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VacationPeriod.objects.select_related("academic_year", "vacation_type").all()
    serializer_class = VacationPeriodSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["academic_year", "vacation_type", "is_extra"]


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Room.objects.select_related("school").all()
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["school", "is_specialized", "type"]
    search_fields = ["number"]


class TeacherViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["full_name"]


class ClassGroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ClassGroup.objects.select_related(
        "school", "academic_year", "class_specialisation"
    ).prefetch_related("subgroups").all()
    serializer_class = ClassGroupSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["school", "academic_year", "grade_number", "shift_number"]
    search_fields = ["name"]


class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["name"]
    filterset_fields = ["is_elective"]


# ── ScheduleEntry — основной ресурс ───────────────────────────────────────────

class ScheduleEntryViewSet(viewsets.ModelViewSet):
    """
    Расписание.
    - GET (list/retrieve) — все авторизованные.
    - POST/PUT/PATCH/DELETE — только is_staff (администраторы).
    """
    queryset = ScheduleEntry.objects.select_related(
        "class_group", "subgroup", "subject", "teacher", "room", "academic_year"
    ).all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "academic_year",
        "class_group",
        "class_group__school",
        "subgroup",
        "teacher",
        "room",
        "day_of_week",
        "week_parity",
        "is_substitution",
        "subject",
    ]
    search_fields = ["class_group__name", "teacher__full_name", "subject__name"]
    ordering_fields = ["day_of_week", "period_number"]
    ordering = ["day_of_week", "period_number"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return ScheduleEntryReadSerializer
        return ScheduleEntryWriteSerializer

    @action(detail=False, methods=["get"], url_path="by-class/(?P<class_group_id>[^/.]+)")
    def by_class(self, request, class_group_id=None):
        """GET /api/schedule/by-class/{id}/?academic_year=X — расписание класса."""
        qs = self.get_queryset().filter(class_group_id=class_group_id)
        academic_year_id = request.query_params.get("academic_year")
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        serializer = ScheduleEntryReadSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-teacher/(?P<teacher_id>[^/.]+)")
    def by_teacher(self, request, teacher_id=None):
        """GET /api/schedule/by-teacher/{id}/?academic_year=X — расписание учителя."""
        qs = self.get_queryset().filter(teacher_id=teacher_id)
        academic_year_id = request.query_params.get("academic_year")
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        serializer = ScheduleEntryReadSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="by-room/(?P<room_id>[^/.]+)")
    def by_room(self, request, room_id=None):
        """GET /api/schedule/by-room/{id}/?academic_year=X — расписание кабинета."""
        qs = self.get_queryset().filter(room_id=room_id)
        academic_year_id = request.query_params.get("academic_year")
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        serializer = ScheduleEntryReadSerializer(qs, many=True)
        return Response(serializer.data)


# ── Generate (заглушка для алгоритма генерации) ───────────────────────────────

class GenerateScheduleView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=inline_serializer(
            name="GenerateScheduleRequest",
            fields={"academic_year_id": drf_serializers.IntegerField()}
        ),
        responses={202: inline_serializer(
            name="GenerateScheduleResponse",
            fields={"detail": drf_serializers.CharField()}
        )}
    )

    def post(self, request):
        academic_year_id = request.data.get("academic_year_id")
        if not academic_year_id:
            return Response(
                {"detail": "academic_year_id обязателен."},
                status=status.HTTP_400_BAD_REQUEST
            )

        get_object_or_404(AcademicYear, pk=academic_year_id)

        # Запускаем в фоновом потоке
        def run():
            try:
                generate_schedule(int(academic_year_id))
            except Exception as e:
                # Здесь можно записать ошибку в лог или в БД
                print(f"Ошибка генерации: {e}")

        thread = threading.Thread(target=run)
        thread.start()

        return Response(
            {"detail": f"Генерация расписания для учебного года {academic_year_id} запущена в фоновом режиме."},
            status=status.HTTP_202_ACCEPTED
        )
