---
name: fast-project
description: Создать новый Django-проект компании поверх cookiecutter-django без ручной зачистки — uv, Docker, prek, /api-префикс, корневой conftest + conftest_plugins, test compose и CI (GitLab/GitHub), опционально Wagtail и S3. Использовать, когда просят "создай/разверни новый проект", "запусти кукикатор", "новый django-проект как у нас".
---

# fast-project

Генерирует проект в два шага: upstream `cookiecutter-django` (зафиксированный тег) → детерминированная
постобработка `scripts/fastproject.py`. Затем `scripts/verify.sh` проверяет результат.

**Правило:** не правь сгенерированный проект руками, чтобы «довести до ума». Если что-то не так —
чини `scripts/fastproject.py` или `assets/` и генерируй заново. Иначе следующий проект получится другим.

## 0. Предусловия

Проверь одной командой и скажи пользователю, чего не хватает:

```bash
uv --version && git --version && docker info --format '{{.ServerVersion}}'
```

Нужны: `uv`, `git`, запущенный Docker (для Wagtail-миграций и проверки), доступ в интернет (GitHub, PyPI).

## 1. Вопросы

Текстовые поля спрашивай по шагам, не списком «напиши всё одной строкой».

**1а. Название.** Отдельным коротким сообщением задай один вопрос: «Как называется проект?». Больше ничего
в этом сообщении не спрашивай: от названия зависят значения по умолчанию в следующих вопросах.

**1б. Идентификаторы.** Один вызов `AskUserQuestion`, 4 вопроса. Свой вариант пользователь вводит через «Other».
Перед вызовом прочитай `git config --global user.name` и `git config --global user.email`.

| Ключ (header) | Варианты |
|---|---|
| `project_slug` (Slug) | `<slug из названия>` (Recommended): `lower`, пробелы и `-` → `_`, остальные не `[a-z0-9_]` выкинуть; `<тот же slug без _>` |
| `author_name` (Автор) | `<git user.name>` (Recommended); `<project_name> Team` |
| `email` (Email) | `<git user.email>` (Recommended); `admin@<domain_name по умолчанию>` |
| `domain_name` (Домен) | `example.com` (Recommended); `<slug с _ → ->.ru` |

Если `git config` пуст, то первым вариантом для автора ставь `<project_name> Team`, а для email ставь `admin@example.com`.
Вторым вариантом ставь любое другое разумное значение. Помечай в описании варианта, откуда он взят (git, из названия).

**1в. Описание и папка.** Один вызов `AskUserQuestion`, 2 вопроса:

| Ключ (header) | Варианты |
|---|---|
| `description` (Описание) | `<project_name> backend` (Recommended); `Без описания` → пустая строка |
| папка (Папка) | `~/PycharmProjects` (Recommended); текущая рабочая директория |

Если пользователь ввёл значение через «Other», не переспрашивай его. Если введённый slug не подходит под
`^[a-z][a-z0-9_]*$`, скажи об этом и предложи исправленный вариант. Скрипт всё равно отвергнет невалидный slug.

**1г. Опции.** Выбор через `AskUserQuestion`, порциями по 4 вопроса. Первый вариант каждого вопроса — значение
по умолчанию с пометкой «(Recommended)». Если пользователь отвечает «по умолчанию» — бери первый вариант.

| Ключ | Варианты (первый — по умолчанию) |
|---|---|
| `python_version` | `3.14`, `3.13`, `3.12` |
| `django_version` | `6.0`, `5.2` |
| `use_wagtail` | `y`, `n` — Wagtail 8.0 + wagtail-modeladmin + wagtail-autocomplete, админка на `/api/cms/admin/` |
| `use_s3` | `y`, `n` — флаг `USE_S3`: True → S3 (AWS_* переменные), False → локальное хранение |
| `rest_api` | `DRF`, `Django Ninja`, `None` |
| `use_celery` | `y`, `n` |
| `use_async` | `n`, `y` — ASGI (gunicorn + uvicorn worker) |
| `ci_tool` | `Gitlab`, `Github`, `None` — генерируются только джобы prek и pytest |
| `remove_users_tests` | `y`, `n` — удалить тесты `users/` (UserFactory переносится в `conftest_plugins/user_fixtures.py`) |
| `username_type` | `email`, `username` |
| `mail_service` | `Mailgun`, `Other SMTP`, `Sendgrid` (ещё можно через «Other»: `Mailjet`, `Mandrill`, `Postmark`, `Brevo`, `SparkPost`). `Amazon SES` недоступен: upstream требует для него `cloud_provider=AWS` |
| `use_sentry` | `n`, `y` |
| `postgresql_version` | `18`, `17`, `16` |
| `open_source_license` | `Not open source`, `MIT`, `BSD`, `Apache Software License 2.0` |

Не спрашивай: `use_docker`, `cloud_provider`, `editor`, `use_whitenoise`, `keep_local_envs_in_vcs`,
`frontend_pipeline`, `use_heroku`, `windows` — они зафиксированы в скрипте как конвенции компании.

Перед запуском покажи итоговую таблицу ответов и спроси подтверждение.

## 2. Генерация

Запиши ответы в JSON во временный файл (scratchpad), значения `y`/`n` — строками. Все 20 ключей обязательны:
скрипт не подставляет значения по умолчанию, потому что у upstream они другие. Образец — `examples/full.json`.

```json
{
  "project_name": "Alpha Shop", "project_slug": "alpha_shop", "description": "...",
  "author_name": "...", "email": "...", "domain_name": "alpha.example.com",
  "python_version": "3.14", "django_version": "6.0", "use_wagtail": "y", "use_s3": "y",
  "rest_api": "DRF", "use_celery": "y", "use_async": "n", "ci_tool": "Gitlab",
  "remove_users_tests": "y", "username_type": "email", "mail_service": "Mailgun",
  "use_sentry": "n", "postgresql_version": "18", "open_source_license": "Not open source"
}
```

Запусти (папки `<output_dir>/<project_slug>` быть не должно — проверь заранее и спроси, если есть):

```bash
uv run --no-project --with cookiecutter==2.6.0 \
  python <путь к скиллу>/scripts/fastproject.py --answers <answers.json> --output-dir <output_dir>
```

Занимает 1–5 минут (с Wagtail дольше: собирается Docker-образ для миграций). Если скрипт упал на
`expected exactly one occurrence ...` — upstream поменял файл: сообщи пользователю, какой якорь не совпал,
не пытайся обойти вручную.

## 3. Проверка

```bash
<путь к скиллу>/scripts/verify.sh <output_dir>/<project_slug>
```

Шаги: `uv lock --check` → `prek run --all-files` → сборка test-образа → `makemigrations --check` →
`pytest` в `docker-compose.test.yml` → `manage.py check --deploy` с production-настройками.
Проект считается готовым, только если все шаги ok. Ожидаемые предупреждения, о которых не надо тревожить:
`security.W019` при Wagtail (превью Wagtail требует `X_FRAME_OPTIONS = "SAMEORIGIN"`) и
`No directory at: /app/staticfiles/` в тестах.

## 4. Отчёт пользователю

Коротко, по-русски:

1. Где лежит проект и итог проверки (каждый шаг verify — ok/fail; при fail — вывод ошибки).
2. Что сделано поверх upstream (список ниже, только применимые пункты).
3. Следующие шаги: `git commit` (репозиторий уже инициализирован, файлы добавлены, коммита нет),
   `docker compose -f docker-compose.local.yml up --build`, `createsuperuser`, заполнить
   `.envs/.production/*` (в git не попадают).

### Что делает постобработка

- Удаляет: `docs/`, `.readthedocs.yml`, `locale/`, `.devcontainer/`, `justfile`, `merge_production_dotenvs_in_dotenv.py`,
  папку `<slug>/templates/` целиком (`TEMPLATES["DIRS"] = []`), фронтенд-статику,
  HTML-вьюхи и urls `users/`, `users/context_processors.py`, маршруты home/about/users/accounts,
  `DJANGO_ADMIN_FORCE_ALLAUTH`.
- Удаляет демо-код upstream: `users/api/` (`UserViewSet`/`UserSerializer` или Ninja-роутер), `users/tasks.py`
  (`get_users_count`) и их тесты. `config/api_router.py` остаётся с пустым роутером (DRF),
  из `config/api.py` убирается `add_router("/users/")` (Ninja).
- `users` остаётся (AUTH_USER_MODEL), `LOGIN_URL = "admin:login"`.
- Все маршруты под `/api/`: `api/ping/` (health-check), `api/<ADMIN_URL>`, `api/docs/` (Swagger только staff),
  `STATIC_URL=/api/static/`, `MEDIA_URL=/api/media/`, nginx отдаёт `/api/media/`.
- БД только через `POSTGRES_HOST/PORT/DB/USER/PASSWORD`.
- Docker: `uv sync --locked` (local и production), entrypoint ждёт БД psycopg-циклом и логирует этапы,
  production `start` логирует план миграций, `migrate`, `collectstatic`, запуск сервера.
- Тесты: корневой `conftest.py` (только `pytest_plugins`) + `<slug>/conftest_plugins/`, `docker-compose.test.yml`,
  смоук-тесты в `core/tests/` (ping, логин Django-админки и Wagtail).
- Линтер: prek вместо pre-commit, ruff `line-length = 120`, `force-single-line = false`, игнор кириллицы (RUF001–003) и т.д.
- CI: только prek и pytest (`allow_failure: true` — конвенция компании).
- Wagtail: `core.CustomImage`/`CustomRendition`/`CustomDocument` с первой миграцией, все лимиты и форматы
  изображений/документов выписаны в `base.py` со значениями по умолчанию.
- S3: блок `USE_S3` в `base.py`, `AWS_*` в `.envs/.production/.django`.
- `.idea/` в `.gitignore`, `.envs/.local/` в git.

## Обновление версий

Все версии — константы в начале `scripts/fastproject.py` (`UPSTREAM_TAG`, `DJANGO_VERSIONS`, `WAGTAIL_PACKAGES`,
`S3_PACKAGES`, `PREK`) и ревизии хуков в `assets/pre-commit-config.yaml.j2`. После изменения прогоняй
генерацию минимум в двух вариантах (Wagtail+S3+Celery и без них, разные Python/Django) и `verify.sh` на обоих.
При смене версии Wagtail сверь значения по умолчанию в `assets/settings/wagtail.py.j2` с исходниками новой версии.
