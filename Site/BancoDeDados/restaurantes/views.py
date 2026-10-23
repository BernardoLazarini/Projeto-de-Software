from django.contrib.auth.hashers import make_password, check_password
from django.shortcuts import render, redirect
from .models import Aluno
from django.shortcuts import render, redirect, get_object_or_404

def login(request):
    erro = None
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        aluno = Aluno.objects.filter(username=username).first()
        if aluno and check_password(password, aluno.password):
            request.session["aluno_id"] = aluno.id
            return redirect("listar_usuarios")
        erro = "Usuário ou senha incorretos."
    return render(request, "restaurantes/login.html", {"erro": erro})


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

def listar_usuarios(request):
    alunos = Aluno.objects.all()
    return render(request, "restaurantes/listausuarios.html", {"alunos": alunos})

def editar(request, id):
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
    return render(request, "restaurantes/editarperfil.html", {"aluno": aluno, "erro": erro})


def excluir(request, id):
    aluno = get_object_or_404(Aluno, id=id)
    erro = None
    if request.method == "POST":
        if check_password(request.POST.get("senhaAtual", ""), aluno.password):
            aluno.delete()
            return redirect("listar_usuarios")
        erro = "Senha incorreta."
    return render(request, "restaurantes/excluirconta.html", {"aluno": aluno, "erro": erro})