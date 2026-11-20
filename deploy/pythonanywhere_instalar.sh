#!/usr/bin/env bash
# =============================================================================
# deploy/pythonanywhere_instalar.sh
# Instala OU atualiza o sistema no PythonAnywhere. Rode num console Bash:
#
#     cd ~/laticinio2.0 && bash deploy/pythonanywhere_instalar.sh
#
# Conta na Europa (eu.pythonanywhere.com)? Informe o endereço:
#     bash deploy/pythonanywhere_instalar.sh SEUUSUARIO.eu.pythonanywhere.com
#
# Pode rodar quantas vezes quiser: não apaga o banco nem troca a SECRET_KEY.
# =============================================================================
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
DOMINIO="${1:-${USER}.pythonanywhere.com}"
cd "$PASTA"

echo "==> Pasta do projeto: $PASTA"
echo "==> Endereço do site: https://$DOMINIO"

# 1. Python: usa o mais novo disponível (3.10 ou superior).
if [ ! -x .venv/bin/python ]; then
    PYTHON=""
    for versao in 3.13 3.12 3.11 3.10; do
        if command -v "python$versao" >/dev/null 2>&1; then PYTHON="python$versao"; break; fi
    done
    if [ -z "$PYTHON" ]; then echo "[ERRO] Nenhum Python 3.10+ encontrado."; exit 1; fi
    echo "==> Criando o ambiente virtual com $PYTHON"
    "$PYTHON" -m venv .venv
fi
PY="$PASTA/.venv/bin/python"

# 2. Dependências.
echo "==> Instalando dependências (demora alguns minutos na primeira vez)"
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -r requirements.txt -q

# 3. Arquivo .env (só na primeira vez).
if [ ! -f .env ]; then
    echo "==> Criando o .env com uma chave secreta nova"
    SECRET=$("$PY" -c "import secrets; print(secrets.token_urlsafe(50))")
    ADMIN=$("$PY" -c "import secrets; print('gestao-' + secrets.token_hex(4))")
    cat > .env <<EOF
# Configurações do sistema no PythonAnywhere. NÃO compartilhe este arquivo!
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$DOMINIO
CSRF_TRUSTED_ORIGINS=https://$DOMINIO
ADMIN_URL=$ADMIN/
ACESSO_REDE=False
USAR_HTTPS=True
EOF
    chmod 600 .env
fi

# 4. Banco, níveis de acesso, admin e arquivos estáticos.
echo "==> Preparando o banco de dados"
"$PY" manage.py migrate --noinput -v 0
"$PY" manage.py configurar_grupos
"$PY" manage.py criar_admin_inicial --senha-aleatoria
"$PY" manage.py collectstatic --noinput -v 0
"$PY" manage.py check --deploy --fail-level ERROR

# 5. Recarrega o site (o PythonAnywhere reinicia ao "tocar" o arquivo WSGI).
WSGI="/var/www/$(echo "$DOMINIO" | tr '.' '_')_wsgi.py"
if [ -f "$WSGI" ] && grep -q "config.wsgi" "$WSGI"; then
    touch "$WSGI"
    echo "==> Site recarregado."
fi

cat <<EOF

=============================================================================
 Pronto! Se é a PRIMEIRA instalação, configure a aba "Web" do PythonAnywhere:
   Source code ......: $PASTA
   Working directory : $PASTA
   Virtualenv .......: $PASTA/.venv
   Python version ...: $("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
   WSGI file ........: cole o conteúdo de deploy/pythonanywhere_wsgi.py
   Static files .....: URL /static/  ->  $PASTA/staticfiles
   Force HTTPS ......: Enabled
 Depois clique em "Reload".
=============================================================================
EOF
