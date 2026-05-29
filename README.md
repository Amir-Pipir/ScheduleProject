# 🏫 Schedule Project — Django Backend

## Структура проекта

```
schedule_project/
├── schedule_project/       # Конфиг Django
│   ├── settings.py
│   └── urls.py
├── schedule_app/           # Основное приложение
│   ├── models.py           # Все модели БД
│   ├── admin.py            # Настройка Django Admin
│   ├── serializers.py      # DRF сериализаторы
│   ├── views.py            # ViewSet'ы и APIView
│   └── urls.py             # Маршруты API
├── requirements.txt
└── README.md
```

---

## Быстрый старт

### 1. Установка зависимостей
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Настройка БД (PostgreSQL)
Отредактируй `settings.py` → `DATABASES`:
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "schedule_db",
        "USER": "твой_юзер",
        "PASSWORD": "твой_пароль",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

Создай базу:
```bash
psql -U postgres -c "CREATE DATABASE schedule_db;"
```

### 3. Миграции
```bash
python manage.py makemigrations schedule_app
python manage.py migrate
```

### 4. Суперпользователь (для Admin)
```bash
python manage.py createsuperuser
```

### 5. Запуск сервера
```bash
python manage.py runserver
```

---

## Доступ

| URL | Описание |
|---|---|
| `http://localhost:8000/admin/` | Django Admin (заполнение всех данных) |
| `http://localhost:8000/api/` | REST API |

---

## API Endpoints

### Аутентификация

| Метод | URL | Доступ | Описание |
|---|---|---|---|
| POST | `/api/auth/register/` | Все | Регистрация |
| POST | `/api/auth/login/` | Все | Получить JWT токен |
| POST | `/api/auth/refresh/` | Все | Обновить токен |
| GET  | `/api/auth/me/` | Auth | Текущий пользователь |

**Авторизация через заголовок:**
```
Authorization: Bearer <access_token>
```

**Пример регистрации:**
```json
POST /api/auth/register/
{
  "username": "ivanov",
  "email": "ivanov@school.ru",
  "password": "secret123",
  "password2": "secret123"
}
```

**Пример логина:**
```json
POST /api/auth/login/
{
  "username": "ivanov",
  "password": "secret123"
}
```

---

### Справочники (только чтение, для всех авторизованных)

| URL | Фильтры/поиск |
|---|---|
| `GET /api/schools/` | `?search=название` |
| `GET /api/academic-years/` | `?school=1` |
| `GET /api/bell-schedules/` | `?school=1&shift_number=1` |
| `GET /api/vacation-types/` | — |
| `GET /api/vacation-periods/` | `?academic_year=1&vacation_type=1&is_extra=true` |
| `GET /api/rooms/` | `?school=1&is_specialized=true&type=...` |
| `GET /api/teachers/` | `?search=фамилия` |
| `GET /api/class-groups/` | `?school=1&academic_year=1&grade_number=9` |
| `GET /api/subjects/` | `?is_elective=false&search=матем` |

---

### Расписание

| Метод | URL | Доступ | Описание |
|---|---|---|---|
| GET | `/api/schedule/` | Auth | Список записей расписания |
| GET | `/api/schedule/{id}/` | Auth | Одна запись |
| POST | `/api/schedule/` | Admin | Создать запись |
| PUT/PATCH | `/api/schedule/{id}/` | Admin | Изменить запись |
| DELETE | `/api/schedule/{id}/` | Admin | Удалить запись |
| GET | `/api/schedule/by-class/{id}/` | Auth | Расписание класса |
| GET | `/api/schedule/by-teacher/{id}/` | Auth | Расписание учителя |
| GET | `/api/schedule/by-room/{id}/` | Auth | Расписание кабинета |
| POST | `/api/schedule/generate/` | Admin | Запустить генерацию |

**Фильтры расписания:**
```
?academic_year=1
?class_group=5
?class_group__school=1
?teacher=3
?room=7
?day_of_week=1        # 1=Пн ... 6=Сб
?week_parity=0        # 0=обе, 1=нечёт, 2=чёт
?is_substitution=false
```

---

### Генерация расписания (заглушка)

```json
POST /api/schedule/generate/
Authorization: Bearer <admin_token>

{
  "academic_year_id": 1
}
```

> В `views.py` в методе `GenerateScheduleView.post()` подключи свой алгоритм генерации.

---

## Права доступа

| Роль | Возможности |
|---|---|
| Анонимный | Только регистрация и логин |
| Авторизованный пользователь | Просмотр всех справочников и расписания |
| Администратор (`is_staff=True`) | Всё выше + создание/изменение/удаление расписания + генерация |
| Суперадмин | Полный доступ к Admin-панели |

Назначить права в коде:
```python
user.is_staff = True
user.save()
```
Или через Django Admin: Пользователи → галочка «Статус персонала».

---

## Пагинация

Все списки отдаются по 50 записей:
```json
{
  "count": 120,
  "next": "http://localhost:8000/api/schedule/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Сброс SECRET_KEY для продакшна

В `settings.py` замени:
```python
SECRET_KEY = "django-insecure-REPLACE-ME-IN-PRODUCTION"
```
на генерированный ключ:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
