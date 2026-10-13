"""Generate a company Django project on top of cookiecutter-django.

Usage (from any directory):

    uv run --no-project --with cookiecutter==2.6.0 python fastproject.py \
        --answers answers.json --output-dir ~/PycharmProjects

Every change to the upstream output is deterministic: files we own are rendered
from ``assets/`` and upstream files are patched with ``replace_once``, which
fails loudly when the upstream text no longer matches. When it fails after an
upstream bump, fix the anchor here instead of patching the result by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from cookiecutter.main import cookiecutter
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# ---------------------------------------------------------------------------
# Pinned versions. Bump them together and re-run a test generation.
# ---------------------------------------------------------------------------
UPSTREAM = "https://github.com/cookiecutter/cookiecutter-django"
UPSTREAM_TAG = "2026.10.5"

PYTHON_VERSIONS = ("3.12", "3.13", "3.14")
DEFAULT_PYTHON = "3.14"
DJANGO_VERSIONS = {"5.2": "5.2.18", "6.0": "6.0.8"}
DEFAULT_DJANGO = "6.0"
# Upstream tag 2026.10.5 is built for these defaults; others are patched in.
UPSTREAM_PYTHON = "3.14"

PREK = "prek==0.5.5"
WAGTAIL_PACKAGES = (
    "wagtail==8.0",
    "wagtail-modeladmin==2.5.0",
    "wagtail-autocomplete==0.12.1",
)
S3_PACKAGES = ("django-storages[s3]==1.14.6",)

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"

# Answers the skill never asks: they are company conventions.
FIXED_UPSTREAM_ANSWERS = {
    "use_docker": "y",
    "cloud_provider": "None",  # S3 is wired by our own USE_S3 block
    "editor": "None",  # .idea is git-ignored
    "use_whitenoise": "y",
    "keep_local_envs_in_vcs": "y",
    "frontend_pipeline": "None",  # templates are removed
    "use_heroku": "n",
    "windows": "n",
}
# Upstream answers the skill passes through from the user.
PASSTHROUGH_UPSTREAM_KEYS = (
    "project_name",
    "project_slug",
    "description",
    "author_name",
    "domain_name",
    "email",
    "version",
    "open_source_license",
    "username_type",
    "timezone",
    "postgresql_version",
    "mail_service",
    "rest_api",
    "use_async",
    "use_celery",
    "mail_catcher",
    "use_sentry",
    "ci_tool",
)
REQUIRED_ANSWER_KEYS = (
    "project_name",
    "project_slug",
    "description",
    "author_name",
    "email",
    "domain_name",
    "python_version",
    "django_version",
    "use_wagtail",
    "use_s3",
    "rest_api",
    "use_celery",
    "use_async",
    "ci_tool",
    "remove_users_tests",
    "username_type",
    "mail_service",
    "use_sentry",
    "postgresql_version",
    "open_source_license",
)


class PostprocessError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[fast-project] {message}", flush=True)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        msg = f"{path}: expected exactly one occurrence of {old!r}, found {count}"
        raise PostprocessError(msg)
    path.write_text(text.replace(old, new))


def replace_all(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        msg = f"{path}: {old!r} not found"
        raise PostprocessError(msg)
    path.write_text(text.replace(old, new))


def regex_once(path: Path, pattern: str, new: str, flags: int = 0) -> None:
    text = path.read_text()
    result, count = re.subn(pattern, new, text, flags=flags)
    if count != 1:
        msg = f"{path}: expected exactly one match of /{pattern}/, found {count}"
        raise PostprocessError(msg)
    path.write_text(result)


def append(path: Path, text: str) -> None:
    content = path.read_text()
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content + text)


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    log("$ " + " ".join(cmd))
    full_env = {**os.environ, **(env or {})}
    # Never install into whatever virtualenv the caller has activated.
    full_env.pop("VIRTUAL_ENV", None)
    subprocess.run(cmd, cwd=cwd, env=full_env, check=True)


class Renderer:
    def __init__(self, ctx: dict) -> None:
        self.ctx = ctx
        self.env = Environment(
            loader=FileSystemLoader(ASSETS),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def text(self, template: str) -> str:
        return self.env.get_template(template).render(**self.ctx)

    def write(self, template: str, dest: Path, *, executable: bool = False) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.text(template))
        if executable:
            dest.chmod(0o755)


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------
def yes(value: object) -> bool:
    return str(value).lower() in {"y", "yes", "true", "1"}


def load_answers(path: Path) -> dict:
    answers = json.loads(path.read_text())
    # Upstream defaults differ from ours (e.g. rest_api=None, license=MIT), so nothing is implicit.
    missing = [key for key in REQUIRED_ANSWER_KEYS if key not in answers]
    if missing:
        msg = f"{path}: missing answers: {', '.join(missing)} (see examples/full.json)"
        raise SystemExit(msg)
    python_version = answers.get("python_version", DEFAULT_PYTHON)
    if python_version not in PYTHON_VERSIONS:
        msg = f"python_version must be one of {PYTHON_VERSIONS}, got {python_version}"
        raise SystemExit(msg)
    django_version = answers.get("django_version", DEFAULT_DJANGO)
    if django_version not in DJANGO_VERSIONS:
        msg = f"django_version must be one of {tuple(DJANGO_VERSIONS)}, got {django_version}"
        raise SystemExit(msg)
    if answers.get("mail_service") == "Amazon SES":
        # Upstream ties SES to cloud_provider=AWS, and we always generate with cloud_provider=None.
        msg = (
            "mail_service 'Amazon SES' is not supported (needs cloud_provider=AWS); use another service or 'Other SMTP'"
        )
        raise SystemExit(msg)
    if not answers.get("project_name", "").strip():
        msg = "project_name is required"
        raise SystemExit(msg)
    slug = answers.get("project_slug")
    if slug is not None and not re.fullmatch(r"[a-z][a-z0-9_]*", slug):
        msg = f"project_slug must match ^[a-z][a-z0-9_]*$ (a Python package name), got {slug!r}"
        raise SystemExit(msg)
    email = answers.get("email")
    if email is not None and "@" not in email:
        msg = f"email must contain '@', got {email!r}"
        raise SystemExit(msg)
    license_name = answers.get("open_source_license", "Not open source")
    if license_name != "Not open source" and not answers.get("author_name", "").strip():
        # Otherwise LICENSE ends up with "Copyright (c) <year>, " and no holder.
        msg = f"author_name is required for open_source_license={license_name!r}"
        raise SystemExit(msg)
    return answers


def build_context(answers: dict, project_dir: Path) -> dict:
    python_version = answers.get("python_version", DEFAULT_PYTHON)
    django_version = answers.get("django_version", DEFAULT_DJANGO)
    return {
        "project_name": answers["project_name"],
        "slug": project_dir.name,
        "domain_name": answers.get("domain_name", "example.com"),
        "python_version": python_version,
        "py_nodot": python_version.replace(".", ""),
        "django_version": django_version,
        "django_pin": DJANGO_VERSIONS[django_version],
        "rest_api": answers.get("rest_api", "DRF"),
        "use_async": yes(answers.get("use_async", "n")),
        "use_celery": yes(answers.get("use_celery", "n")),
        "use_wagtail": yes(answers.get("use_wagtail", "n")),
        "use_s3": yes(answers.get("use_s3", "n")),
        "remove_users_tests": yes(answers.get("remove_users_tests", "y")),
        "ci_tool": answers.get("ci_tool", "Gitlab"),
    }


def run_upstream(answers: dict, output_dir: Path) -> Path:
    extra = {key: answers[key] for key in PASSTHROUGH_UPSTREAM_KEYS if key in answers}
    extra.update(FIXED_UPSTREAM_ANSWERS)
    log(f"cookiecutter-django {UPSTREAM_TAG} → {output_dir}")
    result = cookiecutter(
        UPSTREAM,
        checkout=UPSTREAM_TAG,
        no_input=True,
        output_dir=str(output_dir),
        extra_context=extra,
    )
    return Path(result)


# ---------------------------------------------------------------------------
# Postprocess steps
# ---------------------------------------------------------------------------
def drop_unused_upstream_parts(root: Path, slug: str) -> None:
    for rel in (
        "docs",
        ".readthedocs.yml",
        "docker-compose.docs.yml",
        "compose/local/docs",
        "locale",
        ".devcontainer",
        "justfile",
        "merge_production_dotenvs_in_dotenv.py",
        "tests",  # only held the merge_production_dotenvs test
        f"{slug}/conftest.py",  # replaced by root conftest.py + conftest_plugins/
    ):
        remove(root / rel)

    templates = root / slug / "templates"
    for rel in (
        "pages",
        "account",
        "allauth",
        "users",
        "base.html",
        "403.html",
        "403_csrf.html",
        "404.html",
        "500.html",
    ):
        remove(templates / rel)
    if any(templates.iterdir()):
        msg = f"{templates}: unexpected upstream templates left: {sorted(p.name for p in templates.iterdir())}"
        raise PostprocessError(msg)
    # No HTML pages: only package templates (admin, wagtail, drf) are used via APP_DIRS.
    remove(templates)

    # Frontend assets were only used by the removed base.html.
    static = root / slug / "static"
    for child in static.iterdir():
        remove(child)
    (static / ".gitkeep").touch()

    base = root / "config/settings/base.py"
    replace_once(
        base,
        '# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths\nLOCALE_PATHS = [str(BASE_DIR / "locale")]\n',
        "",
    )
    replace_once(base, '"DIRS": [str(APPS_DIR / "templates")],', '"DIRS": [],')


def strip_users_web_layer(root: Path, slug: str) -> None:
    """Users stay as AUTH_USER_MODEL, but lose HTML views, urls and the allauth admin redirect."""
    users = root / slug / "users"
    for rel in ("views.py", "urls.py", "tests/test_views.py", "tests/test_urls.py", "tests/test_models.py"):
        remove(users / rel)

    models = users / "models.py"
    regex_once(models, r"\n    def get_absolute_url\(self\).*", "\n", flags=re.DOTALL)
    replace_once(models, "from django.urls import reverse\n", "")

    admin = users / "admin.py"
    regex_once(
        admin,
        r"\nif settings\.DJANGO_ADMIN_FORCE_ALLAUTH:\n.*?admin\.site\.login\)  # type: ignore\[method-assign\]\n",
        "",
        flags=re.DOTALL,
    )
    replace_once(admin, "from allauth.account.decorators import secure_admin_login\n", "")
    replace_once(admin, "from django.conf import settings\n", "")

    test_admin = users / "tests/test_admin.py"
    if test_admin.exists():
        regex_once(test_admin, r"\n    @pytest\.fixture\n    def _force_allauth.*", "\n", flags=re.DOTALL)

    base = root / "config/settings/base.py"
    replace_once(base, 'LOGIN_REDIRECT_URL = "users:redirect"', 'LOGIN_REDIRECT_URL = "admin:index"')
    replace_once(base, 'LOGIN_URL = "account_login"', 'LOGIN_URL = "admin:login"')
    regex_once(
        base,
        r"# https://cookiecutter-django\.readthedocs\.io/en/latest/settings\.html#other-environment-settings\n"
        r"# Force the `admin` sign in process to go through the `django-allauth` workflow\n"
        r'DJANGO_ADMIN_FORCE_ALLAUTH = env\.bool\("DJANGO_ADMIN_FORCE_ALLAUTH", default=False\)\n',
        "",
    )

    # allauth_settings only fed the removed HTML templates.
    remove(users / "context_processors.py")
    replace_once(base, f'                "{slug}.users.context_processors.allauth_settings",\n', "")


def strip_users_api_and_tasks(root: Path, slug: str, ctx: dict) -> None:
    """Drop upstream demo code: the users API (DRF/Ninja) and the get_users_count Celery task."""
    users = root / slug / "users"
    # Tests go too: they only matter when remove_users_tests=n.
    for rel in ("api", "tests/api", "tasks.py", "tests/test_tasks.py"):
        remove(users / rel)

    if ctx["rest_api"] == "DRF":
        # The router stays empty: new ViewSets are registered here.
        api_router = root / "config/api_router.py"
        replace_once(api_router, f"from {slug}.users.api.views import UserViewSet\n\n", "")
        replace_once(api_router, 'router.register("users", UserViewSet)\n', "")
    elif ctx["rest_api"] == "Django Ninja":
        replace_once(
            root / "config/api.py",
            f'\n\napi.add_router("/users/", "{slug}.users.api.views.router")\n',
            "\n",
        )


def setup_tests(root: Path, slug: str, ctx: dict, r: Renderer) -> None:
    users_tests = root / slug / "users/tests"
    if ctx["remove_users_tests"]:
        # The factory is needed by fixtures, so it moves out before the tests go.
        factory = (users_tests / "factories.py").read_text()
        future = "from __future__ import annotations\n"
        if not factory.startswith(future):
            msg = f"{users_tests / 'factories.py'}: expected to start with {future!r}"
            raise PostprocessError(msg)
        ctx["user_factory_source"] = factory.replace(future, future + "\nimport pytest\n", 1).rstrip("\n") + "\n"
        remove(users_tests)
    else:
        ctx["user_factory_source"] = None

    r.write("conftest.py.j2", root / "conftest.py")
    plugins = root / slug / "conftest_plugins"
    r.write("conftest_plugins/__init__.py.j2", plugins / "__init__.py")
    r.write("conftest_plugins/base_fixtures.py.j2", plugins / "base_fixtures.py")
    r.write("conftest_plugins/user_fixtures.py.j2", plugins / "user_fixtures.py")
    if ctx["rest_api"] == "DRF":
        r.write("conftest_plugins/api_client_fixtures.py.j2", plugins / "api_client_fixtures.py")

    r.write("docker-compose.test.yml.j2", root / "docker-compose.test.yml")

    test_settings = root / "config/settings/test.py"
    if ctx["use_celery"]:
        replace_once(
            test_settings,
            "# Your stuff...\n",
            "# CELERY\n"
            "# ------------------------------------------------------------------------------\n"
            "# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-always-eager\n"
            "CELERY_TASK_ALWAYS_EAGER = True\n"
            "# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-eager-propagates\n"
            "CELERY_TASK_EAGER_PROPAGATES = True\n"
            "# Your stuff...\n",
        )


def add_core_app(root: Path, slug: str, ctx: dict, r: Renderer) -> None:
    core = root / slug / "core"
    r.write("core/__init__.py.j2", core / "__init__.py")
    r.write("core/apps.py.j2", core / "apps.py")
    r.write("core/views.py.j2", core / "views.py")
    r.write("core/models.py.j2", core / "models.py")
    r.write("core/migrations/__init__.py.j2", core / "migrations/__init__.py")
    r.write("core/tests/__init__.py.j2", core / "tests/__init__.py")
    r.write("core/tests/test_ping.py.j2", core / "tests/test_ping.py")
    # Smoke tests for the admin routes: they would catch a broken urls.py right after generation.
    r.write("core/tests/test_urls.py.j2", core / "tests/test_urls.py")
    if ctx["use_wagtail"] and ctx["rest_api"] == "DRF":
        r.write("core/openapi.py.j2", core / "openapi.py")

    base = root / "config/settings/base.py"
    replace_once(
        base,
        f'    "{slug}.users",\n    # Your stuff: custom apps go here\n',
        f'    "{slug}.users",\n    "{slug}.core",\n    # Your stuff: custom apps go here\n',
    )


def configure_settings(root: Path, ctx: dict, r: Renderer) -> None:
    base = root / "config/settings/base.py"

    # Only separate POSTGRES_* variables, no DATABASE_URL.
    regex_once(
        base,
        r'\nif os\.getenv\("DATABASE_URL", default=None\):\n    DATABASES = \{"default": env\.db\("DATABASE_URL"\)\}\nelse:\n'
        r"(    DATABASES = \{\n(?:.*\n)*?    \}\n)",
        lambda m: "\n" + "\n".join(line[4:] if line else line for line in m.group(1).split("\n")),
    )
    if "os." not in base.read_text().replace("import os\n", ""):
        replace_once(base, "import os\n", "")

    # Everything is served under /api/.
    replace_once(base, 'STATIC_URL = "/static/"', 'STATIC_URL = "/api/static/"')
    replace_once(
        base,
        "# MEDIA\n"
        "# ------------------------------------------------------------------------------\n"
        "# https://docs.djangoproject.com/en/dev/ref/settings/#media-root\n"
        'MEDIA_ROOT = str(APPS_DIR / "media")\n'
        "# https://docs.djangoproject.com/en/dev/ref/settings/#media-url\n"
        'MEDIA_URL = "/media/"\n',
        r.text("settings/storages.py.j2"),
    )
    replace_once(base, "# Your stuff...\n", r.text("settings/uploads.py.j2") + "# Your stuff...\n")

    production = root / "config/settings/production.py"
    replace_once(
        production, "from .base import DATABASES\n", "from .base import DATABASES\nfrom .base import STORAGES\n"
    )
    replace_once(
        production,
        "# STATIC & MEDIA\n"
        "# ------------------------\n"
        "STORAGES = {\n"
        '    "default": {\n'
        '        "BACKEND": "django.core.files.storage.FileSystemStorage",\n'
        "    },\n"
        '    "staticfiles": {\n'
        '        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",\n'
        "    },\n"
        "}\n",
        "# STATIC & MEDIA\n"
        "# ------------------------------------------------------------------------------\n"
        '# "default" storage is configured in base.py (local filesystem or S3, see USE_S3).\n'
        'STORAGES["staticfiles"] = {\n'
        '    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",\n'
        "}\n",
    )

    if ctx["use_wagtail"]:
        # Wagtail's search index uses SearchVectorField on PostgreSQL.
        replace_once(
            base,
            '    "django.contrib.admin",\n',
            '    "django.contrib.admin",\n    "django.contrib.postgres",\n',
        )
        replace_once(
            base,
            '    "allauth.socialaccount",\n',
            '    "allauth.socialaccount",\n' + r.text("settings/wagtail_apps.py.j2"),
        )
        replace_once(
            base,
            '    "allauth.account.middleware.AccountMiddleware",\n]',
            '    "allauth.account.middleware.AccountMiddleware",\n'
            '    "wagtail.contrib.redirects.middleware.RedirectMiddleware",\n]',
        )
        # Wagtail previews render inside an iframe of the admin.
        replace_once(base, 'X_FRAME_OPTIONS = "DENY"', 'X_FRAME_OPTIONS = "SAMEORIGIN"')
        replace_once(base, "# Your stuff...\n", r.text("settings/wagtail.py.j2") + "# Your stuff...\n")

    r.write("urls.py.j2", root / "config/urls.py")


def configure_envs(root: Path, ctx: dict) -> None:
    local = root / ".envs/.local/.django"
    production = root / ".envs/.production/.django"
    if ctx["use_s3"]:
        append(
            local,
            "\n# S3\n# ------------------------------------------------------------------------------\nUSE_S3=False\n",
        )
        append(
            production,
            "\n# S3\n"
            "# ------------------------------------------------------------------------------\n"
            "USE_S3=True\n"
            "AWS_ACCESS_KEY_ID=\n"
            "AWS_SECRET_ACCESS_KEY=\n"
            "AWS_S3_ENDPOINT_URL=\n"
            "AWS_REGION_NAME=ru-1\n"
            "AWS_STORAGE_BUCKET_NAME=\n",
        )
    if ctx["use_wagtail"]:
        append(
            local,
            "\n# Wagtail\n# ------------------------------------------------------------------------------\n"
            "FRONTEND_URL=http://localhost:8000\n",
        )
        append(
            production,
            "\n# Wagtail\n# ------------------------------------------------------------------------------\n"
            f"FRONTEND_URL=https://{ctx['domain_name']}\n",
        )


def configure_docker(root: Path, ctx: dict, r: Renderer) -> None:
    pv = ctx["python_version"]

    r.write("compose/entrypoint.j2", root / "compose/production/django/entrypoint", executable=True)
    r.write("compose/start.j2", root / "compose/production/django/start", executable=True)

    local = root / "compose/local/django/Dockerfile"
    # Upstream mounts the lock as a file literally named "uv.lock:rw", so uv never sees it.
    replace_all(local, "target=uv.lock:rw", "target=uv.lock")
    replace_once(local, "    uv sync --no-install-project\n", "    uv sync --locked --no-install-project\n")
    replace_once(local, "    uv sync\n", "    uv sync --locked\n")
    replace_once(local, "  libpq-dev \\\n  gettext \\\n  wait-for-it\n", "  libpq-dev \\\n  gettext\n")
    regex_once(
        local,
        r"# devcontainer dependencies and utils\n.*?&& chmod 0440 /etc/sudoers\.d/dev-user\n\n",
        "",
        flags=re.DOTALL,
    )

    production = root / "compose/production/django/Dockerfile"
    replace_once(production, "  # entrypoint\n  wait-for-it \\\n", "")
    replace_once(
        production,
        'RUN DATABASE_URL="postgres://dummy" \\\n'
        '  DJANGO_SETTINGS_MODULE="config.settings.test" \\\n'
        "  python manage.py compilemessages\n\n",
        "",
    )

    if pv != UPSTREAM_PYTHON:
        for dockerfile in (local, production):
            replace_all(dockerfile, f"python{UPSTREAM_PYTHON}", f"python{pv}")
        replace_once(production, f"FROM python:{UPSTREAM_PYTHON}-slim", f"FROM python:{pv}-slim")

    nginx = root / "compose/production/nginx/default.conf"
    if nginx.exists():
        replace_once(nginx, "location /media/ {", "location /api/media/ {")


def configure_python_and_lint(root: Path, ctx: dict, r: Renderer) -> None:
    pv = ctx["python_version"]
    pyproject = root / "pyproject.toml"

    (root / ".python-version").write_text(f"{pv}\n")
    replace_once(pyproject, f'requires-python = "=={UPSTREAM_PYTHON}.*"', f'requires-python = "=={pv}.*"')
    replace_once(
        pyproject,
        f'"Programming Language :: Python :: {UPSTREAM_PYTHON}",',
        f'"Programming Language :: Python :: {pv}",',
    )
    replace_once(pyproject, f'python_version = "{UPSTREAM_PYTHON}"', f'python_version = "{pv}"')

    # prek instead of pre-commit, no Sphinx (docs/ is removed).
    regex_once(pyproject, r'  "pre-commit==[^"]+",\n', f'  "{PREK}",\n')
    regex_once(pyproject, r'  "sphinx==[^"]+",\n', "")
    regex_once(pyproject, r'  "sphinx-autobuild==[^"]+",\n', "")

    # Company ruff/djlint conventions.
    replace_once(
        pyproject, "[tool.ruff]\n", f'[tool.ruff]\nline-length = 120\ntarget-version = "py{ctx["py_nodot"]}"\n'
    )
    regex_once(
        pyproject,
        r"lint\.ignore = \[\n.*?\]\nlint\.isort\.force-single-line = true\n",
        r.text("pyproject/ruff_ignore.toml.j2"),
        flags=re.DOTALL,
    )
    replace_once(pyproject, "max_line_length = 119", "max_line_length = 120")
    regex_once(pyproject, r"# ==== pyproject-fmt ====\n\[tool\.pyproject-fmt\]\n[^\[]*?\n\n", "")

    r.write("pre-commit-config.yaml.j2", root / ".pre-commit-config.yaml")

    gitignore = root / ".gitignore"
    append(gitignore, "\n# IDE\n.idea/\n")


def configure_ci(root: Path, ctx: dict, r: Renderer) -> None:
    ci_tool = ctx["ci_tool"]
    if ci_tool == "Gitlab":
        r.write("ci/gitlab-ci.yml.j2", root / ".gitlab-ci.yml")
    elif ci_tool == "Github":
        r.write("ci/github-ci.yml.j2", root / ".github/workflows/ci.yml")
    else:
        log(f"ci_tool={ci_tool}: CI files left as upstream generated them")


def configure_readme(root: Path, r: Renderer) -> None:
    r.write("README.md.j2", root / "README.md")


def sync_dependencies(root: Path, ctx: dict) -> None:
    packages: list[str] = []
    if ctx["django_version"] != DEFAULT_DJANGO:
        packages.append(f"django=={ctx['django_pin']}")
    if ctx["use_wagtail"]:
        packages.extend(WAGTAIL_PACKAGES)
    if ctx["use_s3"]:
        packages.extend(S3_PACKAGES)
    if packages:
        run(["uv", "add", "--no-sync", *packages], cwd=root)
    run(["uv", "lock"], cwd=root)


def make_core_migrations(root: Path, ctx: dict) -> None:
    """Wagtail custom Image/Document models need an initial migration.

    It is generated inside the local Docker image so the result matches the
    locked dependencies and no Postgres client library is needed on the host.
    """
    if not ctx["use_wagtail"]:
        return
    compose = ["docker", "compose", "-f", "docker-compose.local.yml"]
    run([*compose, "build", "django"], cwd=root)
    run(
        [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "",
            "django",
            "python",
            "manage.py",
            "makemigrations",
            "core",
        ],
        cwd=root,
    )


def init_git_and_format(root: Path) -> None:
    run(["git", "init", "-q", "-b", "main"], cwd=root)
    run(["git", "add", "-A"], cwd=root)
    # The first pass applies autofixes (import merging, formatting), the second must be clean.
    try:
        run(["uvx", PREK, "run", "--all-files"], cwd=root)
    except subprocess.CalledProcessError:
        run(["git", "add", "-A"], cwd=root)
        run(["uvx", PREK, "run", "--all-files"], cwd=root)
    run(["git", "add", "-A"], cwd=root)


def check_leftovers(root: Path, slug: str) -> None:
    """Fail if references to removed parts survived the patching."""
    patterns = {
        "users:": "users web urls were removed",
        "DJANGO_ADMIN_FORCE_ALLAUTH": "allauth admin redirect was removed",
        "account_login": "allauth urls were removed",
        "DATABASE_URL": "only POSTGRES_* variables are used",
        "pages/home.html": "pages templates were removed",
        'APPS_DIR / "templates"': "templates directory was removed",
        "allauth_settings": "users context processor was removed",
        "users.api": "users API was removed",
        "UserViewSet": "users API was removed",
        "UserSerializer": "users API was removed",
        "get_users_count": "users demo task was removed",
        "pre-commit run": "prek replaces pre-commit",
    }
    problems = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts or path.name == "uv.lock":
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        problems.extend(
            f"{path.relative_to(root)}: {pattern!r} ({reason})"
            for pattern, reason in patterns.items()
            if pattern in text
        )
    if problems:
        raise PostprocessError("Leftovers found:\n  " + "\n  ".join(problems))


def postprocess(root: Path, ctx: dict) -> None:
    slug = ctx["slug"]
    r = Renderer(ctx)
    steps = [
        ("remove unused upstream parts", lambda: drop_unused_upstream_parts(root, slug)),
        ("strip users web layer", lambda: strip_users_web_layer(root, slug)),
        ("strip users api and tasks", lambda: strip_users_api_and_tasks(root, slug, ctx)),
        ("tests layout", lambda: setup_tests(root, slug, ctx, r)),
        ("core app + ping", lambda: add_core_app(root, slug, ctx, r)),
        ("settings and urls", lambda: configure_settings(root, ctx, r)),
        ("env files", lambda: configure_envs(root, ctx)),
        ("docker", lambda: configure_docker(root, ctx, r)),
        ("python version and linters", lambda: configure_python_and_lint(root, ctx, r)),
        ("ci", lambda: configure_ci(root, ctx, r)),
        ("readme", lambda: configure_readme(root, r)),
        ("check leftovers", lambda: check_leftovers(root, slug)),
        ("dependencies (uv lock)", lambda: sync_dependencies(root, ctx)),
        ("wagtail migrations", lambda: make_core_migrations(root, ctx)),
        ("git init + prek autofix", lambda: init_git_and_format(root)),
    ]
    for name, step in steps:
        log(f"step: {name}")
        step()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", type=Path, required=True, help="JSON file with answers")
    parser.add_argument("--output-dir", type=Path, required=True, help="Where the project directory is created")
    args = parser.parse_args()

    answers = load_answers(args.answers)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    project_dir = run_upstream(answers, output_dir)
    ctx = build_context(answers, project_dir)
    try:
        postprocess(project_dir, ctx)
    except (PostprocessError, subprocess.CalledProcessError) as error:
        log(f"FAILED: {error}")
        log(f"The half-processed project is left at {project_dir} for inspection.")
        return 1
    log(f"done: {project_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
