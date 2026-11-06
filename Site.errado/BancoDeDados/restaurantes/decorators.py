from functools import wraps
from django.shortcuts import redirect
from .models import Aluno


def login_obrigatorio(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        aluno_id = request.session.get("aluno_id")
        if not aluno_id or not Aluno.objects.filter(id=aluno_id).exists():
            request.session.flush()
            return redirect("login")
        return view(request, *args, **kwargs)
    return wrapper

