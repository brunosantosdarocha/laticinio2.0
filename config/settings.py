"""
config/settings.py
==================
Configurações gerais do sistema do Laticínio.

Aqui ficam:
- as chaves secretas e opções lidas do arquivo .env (nunca coloque senhas no código!);
- a lista de apps instalados;
- os middlewares (as "camadas" por onde cada requisição passa);
- as regras de segurança (login obrigatório, bloqueio de senha errada, cookies, HTTPS);
- idioma, fuso horário, arquivos estáticos e logs.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Pasta raiz do projeto (onde fica o manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# Lê o arquivo .env (criado automaticamente pelo iniciar.py).
load_dotenv(BASE_DIR / ".env")


def env_bool(nome, padrao=False):
    """Lê uma variável do .env e converte 'True/1/sim' em booleano."""
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


def env_lista(nome, padrao=""):
    """Lê uma lista separada por vírgulas do .env (ex.: 'a.com,b.com')."""
    return [item.strip() for item in os.getenv(nome, padrao).split(",") if item.strip()]


# O Vercel define a variável VERCEL=1. Lá não existe o arquivo .env (as variáveis
# são cadastradas no painel do Vercel) e o disco é somente leitura, exceto /tmp.
NA_VERCEL = bool(os.getenv("VERCEL"))


# ------------------------------------------------------------------------------
# Segurança básica
# ------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "A variável SECRET_KEY não foi encontrada. No computador, rode 'python iniciar.py' "
        "para criar o .env. No Vercel, cadastre SECRET_KEY em Settings > Environment Variables."
    )

# DEBUG começa DESLIGADO. Só ligue no .env enquanto estiver programando.
DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS", "127.0.0.1,localhost")

# Endereços confiáveis para formulários quando usar domínio próprio (ex.: https://leite.meusite.com).
CSRF_TRUSTED_ORIGINS = env_lista("CSRF_TRUSTED_ORIGINS", "")

if NA_VERCEL:
    # Libera os endereços *.vercel.app que o Vercel cria para o projeto.
    ALLOWED_HOSTS.append(".vercel.app")
    for variavel in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        if os.getenv(variavel):
            CSRF_TRUSTED_ORIGINS.append("https://" + os.getenv(variavel))

# Endereço do painel /admin do Django. Mudamos o padrão para dificultar ataques automáticos.
ADMIN_URL = os.getenv("ADMIN_URL", "gestao-interna/").strip("/") + "/"

# Quando True, o comando "servidor" aceita acessos de outros aparelhos da rede (celular, outro PC).
ACESSO_REDE = env_bool("ACESSO_REDE", False)

# ------------------------------------------------------------------------------
# Apps
# ------------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Bloqueio de tentativas de login (força bruta)
    "axes",
    # Apps do sistema
    "core",
    "contas",
    "leite",
    "financeiro",
    "backup",
]

# A ORDEM IMPORTA: cada requisição passa por estes middlewares de cima para baixo.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Exige login em TODAS as páginas (exceto as marcadas com @login_not_required).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Obriga a trocar a senha provisória antes de usar o sistema.
    "contas.middleware.forcar_troca_de_senha",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Deve ser o último: transforma o bloqueio do axes em resposta 429.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.sistema",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ------------------------------------------------------------------------------
# Banco de dados (SQLite: um arquivo só, ótimo para começar).
# Para crescer, troque por PostgreSQL (veja o README).
# ------------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

# Se DATABASE_URL existir (ex.: PostgreSQL do Neon/Vercel), ele substitui o SQLite.
# No Vercel isso é OBRIGATÓRIO: o disco de lá é somente leitura e os dados se perdem.
if os.getenv("DATABASE_URL"):
    import dj_database_url

    DATABASES["default"] = dj_database_url.parse(
        os.environ["DATABASE_URL"], conn_max_age=60, conn_health_checks=True, ssl_require=NA_VERCEL
    )

# ------------------------------------------------------------------------------
# Login e senhas
# ------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # precisa ser o primeiro
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "contas:login"
LOGIN_REDIRECT_URL = "core:inicio"
LOGOUT_REDIRECT_URL = "contas:login"

# django-axes: 5 senhas erradas seguidas bloqueiam usuário + IP por 15 minutos.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "contas/bloqueado.html"

# Sessão: dura 2 horas, renova a cada clique e acaba ao fechar o navegador.
SESSION_COOKIE_AGE = 60 * 60 * 2
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Cabeçalhos de proteção do navegador.
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Ligue USAR_HTTPS=True no .env quando o sistema estiver na internet com certificado (https).
USAR_HTTPS = env_bool("USAR_HTTPS", False)
if USAR_HTTPS:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Necessário atrás de proxy (Nginx da VPS) que repassa o https.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ------------------------------------------------------------------------------
# Idioma, fuso e formatos
# ------------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
# False para o ano não aparecer como "2.026". Para milhar use o filtro |intcomma.
USE_THOUSAND_SEPARATOR = False

# ------------------------------------------------------------------------------
# Arquivos estáticos (CSS, JS, ícones) servidos pelo WhiteNoise
# ------------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# No Vercel, o WhiteNoise serve direto da pasta "static" (não depende do collectstatic).
WHITENOISE_USE_FINDERS = NA_VERCEL

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------------------
# Coleta offline (celular do coletor)
# ------------------------------------------------------------------------------
# Quantos dias para trás um lançamento feito sem internet ainda é aceito.
COLETA_OFFLINE_DIAS = int(os.getenv("COLETA_OFFLINE_DIAS", "7"))
# Sessão do coletor dura mais (o celular pode ficar dias sem internet).
COLETOR_SESSAO_DIAS = int(os.getenv("COLETOR_SESSAO_DIAS", "30"))
# Máximo de lançamentos aceitos em um único envio da fila.
COLETA_OFFLINE_MAX_ITENS = 200

# Pasta onde os backups .zip são guardados.
PASTA_TEMPORARIA = Path("/tmp") if NA_VERCEL else BASE_DIR
PASTA_BACKUPS = PASTA_TEMPORARIA / "backups"
BACKUPS_MANTIDOS = 10

# E-mail: as credenciais SMTP são configuradas pela tela de Backup (ficam criptografadas no banco).
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_TIMEOUT = 20

# ------------------------------------------------------------------------------
# Logs de segurança (logs/seguranca.log, com rotação automática)
# ------------------------------------------------------------------------------
PASTA_LOGS = PASTA_TEMPORARIA / "logs"
PASTA_LOGS.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detalhado": {"format": "{asctime} [{levelname}] {name}: {message}", "style": "{"},
    },
    "handlers": {
        "arquivo_seguranca": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": PASTA_LOGS / "seguranca.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "detalhado",
        },
        "console": {"class": "logging.StreamHandler", "level": "WARNING", "formatter": "detalhado"},
    },
    "loggers": {
        "axes": {"handlers": ["arquivo_seguranca", "console"], "level": "INFO", "propagate": False},
        "django.security": {"handlers": ["arquivo_seguranca", "console"], "level": "INFO", "propagate": False},
        "laticinio": {"handlers": ["arquivo_seguranca", "console"], "level": "INFO", "propagate": False},
    },
}
