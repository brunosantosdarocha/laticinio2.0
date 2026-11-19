"""
iniciar.py
==========
UM comando para ligar o sistema:   python iniciar.py

O que ele faz (só usa a biblioteca padrão do Python):
1. confere se o Python é 3.10 ou mais novo;
2. cria o ambiente virtual .venv (na primeira vez) e se executa de novo dentro dele;
3. instala as dependências só quando o requirements.txt muda;
4. cria o arquivo .env com uma SECRET_KEY aleatória (na primeira vez);
5. prepara o banco (migrate), os níveis de acesso, o admin inicial e os arquivos estáticos;
6. liga o servidor e abre o navegador.

Opções:  --porta 8080   --sem-navegador   --rede (acesso pelo celular/outros PCs)
"""

import hashlib
import os
import secrets
import subprocess
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
VENV = PASTA / ".venv"
REQUISITOS = PASTA / "requirements.txt"
CARIMBO = VENV / ".requisitos.sha256"
ENV = PASTA / ".env"


def python_do_venv():
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def rodar(*argumentos):
    """Executa um comando e para tudo se der erro."""
    resultado = subprocess.run(list(argumentos), cwd=PASTA)
    if resultado.returncode != 0:
        print(f"\n[ERRO] O comando falhou: {' '.join(str(a) for a in argumentos)}")
        sys.exit(resultado.returncode)


def dentro_do_venv():
    return Path(sys.prefix).resolve() == VENV.resolve()


def passo(texto):
    print(f"\n==> {texto}")


def main():
    # 1. Versão do Python
    if sys.version_info < (3, 10):
        print("É preciso Python 3.10 ou mais novo. Baixe em https://www.python.org/downloads/")
        sys.exit(1)

    # 2. Ambiente virtual
    if not dentro_do_venv():
        if not python_do_venv().exists():
            passo("Criando o ambiente virtual (.venv) - só na primeira vez")
            rodar(sys.executable, "-m", "venv", str(VENV))
        # Executa este mesmo arquivo de novo, agora com o Python do .venv
        resultado = subprocess.run([str(python_do_venv()), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=PASTA)
        sys.exit(resultado.returncode)

    # 3. Dependências (só quando o requirements.txt muda)
    hash_atual = hashlib.sha256(REQUISITOS.read_bytes()).hexdigest()
    if not CARIMBO.exists() or CARIMBO.read_text().strip() != hash_atual:
        passo("Instalando as dependências (pode demorar alguns minutos na primeira vez)")
        rodar(sys.executable, "-m", "pip", "install", "--upgrade", "pip", "-q")
        rodar(sys.executable, "-m", "pip", "install", "-r", str(REQUISITOS), "-q")
        CARIMBO.write_text(hash_atual)

    # 4. Arquivo .env
    if not ENV.exists():
        passo("Criando o arquivo .env com uma chave secreta nova")
        ENV.write_text(
            "# Configurações do sistema. NÃO compartilhe este arquivo!\n"
            f"SECRET_KEY={secrets.token_urlsafe(50)}\n"
            "DEBUG=False\n"
            "ALLOWED_HOSTS=127.0.0.1,localhost\n"
            f"ADMIN_URL=gestao-{secrets.token_hex(4)}/\n"
            "ACESSO_REDE=False\n"
            "USAR_HTTPS=False\n",
            encoding="utf-8",
        )

    # 5. Banco, níveis, admin e estáticos
    manage = [sys.executable, "manage.py"]
    passo("Preparando o banco de dados")
    rodar(*manage, "migrate", "--noinput", "-v", "0")
    rodar(*manage, "configurar_grupos")
    rodar(*manage, "criar_admin_inicial")
    rodar(*manage, "collectstatic", "--noinput", "-v", "0")

    # 6. Servidor
    opcoes = sys.argv[1:]
    if "--rede" in opcoes:
        opcoes.remove("--rede")
        os.environ["ACESSO_REDE"] = "True"
    passo("Ligando o sistema")
    rodar(*manage, "servidor", *opcoes)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSistema desligado.")
