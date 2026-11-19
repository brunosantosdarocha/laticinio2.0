"""
backup/agendador.py
===================
Agendador simples: uma thread "daemon" que acorda a cada 60 segundos e
pergunta se está na hora do backup (servicos.executar_agendado).
É iniciado pelo comando "servidor" (python iniciar.py).
"""

import logging
import threading
import time

from django.db import close_old_connections

logger = logging.getLogger("laticinio")
_iniciado = False


def _laco(intervalo):
    from . import servicos  # importa aqui para o Django já estar carregado

    while True:
        try:
            close_old_connections()
            registro = servicos.executar_agendado()
            if registro is not None:
                logger.warning("Backup automático: %s", registro.mensagem)
        except Exception:  # o agendador nunca pode derrubar o sistema
            logger.exception("Erro no agendador de backup")
        finally:
            close_old_connections()
        time.sleep(intervalo)


def iniciar_agendador(intervalo=60):
    """Liga a thread uma única vez."""
    global _iniciado
    if _iniciado:
        return
    _iniciado = True
    threading.Thread(target=_laco, args=(intervalo,), name="agendador-backup", daemon=True).start()
