import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drf.settings')
django.setup()

from api.models import Teacher, Course, Student, StudentCourse

def populate():
    print("Cargando datos iniciales...")

    # 1. Crear 6 Profesores
    teachers_data = [
        {"first_name": "Carlos", "last_name": "Mendoza"},
        {"first_name": "Laura", "last_name": "Gómez"},
        {"first_name": "Andrés", "last_name": "Ríos"},
        {"first_name": "Patricia", "last_name": "Fernández"},
        {"first_name": "Gabriel", "last_name": "Silva"},
        {"first_name": "Elena", "last_name": "Torres"},
    ]

    teachers = []
    for t_data in teachers_data:
        teacher, created = Teacher.objects.get_or_create(
            first_name=t_data["first_name"],
            last_name=t_data["last_name"]
        )
        teachers.append(teacher)
        print(f"Profesor: {teacher} ({'creado' if created else 'ya existía'})")

    # 2. Crear 6 Cursos asociados a cada profesor
    courses_data = [
        {"name": "Programación en Python", "teacher": teachers[0]},
        {"name": "Bases de Datos SQL", "teacher": teachers[1]},
        {"name": "Desarrollo Web con Django", "teacher": teachers[2]},
        {"name": "Estructuras de Datos y Algoritmos", "teacher": teachers[3]},
        {"name": "Inteligencia Artificial y Machine Learning", "teacher": teachers[4]},
        {"name": "Seguridad Informática y Redes", "teacher": teachers[5]},
    ]

    courses = []
    for c_data in courses_data:
        course, created = Course.objects.get_or_create(
            name=c_data["name"],
            teacher=c_data["teacher"]
        )
        courses.append(course)
        print(f"Curso: {course.name} - Prof. {course.teacher} ({'creado' if created else 'ya existía'})")

    # 3. Crear 6 Estudiantes
    students_data = [
        {"first_name": "Matías", "last_name": "Alarcón"},
        {"first_name": "Sofía", "last_name": "Valenzuela"},
        {"first_name": "Diego", "last_name": "Herrera"},
        {"first_name": "Camila", "last_name": "Castillo"},
        {"first_name": "Joaquín", "last_name": "Morales"},
        {"first_name": "Valentina", "last_name": "Paredes"},
    ]

    students = []
    for s_data in students_data:
        student, created = Student.objects.get_or_create(
            first_name=s_data["first_name"],
            last_name=s_data["last_name"]
        )
        students.append(student)
        print(f"Estudiante: {student} ({'creado' if created else 'ya existía'})")

    # 4. Inscripciones de ejemplo (StudentCourse)
    for i in range(6):
        StudentCourse.objects.get_or_create(
            student=students[i],
            course=courses[i % len(courses)]
        )

    print("\n¡Carga de datos completada exitosamente!")

if __name__ == '__main__':
    populate()
