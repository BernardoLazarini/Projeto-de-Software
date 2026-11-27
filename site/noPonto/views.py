from django.contrib.auth import authenticate, login as auth_login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required as login_obrigatorio
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from .models import Aluno, Avaliacao, Cardapio, EstiloComida, Restaurante
from django.db.models import Avg, Count
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST

def aluno_atual(request):
    """Devolve o Aluno do usuário logado (cria se for, por ex., o admin)."""
    aluno, _ = Aluno.objects.get_or_create(
        user=request.user,
        defaults={"nome": request.user.get_full_name() or request.user.username},
    )
    return aluno

def restaurante_detalhe(request, pk):
    restaurante = get_object_or_404(Restaurante.objects.select_related("estilo"), pk=pk)
    cardapio = Cardapio.objects.filter(restaurante=restaurante).first()
    pratos = cardapio.prato_set.order_by("id") if cardapio else []
    return render(request, "restaurante.html", {
        "restaurante": restaurante,
        "cardapio": cardapio,
        "pratos": pratos,})

# ---------- Login, cadastro e sair ----------

def login(request):
    erro = None
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST["username"],
            password=request.POST["password"],
        )
        if user is not None:
            auth_login(request, user)
            return redirect("restaurantes")
        erro = "Usuário ou senha incorretos."
    return render(request, "login.html", {"erro": erro})


def sair(request):
    logout(request)
    return redirect("login")


def cadastrar(request):
    erro = None
    if request.method == "POST":
        email = request.POST["email"]
        senha = request.POST["senha"]
        if senha != request.POST["confirmarSenha"]:
            erro = "As senhas não coincidem."
        elif (
            User.objects.filter(username=email).exists()
            or Aluno.objects.filter(username=email).exists()
        ):
            erro = "Esse e-mail já está cadastrado."
        else:
            with transaction.atomic():
                user = User.objects.create_user(username=email, email=email, password=senha)
                Aluno.objects.create(
                    user=user,
                    nome=request.POST["nome"],
                    username=email,
                )
            return redirect("login")
    return render(request, "cadastro.html", {"erro": erro})


@login_obrigatorio
def listar_usuarios(request):
    return render(request, "listausuarios.html", {
        "alunos": Aluno.objects.select_related("user"),
        "meu_id": aluno_atual(request).id,
    })


@login_obrigatorio
def editar(request, id):
    aluno = aluno_atual(request)
    if aluno.id != id:
        return HttpResponseForbidden("Você só pode editar a sua própria conta.")
    erro = None
    if request.method == "POST":
        email = request.POST["email"]
        nova_senha = request.POST.get("senha", "")
        if User.objects.filter(username=email).exclude(id=aluno.user_id).exists():
            erro = "Esse e-mail já está cadastrado."
        elif nova_senha and nova_senha != request.POST.get("confirmarSenha", ""):
            erro = "As senhas não coincidem."
        else:
            aluno.nome = request.POST["nome"]
            aluno.save()
            user = aluno.user
            user.username = email
            user.email = email
            if nova_senha:
                user.set_password(nova_senha)
            user.save()
            if nova_senha:
                update_session_auth_hash(request, user)  # mantém logado após trocar a senha
            return redirect("listar_usuarios")
    return render(request, "editar.html", {"aluno": aluno, "erro": erro})


@login_obrigatorio
def excluir(request, id):
    aluno = aluno_atual(request)
    if aluno.id != id:
        return HttpResponseForbidden("Você só pode excluir a sua própria conta.")
    erro = None
    if request.method == "POST":
        if aluno.user.check_password(request.POST.get("senhaAtual", "")):
            user = aluno.user
            logout(request)
            user.delete()  # apaga o Aluno junto (CASCADE)
            return redirect("login")
        erro = "Senha incorreta."
    return render(request, "excluir.html", {"aluno": aluno, "erro": erro})


# ---------- Usuários (editar e excluir só a própria conta) ----------
def aluno_atual(request):
    """Devolve o Aluno do usuário logado (cria se for, por ex., o admin)."""
    aluno, _ = Aluno.objects.get_or_create(
        user=request.user,
        defaults={"nome": request.user.get_full_name() or request.user.username},
    )
    return aluno




# ---------- Restaurantes ----------

@login_required
def listar_restaurantes(request):
    aluno = getattr(request.user, "aluno", None)

    restaurantes = list(
        Restaurante.objects.select_related("estilo", "cardapio")
        .prefetch_related("cardapio__prato_set")
        .annotate(media=Avg("avaliacao__estrela"), total=Count("avaliacao"))
        .order_by("nome")
    )

    ids_favoritos = set()
    minhas = {}
    if aluno:
        ids_favoritos = set(
            aluno.restaurantes_favoritos.values_list("id", flat=True)
        )
        minhas = dict(
            Avaliacao.objects.filter(aluno=aluno)
            .values_list("restaurante_id", "estrela")
        )

    for r in restaurantes:
        r.pct = round((r.media or 0) / 5 * 100)
        r.minha = minhas.get(r.id, 0)
        r.favorito = r.id in ids_favoritos

    restaurantes = sorted(restaurantes, key=lambda r: not r.favorito)  # favoritos primeiro

    return render(request, "restaurantes.html", {
        "restaurantes": restaurantes,
        "estilos": EstiloComida.objects.all().order_by("nome"),
        "aluno": aluno,
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
                aluno=aluno_atual(request),
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

@login_obrigatorio
def mapa(request):
    restaurantes = list(
        Restaurante.objects.select_related("estilo")
        .filter(latitude__isnull=False, longitude__isnull=False)
        .annotate(media=Avg("avaliacao__estrela"), total=Count("avaliacao"))
        .order_by("nome")
    )
    for r in restaurantes:
        r.media_int = int((r.media or 0) + 0.5)

    pontos = [
        {
            "nome": r.nome,
            "localizacao": r.localizacao,
            "lat": r.latitude,
            "lng": r.longitude,
            "url": reverse("detalhe_restaurante", args=[r.id]),
        }
        for r in restaurantes
    ]

    return render(request, "mapa.html", {
        "restaurantes": restaurantes,
        "pontos": pontos,
    })

@login_obrigatorio
def listar_restaurantes(request):
    restaurantes = list(
        Restaurante.objects.select_related("estilo", "cardapio")
        .prefetch_related("cardapio__prato_set")
        .annotate(media=Avg("avaliacao__estrela"), total=Count("avaliacao"))
        .order_by("nome")
    )
    aluno = aluno_atual(request)
    minhas = dict(
        Avaliacao.objects.filter(aluno=aluno)
        .order_by("id")
        .values_list("restaurante_id", "estrela")
    )
    for r in restaurantes:
        r.pct = round((r.media or 0) / 5 * 100)
        r.minha = minhas.get(r.id, 0)

    return render(request, "restaurantes.html", {
        "restaurantes": restaurantes,
        "estilos": EstiloComida.objects.all().order_by("nome"),
        "aluno": aluno,
    })
@login_obrigatorio
def avaliacoes(request):
    lista_avaliacoes = (
        Avaliacao.objects.select_related("aluno", "restaurante")
        .order_by("-id")
    )
    resumo = lista_avaliacoes.aggregate(media=Avg("estrela"), total=Count("id"))

    restaurantes_qs = (
        Restaurante.objects.select_related("estilo")
        .prefetch_related("avaliacao_set")
        .annotate(
            media=Avg("avaliacao__estrela"),
            total=Count("avaliacao"),
        )
        .order_by("-media", "-total", "nome")
    )

    return render(request, "avaliacoes.html", {
        "restaurantes": restaurantes_qs,
        "avaliacoes": lista_avaliacoes,
        "media": resumo["media"] or 0,
        "total": resumo["total"],
    })
def termo_de_uso(request):
    return render(request, "termodeuso.html")

def politica_de_privacidade(request):
    return render(request, "politicadeprivacidade.html")

def por_que_fizemos(request):
    return render(request, "porquefizemos.html")

@login_obrigatorio
def perfil(request):
    aluno = aluno_atual(request)
    avaliacoes = aluno.avaliacao_set.select_related("restaurante").order_by("-id")
    return render(request, "perfil.html", {
        "aluno": aluno,
        "estilos": aluno.estilos_favoritos.all(),
        "avaliacoes": avaliacoes,
    })

@login_obrigatorio
@require_POST
def avaliar(request, id):
    restaurante = get_object_or_404(Restaurante, id=id)
    try:
        estrelas = int(request.POST.get("estrelas", ""))
    except ValueError:
        estrelas = 0
    if estrelas < 1 or estrelas > 5:
        return JsonResponse({"erro": "Nota inválida."}, status=400)

    aluno = aluno_atual(request)
    # Se o aluno já avaliou este restaurante, atualiza a nota em vez de duplicar
    avaliacao = Avaliacao.objects.filter(aluno=aluno, restaurante=restaurante).order_by("id").first()
    if avaliacao:
        avaliacao.estrela = estrelas
        avaliacao.save(update_fields=["estrela"])
    else:
        Avaliacao.objects.create(aluno=aluno, restaurante=restaurante, estrela=estrelas)

    resumo = Avaliacao.objects.filter(restaurante=restaurante).aggregate(
        media=Avg("estrela"), total=Count("id")
    )
    media = resumo["media"] or 0
    return JsonResponse({
        "minha": estrelas,
        "media": round(media, 1),
        "total": resumo["total"],
        "pct": round(media / 5 * 100),
    })

@require_POST
def favoritar(request, id):
    if not request.user.is_authenticated:
        return JsonResponse({"erro": "login"}, status=401)

    aluno = request.user.aluno
    restaurante = get_object_or_404(Restaurante, id=id)

    if aluno.restaurantes_favoritos.filter(id=id).exists():
        aluno.restaurantes_favoritos.remove(restaurante)
        favorito = False
    else:
        aluno.restaurantes_favoritos.add(restaurante)
        favorito = True

    return JsonResponse({"favorito": favorito})    