# fast-project

Скилл для [Claude Code](https://claude.com/claude-code), который за ~15–20 минут создаёт новый Django-проект,
готовый к разработке: Docker, uv, линтеры, тесты, CI. Ручная зачистка шаблона не нужна.

Под капотом два шага:

1. **[cookiecutter-django](https://github.com/cookiecutter/cookiecutter-django)** генерирует проект.
   Версия зафиксирована тегом `2026.10.5`.
2. **`scripts/fastproject.py`** детерминированно приводит результат к нашим конвенциям: убирает лишнее
   и добавляет недостающее.

После генерации `scripts/verify.sh` проверяет, что проект собирается, проходит линтеры и тесты.
Одинаковые ответы всегда дают одинаковый проект.

Скилл можно запускать и без Claude Code, напрямую скриптом. См. [Запуск без Claude Code](#запуск-без-claude-code).

---

## Содержание

- [Что получается на выходе](#что-получается-на-выходе)
- [Требования](#требования)
- [Установка](#установка)
- [Использование через Claude Code](#использование-через-claude-code)
- [Запуск без Claude Code](#запуск-без-claude-code)
- [Как проверить, что всё работает](#как-проверить-что-всё-работает)
- [Запуск сгенерированного проекта](#запуск-сгенерированного-проекта)
- [Параметры (answers.json)](#параметры-answersjson)
- [Решение проблем](#решение-проблем)
- [Обновление версий](#обновление-версий)
- [Структура репозитория](#структура-репозитория)

---

## Что получается на выходе

**Основа**
- Python 3.12–3.14, Django 5.2 или 6.0, PostgreSQL 16–18.
- uv: зависимости в `pyproject.toml`, `uv.lock` фиксирует версии, в Docker `uv sync --locked`.
- Docker для локальной разработки, тестов и production. Entrypoint ждёт PostgreSQL и пишет в лог этапы
  запуска.
- БД настраивается через `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`, без `DATABASE_URL`.

**Чистый backend**
- Все маршруты под `/api/`: `api/ping/` (health-check), `api/admin/`, `api/docs/` (Swagger, только для staff),
  `api/static/`, `api/media/`.
- Никакого HTML-фронтенда: удалены шаблоны, страницы allauth, вьюхи `users` и демо-код upstream
  (`UserViewSet`, демо-задача Celery).
- Модель пользователя `users.User` остаётся. Вход в систему идёт через Django-админку.

**Опции**
- **Wagtail 8.0** с wagtail-modeladmin и wagtail-autocomplete. Админка на `/api/cms/admin/`, свои модели
  изображений и документов, все лимиты загрузки выписаны в настройках.
- **S3** через флаг `USE_S3`: `True` — хранилище S3, `False` — локальная файловая система.
- **REST API**: DRF или Django Ninja.
- **Celery**, **ASGI**, **Sentry**.

**Качество**
- [prek](https://github.com/j178/prek) вместо pre-commit, ruff (`line-length = 120`).
- Тесты: корневой `conftest.py`, фикстуры в `<slug>/conftest_plugins/`, отдельный `docker-compose.test.yml`,
  смоук-тесты (ping, вход в Django-админку и Wagtail).
- CI для GitLab или GitHub: джобы prek и pytest.

Полный список правок поверх upstream описан в [SKILL.md](SKILL.md), раздел «Что делает постобработка».

---

## Требования

| Что | Зачем | Как проверить | Установка |
|---|---|---|---|
| macOS или Linux | скрипты на bash | — | на Windows через WSL2 |
| [uv](https://docs.astral.sh/uv/) | запуск cookiecutter, lock зависимостей, prek | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | инициализация репозитория проекта | `git --version` | `xcode-select --install` / `apt install git` |
| Docker с Compose v2, **запущенный** | миграции Wagtail, сборка образов, тесты | `docker info` | [Docker Desktop](https://www.docker.com/products/docker-desktop/) или OrbStack |
| Интернет | GitHub (шаблон, хуки), PyPI, Docker Hub | — | — |
| [Claude Code](https://claude.com/claude-code) | только для запуска через `/fast-project` | `claude --version` | `npm install -g @anthropic-ai/claude-code` |

Python ставить отдельно не нужно: uv скачает нужную версию сам.

Проверка всего одной командой:

```bash
uv --version && git --version && docker info --format '{{.ServerVersion}}'
```

Если последняя команда падает с `Cannot connect to the Docker daemon`, значит, Docker не запущен.

---

## Установка

Клонируйте репозиторий в папку пользовательских скиллов Claude Code. Скилл станет доступен во всех проектах:

```bash
git clone https://github.com/AppleIpx/claude-skill-fast-project.git ~/.claude/skills/fast-project
```

Обновление:

```bash
git -C ~/.claude/skills/fast-project pull
```

Для запуска без Claude Code репозиторий можно клонировать в любую папку.

---

## Использование через Claude Code

1. Запустите `claude` в любой папке.
2. Введите `/fast-project` или просто напишите «создай новый django-проект».
3. Ответьте на вопросы:
   - название проекта;
   - slug, автор, email, домен. Предложены готовые варианты, свой можно ввести через «Other»;
   - описание и папка для проекта (по умолчанию `~/PycharmProjects`);
   - опции порциями по 4: Python, Django, Wagtail, S3, API, Celery, CI и т.д. Первый вариант в каждом
     вопросе — рекомендованный.
4. Claude покажет итоговую таблицу ответов. Подтвердите её.
5. Claude сгенерирует проект, прогонит `verify.sh` и пришлёт отчёт: результат каждого шага проверки и
   дальнейшие шаги.

Генерация занимает 1–5 минуты, с Wagtail дольше: собирается Docker-образ для миграций. Первый запуск на
машине дольше: скачиваются базовые образы.

---

## Запуск без Claude Code

Подготовьте файл ответов. Готовые примеры лежат в [`examples/`](examples), все поля описаны в разделе
[Параметры](#параметры-answersjson).

```bash
cd ~/.claude/skills/fast-project   # или куда вы клонировали репозиторий

# 1. Генерация. Папки <output-dir>/<project_slug> быть не должно.
uv run --no-project --with cookiecutter==2.6.0 \
  python scripts/fastproject.py --answers examples/full.json --output-dir ~/PycharmProjects

# 2. Проверка
scripts/verify.sh ~/PycharmProjects/demo_full
```

В конце генерации печатается `[fast-project] done: <путь к проекту>`. Если что-то пошло не так, печатается
`[fast-project] FAILED: ...`, а недоделанный проект остаётся на диске для разбора.

---

## Как проверить, что всё работает

Самый быстрый способ убедиться, что скилл рабочий: сгенерировать два противоположных варианта из
`examples/` и прогнать проверку на обоих.

| Файл | Что покрывает |
|---|---|
| `examples/full.json` | Python 3.14, Django 6.0, Wagtail, S3, DRF, Celery, GitLab CI, логин по email, тесты `users/` удалены |
| `examples/minimal.json` | Python 3.12, Django 5.2, без Wagtail, S3 и Celery, Django Ninja, GitHub CI, логин по username, тесты `users/` оставлены, лицензия MIT |

```bash
cd ~/.claude/skills/fast-project
OUT=$(mktemp -d)

for v in full minimal; do
  uv run --no-project --with cookiecutter==2.6.0 \
    python scripts/fastproject.py --answers examples/$v.json --output-dir "$OUT" \
  && scripts/verify.sh "$OUT/demo_$v"
done
```

> Запускайте варианты **по очереди**, не параллельно: cookiecutter кладёт шаблон в общий кэш
> `~/.cookiecutters/`, и одновременные запуски мешают друг другу.

`verify.sh` выполняет шесть шагов. В конце печатается сводка, и при успехе все шаги `ok`:

```
=== [verify] summary
  uv lock --check: ok
  prek run --all-files: ok
  docker compose test build: ok
  makemigrations --check: ok
  pytest: ok
  check --deploy (production settings): ok
```

| Шаг | Что проверяет |
|---|---|
| `uv lock --check` | `uv.lock` соответствует `pyproject.toml` |
| `prek run --all-files` | все хуки (ruff, django-upgrade и др.) проходят без изменений файлов |
| сборка test-образа | `docker-compose.test.yml` собирается |
| `makemigrations --check` | нет недостающих миграций |
| `pytest` | смоук-тесты проходят на реальном PostgreSQL |
| `check --deploy` | production-настройки валидны |

Если какой-то шаг падает, скрипт останавливается с ненулевым кодом, ошибка видна выше в выводе. Контейнеры
и тома тестового окружения удаляются автоматически.

**Ожидаемые предупреждения**, на них не нужно обращать внимание:
- `security.W019` в `check --deploy`, только с Wagtail: превью Wagtail работает в iframe, поэтому
  `X_FRAME_OPTIONS = "SAMEORIGIN"`.
- `UserWarning: No directory at: /app/staticfiles/` в pytest: в тестах статика не собирается.

После проверки временную папку можно удалить: `rm -rf "$OUT"`.

---

## Запуск сгенерированного проекта

Внутри проекта уже инициализирован git-репозиторий, файлы добавлены в индекс, но коммита нет.

```bash
cd ~/PycharmProjects/<project_slug>

git commit -m "Initial commit"

docker compose -f docker-compose.local.yml up --build

# в другом терминале
docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
```

| Что | URL |
|---|---|
| Health-check | http://localhost:8000/api/ping/ |
| Django-админка | http://localhost:8000/api/admin/ |
| Wagtail-админка (если включён) | http://localhost:8000/api/cms/admin/ |
| Swagger (только staff, если есть API) | http://localhost:8000/api/docs/ |
| Flower (если включён Celery) | http://localhost:5555/ |

Порты 8000 (и 5555 с Celery) должны быть свободны.

Для production заполните `.envs/.production/.django` и `.envs/.production/.postgres`: секретный ключ,
почта, `AWS_*` для S3. Эти файлы в git не попадают.

Подробнее см. README внутри сгенерированного проекта.

---

## Параметры (answers.json)

**Все ключи обязательны.** Значения по умолчанию у cookiecutter-django отличаются от наших (например,
`rest_api=None`, лицензия MIT с чужим автором), поэтому скрипт ничего не подставляет молча. Если ключа нет,
скрипт до генерации печатает список недостающих. Проще всего скопировать `examples/full.json` и поправить.

Значения `y`/`n` указываются строками.

| Ключ | Значения | Рекомендуется | Описание |
|---|---|---|---|
| `project_name` | любая непустая строка | — | Название проекта |
| `project_slug` | `^[a-z][a-z0-9_]*$` | из названия: `My Shop` → `my_shop` | Имя Python-пакета и папки проекта |
| `description` | строка, можно `""` | `<название> backend` | Описание |
| `author_name` | строка | — | Пустая строка допустима только при `Not open source` |
| `email` | email | — | Email автора |
| `domain_name` | домен | `example.com` | Домен для production-настроек |
| `python_version` | `3.14`, `3.13`, `3.12` | `3.14` | |
| `django_version` | `6.0`, `5.2` | `6.0` | |
| `use_wagtail` | `y`, `n` | `y` | Wagtail 8.0 + modeladmin + autocomplete |
| `use_s3` | `y`, `n` | `y` | Блок `USE_S3` и переменные `AWS_*` |
| `rest_api` | `DRF`, `Django Ninja`, `None` | `DRF` | |
| `use_celery` | `y`, `n` | `y` | |
| `use_async` | `y`, `n` | `n` | ASGI: gunicorn + uvicorn worker |
| `ci_tool` | `Gitlab`, `Github`, `None` | `Gitlab` | Только джобы prek и pytest |
| `remove_users_tests` | `y`, `n` | `y` | Удалить тесты `users/`, `UserFactory` переезжает в `conftest_plugins/` |
| `username_type` | `email`, `username` | `email` | Поле для входа |
| `mail_service` | `Mailgun`, `Other SMTP`, `Sendgrid`, `Mailjet`, `Mandrill`, `Postmark`, `Brevo`, `SparkPost` | `Mailgun` | `Amazon SES` не поддерживается: upstream требует для него `cloud_provider=AWS` |
| `use_sentry` | `y`, `n` | `n` | |
| `postgresql_version` | `18`, `17`, `16` | `18` | |
| `open_source_license` | `Not open source`, `MIT`, `BSD`, `Apache Software License 2.0` | `Not open source` | |

Остальные параметры cookiecutter-django (`use_docker`, `cloud_provider`, `use_whitenoise` и т.д.)
зафиксированы в скрипте как конвенции компании и не настраиваются.

Ответы проверяются до запуска генерации. Скрипт останавливается с понятной ошибкой, если не хватает ключа,
slug или email невалидны, пустой автор при открытой лицензии, недопустимая версия Python или Django, или
выбран `Amazon SES`.

---

## Решение проблем

| Симптом | Причина и решение |
|---|---|
| `Cannot connect to the Docker daemon` | Docker не запущен. Запустите Docker Desktop или OrbStack. |
| Генерация падает сразу: папка уже существует | `<output-dir>/<project_slug>` уже есть. Удалите её или выберите другой slug. |
| `FileNotFoundError: ... ~/.cookiecutters/cookiecutter-django` | Две генерации запущены параллельно. Запускайте по одной. |
| `expected exactly one occurrence of ...` или `expected exactly one match ...` | Шаблон upstream изменился, и якорь в `scripts/fastproject.py` больше не совпадает. Обновите якорь, а не правьте проект руками. См. [Обновление версий](#обновление-версий). |
| `Leftovers found: ...` | В проекте осталась ссылка на удалённую часть (например, `users:`). Значит, в upstream появился новый файл с такой ссылкой, и его нужно добавить в постобработку. |
| `port is already allocated` при `up` | Порт 8000 или 5555 занят. Остановите другой проект: `docker compose ... down`. |
| `missing answers: ...`, `project_slug must match ...`, `author_name is required ...` | Невалидный файл ответов. См. [Параметры](#параметры-answersjson). |

Главное правило: **не правьте сгенерированный проект руками, чтобы довести его до ума.** Если что-то не так,
чините `scripts/fastproject.py` или `assets/` и генерируйте заново. Иначе следующий проект получится другим.

---

## Обновление версий

Все версии — константы в начале [`scripts/fastproject.py`](scripts/fastproject.py):

| Константа | Что |
|---|---|
| `UPSTREAM_TAG` | тег cookiecutter-django |
| `DJANGO_VERSIONS` | точные версии Django для `5.2` и `6.0` |
| `WAGTAIL_PACKAGES` | Wagtail и плагины |
| `S3_PACKAGES` | django-storages |
| `PREK` | версия prek |

Ревизии хуков лежат в [`assets/pre-commit-config.yaml.j2`](assets/pre-commit-config.yaml.j2). При смене
версии Wagtail сверьте значения по умолчанию в `assets/settings/wagtail.py.j2` с исходниками новой версии.

После любого изменения прогоните оба примера из `examples/` и `verify.sh` на обоих, как описано в
разделе [Как проверить, что всё работает](#как-проверить-что-всё-работает).

---

## Структура репозитория

```
.
├── SKILL.md              # инструкция для Claude Code: вопросы, генерация, проверка, отчёт
├── README.md
├── examples/             # готовые answers.json для проверки
│   ├── full.json
│   └── minimal.json
├── scripts/
│   ├── fastproject.py    # генерация: cookiecutter-django + постобработка
│   └── verify.sh         # проверка сгенерированного проекта
└── assets/               # Jinja-шаблоны файлов, которые скилл добавляет в проект
    ├── ci/               # GitLab / GitHub CI
    ├── compose/          # entrypoint и start
    ├── conftest_plugins/ # фикстуры pytest
    ├── core/             # приложение core: ping, модели Wagtail, смоук-тесты
    ├── settings/         # блоки настроек: S3, загрузки, Wagtail
    └── ...
```
