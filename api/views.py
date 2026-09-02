from django.shortcuts import render
from rest_framework import viewsets
from .serializer import TeacherSerializer, CourseSerializer, StudentSerializer
from .models import Teacher, Course, Student


# ==========================================
# VISTAS DEL FRONTEND (HTML con render)
# ==========================================

def index_view(request):
    """Página principal de bienvenida"""
    return render(request, 'index.html')


def courses_view(request):
    """Página que lista todos los cursos y sus profesores"""
    courses = Course.objects.all()
    return render(request, 'courses.html', {'courses': courses})


def students_view(request):
    """Página que lista todos los estudiantes"""
    students = Student.objects.all()
    return render(request, 'students.html', {'students': students})


# ==========================================
# VISTAS DE LA API (Django REST Framework)
# ==========================================

class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
