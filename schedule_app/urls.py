from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    RegisterView, MeView,
    SchoolViewSet, BellScheduleViewSet, AcademicYearViewSet,
    VacationTypeViewSet, VacationPeriodViewSet, RoomViewSet,
    TeacherViewSet, ClassGroupViewSet, SubjectViewSet,
    ScheduleEntryViewSet, GenerateScheduleView,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet, basename="school")
router.register("bell-schedules", BellScheduleViewSet, basename="bell-schedule")
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("vacation-types", VacationTypeViewSet, basename="vacation-type")
router.register("vacation-periods", VacationPeriodViewSet, basename="vacation-period")
router.register("rooms", RoomViewSet, basename="room")
router.register("teachers", TeacherViewSet, basename="teacher")
router.register("class-groups", ClassGroupViewSet, basename="class-group")
router.register("subjects", SubjectViewSet, basename="subject")
router.register("schedule", ScheduleEntryViewSet, basename="schedule")

urlpatterns = [
    # Auth
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", TokenObtainPairView.as_view(), name="auth-login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("auth/me/", MeView.as_view(), name="auth-me"),

    # Generate
    path("schedule/generate/", GenerateScheduleView.as_view(), name="schedule-generate"),

    # REST resources
    path("", include(router.urls)),
]
