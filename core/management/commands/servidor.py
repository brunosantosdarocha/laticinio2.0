"""
Comando: python manage.py servidor [--porta 8000] [--sem-navegador]

Liga o sistema "de verdade" (sem o runserver de desenvolvimento):
- servidor Waitress com 8 threads (estável no Windows);
- agendador do backup automático;
- abre o navegador na página inicial.

Com ACESSO_REDE=True no .env, aceita conexões de outros aparelhos da rede
(celular do coletor, outro computador) e mostra o endereço para digitar.
"""

import socket
import threading
import webbrowser

from django.conf import settings
from django.core.management.base import BaseCommand

from backup.agendador import iniciar_agendador


def ips_da_maquina():
    """Descobre os IPs locais (ex.: 192.168.0.10) para acesso pela rede."""
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # não envia nada, só descobre a interface de saída
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


class Command(BaseCommand):
    help = "Inicia o sistema com o servidor Waitress e o agendador de backup."

    def add_arguments(self, parser):
        parser.add_argument("--porta", type=int, default=8000)
        parser.add_argument("--sem-navegador", action="store_true")

    def handle(self, *args, **options):
        from waitress import serve

        from config.wsgi import application

        porta = options["porta"]
        host = "127.0.0.1"
        if settings.ACESSO_REDE:
            host = "0.0.0.0"
            ips = ips_da_maquina()
            # Libera só os IPs desta máquina (nunca "*").
            for ip in ips:
                if ip not in settings.ALLOWED_HOSTS:
                    settings.ALLOWED_HOSTS.append(ip)
            for ip in ips:
                self.stdout.write(self.style.SUCCESS(f"Acesso pela rede: http://{ip}:{porta}"))

        iniciar_agendador()
        endereco = f"http://127.0.0.1:{porta}"
        self.stdout.write(self.style.SUCCESS(f"Sistema no ar em {endereco}  (para desligar: Ctrl+C)"))
        if not options["sem_navegador"]:
            threading.Timer(1.5, lambda: webbrowser.open(endereco)).start()
        serve(application, host=host, port=porta, threads=8)
