from django.urls import path, include
from rest_framework import routers
from api import views

# Router para la API REST
router = routers.DefaultRouter()
router.register(r'teachers', views.TeacherViewSet)
router.register(r'courses', views.CourseViewSet)
router.register(r'students', views.StudentViewSet)

urlpatterns = [
    # Vistas del Frontend (HTML)
    path('', views.index_view, name='home'),
    path('cursos/', views.courses_view, name='courses'),
    path('estudiantes/', views.students_view, name='students'),

    # Rutas de la API REST (Django REST Framework)
    path('api/', include(router.urls)),
]
