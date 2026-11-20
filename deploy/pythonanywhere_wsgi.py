# =============================================================================
# Arquivo WSGI para o PythonAnywhere.
#
# Na aba "Web", clique no link do "WSGI configuration file"
# (/var/www/SEUUSUARIO_pythonanywhere_com_wsgi.py), APAGUE tudo o que estiver lá
# e cole este conteúdo. Troque SEUUSUARIO pelo seu usuário do PythonAnywhere.
# =============================================================================
import os
import sys

PASTA = "/home/SEUUSUARIO/laticinio2.0"

if PASTA not in sys.path:
    sys.path.insert(0, PASTA)
os.chdir(PASTA)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
