"""
contas/decoradores.py
=====================
@somente_administrador: libera a view apenas para superusuários (Administrador).
Usado nas telas de usuários e níveis de acesso.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied


def somente_administrador(view):
    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_superuser):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida
