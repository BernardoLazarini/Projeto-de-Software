from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from .decorators import login_obrigatorio
from .models import Aluno, Avaliacao, Cardapio, EstiloComida, Restaurante


# ---------- Login, cadastro e sair ----------

def login(request):
    erro = None
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        aluno = Aluno.objects.filter(username=username).first()
        if aluno and check_password(password, aluno.password):
            request.session["aluno_id"] = aluno.id
            return redirect("restaurantes")
        erro = "Usuário ou senha incorretos."
    return render(request, "restaurantes/login.html", {"erro": erro})


def sair(request):
    request.session.flush()
    return redirect("login")


def cadastrar(request):
    erro = None
    if request.method == "POST":
        email = request.POST["email"]
        senha = request.POST["senha"]
        if senha != request.POST["confirmarSenha"]:
            erro = "As senhas não coincidem."
        elif Aluno.objects.filter(username=email).exists():
            erro = "Esse e-mail já está cadastrado."
        else:
            Aluno.objects.create(
                nome=request.POST["nome"],
                username=email,
                password=make_password(senha),
            )
            return redirect("login")
    return render(request, "restaurantes/cadastro.html", {"erro": erro})


# ---------- Usuários (editar e excluir só a própria conta) ----------

@login_obrigatorio
def listar_usuarios(request):
    alunos = Aluno.objects.all()
    return render(request, "restaurantes/listausuarios.html", {
        "alunos": alunos,
        "meu_id": request.session["aluno_id"],
    })


@login_obrigatorio
def editar(request, id):
    if request.session["aluno_id"] != id:
        return HttpResponseForbidden("Você só pode editar a sua própria conta.")
    aluno = get_object_or_404(Aluno, id=id)
    erro = None
    if request.method == "POST":
        email = request.POST["email"]
        nova_senha = request.POST.get("senha", "")
        if Aluno.objects.filter(username=email).exclude(id=aluno.id).exists():
            erro = "Esse e-mail já está cadastrado."
        elif nova_senha and nova_senha != request.POST.get("confirmarSenha", ""):
            erro = "As senhas não coincidem."
        else:
            aluno.nome = request.POST["nome"]
            aluno.username = email
            if nova_senha:
                aluno.password = make_password(nova_senha)
            aluno.save()
            return redirect("listar_usuarios")
    return render(request, "restaurantes/editar.html", {"aluno": aluno, "erro": erro})


@login_obrigatorio
def excluir(request, id):
    if request.session["aluno_id"] != id:
        return HttpResponseForbidden("Você só pode excluir a sua própria conta.")
    aluno = get_object_or_404(Aluno, id=id)
    erro = None
    if request.method == "POST":
        if check_password(request.POST.get("senhaAtual", ""), aluno.password):
            aluno.delete()
            request.session.flush()
            return redirect("login")
        erro = "Senha incorreta."
    return render(request, "restaurantes/excluir.html", {"aluno": aluno, "erro": erro})


# ---------- Restaurantes ----------

@login_obrigatorio
def listar_restaurantes(request):
    restaurantes = Restaurante.objects.select_related("estilo").annotate(
        media=Avg("avaliacao__estrela"),
        total=Count("avaliacao"),
    )

    busca = request.GET.get("q", "").strip()
    estilo_id = request.GET.get("estilo", "")
    if busca:
        restaurantes = restaurantes.filter(nome__icontains=busca)
    if estilo_id:
        restaurantes = restaurantes.filter(estilo_id=estilo_id)

    restaurantes = list(restaurantes.order_by("nome"))
    for r in restaurantes:
        r.media_int = int((r.media or 0) + 0.5)  # nota arredondada, para as estrelas

    return render(request, "restaurantes/restaurantes.html", {
        "restaurantes": restaurantes,
        "estilos": EstiloComida.objects.all(),
        "busca": busca,
        "estilo_id": estilo_id,
    })


@login_obrigatorio
def detalhe_restaurante(request, id):
    restaurante = get_object_or_404(Restaurante, id=id)
    erro = None

    if request.method == "POST":
        try:
            estrelas = int(request.POST.get("estrelas", ""))
        except ValueError:
            estrelas = 0
        if estrelas < 1 or estrelas > 5:
            erro = "Escolha uma nota de 1 a 5."
        else:
            Avaliacao.objects.create(
                estrela=estrelas,
                comentario=request.POST.get("comentario", "").strip(),
                aluno_id=request.session["aluno_id"],
                restaurante=restaurante,
            )
            return redirect("detalhe_restaurante", id=restaurante.id)

    cardapio = Cardapio.objects.filter(restaurante=restaurante).first()
    pratos = cardapio.prato_set.all() if cardapio else []
    avaliacoes = restaurante.avaliacao_set.select_related("aluno").order_by("-id")
    resumo = avaliacoes.aggregate(media=Avg("estrela"), total=Count("id"))
    media = resumo["media"] or 0

    return render(request, "restaurante.html", {
        "restaurante": restaurante,
        "pratos": pratos,
        "avaliacoes": avaliacoes,
        "media": media,
        "media_int": int(media + 0.5),
        "total": resumo["total"],
        "erro": erro,
    })