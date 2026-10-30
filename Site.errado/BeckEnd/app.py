"""
noPonto — backend de autenticação.

Cadastro, login, logout, edição de perfil e exclusão de conta.
Stack: Flask + SQLite (biblioteca padrão do Python). Não há outras dependências.

Como rodar (a partir da pasta Backend):
    pip install -r requirements.txt
    python app.py
Depois abra http://127.0.0.1:5000

O servidor também entrega as páginas da pasta Site/, então o site e a API ficam
na mesma origem (sem CORS) e o cookie de sessão funciona sem configuração extra.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    send_from_directory,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
SITE_DIR = BASE_DIR.parent / "Site"

# Mesmas opções do <select> da tela de cadastro.
CURSOS = [
    "Engenharia",
    "Administração",
    "Direito",
    "Design",
    "Comunicação Social",
    "Psicologia",
    "Outro",
]

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MATRICULA_RE = re.compile(r"^[A-Za-z0-9]{0,20}$")
SENHA_MIN, SENHA_MAX = 8, 128
FOTO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    curso      TEXT NOT NULL,
    matricula  TEXT,
    senha_hash TEXT NOT NULL,
    foto       TEXT,
    criado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# --------------------------------------------------------------------------
# Erros da API
# --------------------------------------------------------------------------

class ErroApi(Exception):
    """Erro previsto da API: vira uma resposta JSON {"erro": ..., "campo": ...}."""

    def __init__(self, mensagem: str, status: int = 400, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.campo = campo


def resposta_erro(mensagem: str, status: int, campo: str | None = None):
    return jsonify({"erro": mensagem, "campo": campo}), status


# --------------------------------------------------------------------------
# Limite de tentativas de senha (em memória, por processo)
# --------------------------------------------------------------------------

class LimitadorTentativas:
    """Bloqueia uma chave depois de N falhas dentro de uma janela de tempo."""

    def __init__(self, max_tentativas: int, janela_segundos: int):
        self.max_tentativas = max_tentativas
        self.janela = janela_segundos
        self._falhas: dict = defaultdict(deque)

    def _limpar_antigas(self, chave) -> deque:
        falhas = self._falhas[chave]
        agora = time.monotonic()
        while falhas and agora - falhas[0] > self.janela:
            falhas.popleft()
        if not falhas:
            self._falhas.pop(chave, None)
        return falhas

    def restante(self, chave) -> int:
        """Segundos até a chave ser liberada (0 se não está bloqueada)."""
        falhas = self._limpar_antigas(chave)
        if len(falhas) < self.max_tentativas:
            return 0
        return max(1, int(self.janela - (time.monotonic() - falhas[0])))

    def registrar(self, chave) -> None:
        self._falhas[chave].append(time.monotonic())

    def limpar(self, chave) -> None:
        self._falhas.pop(chave, None)


def mensagem_bloqueio(segundos: int) -> str:
    minutos = max(1, -(-segundos // 60))
    return f"Muitas tentativas. Tente novamente em {minutos} min."


# --------------------------------------------------------------------------
# Banco de dados
# --------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


# --------------------------------------------------------------------------
# Validação (sempre no servidor: o navegador não é confiável)
# --------------------------------------------------------------------------

def texto(valor) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def validar_nome(valor) -> str:
    nome = texto(valor)
    if not 3 <= len(nome) <= 100:
        raise ErroApi("Informe seu nome completo (3 a 100 caracteres).", 400, "nome")
    return nome


def validar_email(valor) -> str:
    email = texto(valor).lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ErroApi("Informe um e-mail válido.", 400, "email")
    dominio = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    if dominio and not email.endswith("@" + dominio.lower().lstrip("@")):
        raise ErroApi(f"Use seu e-mail institucional (@{dominio.lstrip('@')}).", 400, "email")
    return email


def validar_curso(valor) -> str:
    curso = texto(valor)
    if curso not in CURSOS:
        raise ErroApi("Selecione um curso da lista.", 400, "curso")
    return curso


def validar_matricula(valor) -> str | None:
    matricula = texto(valor)
    if not MATRICULA_RE.match(matricula):
        raise ErroApi("A matrícula deve ter só letras e números (até 20 caracteres).", 400, "matricula")
    return matricula or None


def validar_senha(valor, campo: str = "senha") -> str:
    if not isinstance(valor, str) or not SENHA_MIN <= len(valor) <= SENHA_MAX:
        raise ErroApi(f"A senha deve ter entre {SENHA_MIN} e {SENHA_MAX} caracteres.", 400, campo)
    return valor


def tipo_imagem(dados: bytes) -> str | None:
    """Descobre o tipo pelo conteúdo do arquivo, não pelo nome ou pelo Content-Type."""
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


def validar_foto(arquivo) -> tuple[str, bytes]:
    dados = arquivo.read(FOTO_MAX_BYTES + 1)
    if len(dados) > FOTO_MAX_BYTES:
        raise ErroApi("A imagem é grande demais. O limite é 2 MB.", 413, "foto")
    extensao = tipo_imagem(dados)
    if not extensao:
        raise ErroApi("Formato não aceito. Use uma imagem JPG, PNG ou WebP.", 400, "foto")
    return extensao, dados


def gravar_foto(extensao: str, dados: bytes) -> str:
    nome = f"{uuid.uuid4().hex}.{extensao}"
    (Path(current_app.config["UPLOAD_DIR"]) / nome).write_bytes(dados)
    return nome


def apagar_foto(nome: str | None) -> None:
    if not nome:
        return
    pasta = Path(current_app.config["UPLOAD_DIR"]).resolve()
    caminho = (pasta / nome).resolve()
    if caminho.parent == pasta:  # nunca apaga nada fora da pasta de uploads
        caminho.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Utilidades de requisição
# --------------------------------------------------------------------------

def dados_requisicao():
    """Aceita JSON (cadastro, login, exclusão) ou multipart (edição com foto)."""
    if request.is_json:
        dados = request.get_json(silent=True)
        return dados if isinstance(dados, dict) else {}
    return request.form


def usuario_publico(row: sqlite3.Row) -> dict:
    """Só devolve para o navegador o que ele pode ver. Nunca o hash da senha."""
    return {
        "id": row["id"],
        "nome": row["nome"],
        "email": row["email"],
        "curso": row["curso"],
        "matricula": row["matricula"] or "",
        "fotoUrl": f"/uploads/{row['foto']}" if row["foto"] else None,
        "criadoEm": row["criado_em"],
    }


def login_required(funcao):
    @wraps(funcao)
    def interna(*args, **kwargs):
        uid = session.get("uid")
        row = None
        if uid is not None:
            row = get_db().execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()
        if row is None:
            session.clear()
            raise ErroApi("Você precisa entrar na sua conta.", 401)
        g.usuario = row
        return funcao(*args, **kwargs)

    return interna


def resolver_alvo(ident: str, usuario: sqlite3.Row) -> None:
    """Cada pessoa só mexe na própria conta: '/me' ou o próprio id."""
    if ident == "me":
        return
    if not ident.isdigit():
        raise ErroApi("Recurso não encontrado.", 404)
    if int(ident) != usuario["id"]:
        raise ErroApi("Você só pode acessar a sua própria conta.", 403)


def confirmar_senha(usuario: sqlite3.Row, senha, campo: str) -> None:
    """Exige a senha atual (troca de senha e exclusão), com limite de tentativas."""
    limitador: LimitadorTentativas = current_app.extensions["limitador"]
    chave = ("conta", usuario["id"])
    restante = limitador.restante(chave)
    if restante:
        raise ErroApi(mensagem_bloqueio(restante), 429, campo)
    if not isinstance(senha, str) or not check_password_hash(usuario["senha_hash"], senha):
        limitador.registrar(chave)
        raise ErroApi("Senha incorreta.", 403, campo)
    limitador.limpar(chave)


# --------------------------------------------------------------------------
# Aplicação
# --------------------------------------------------------------------------

def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(SITE_DIR), static_url_path="")

    app.config.update(
        SECRET_KEY=os.environ.get("NOPONTO_SECRET_KEY"),
        DATABASE=os.environ.get("NOPONTO_DATABASE", str(BASE_DIR / "noponto.db")),
        UPLOAD_DIR=os.environ.get("NOPONTO_UPLOAD_DIR", str(BASE_DIR / "uploads")),
        MAX_CONTENT_LENGTH=FOTO_MAX_BYTES + 512 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Defina NOPONTO_COOKIE_SECURE=1 quando o site rodar em HTTPS.
        SESSION_COOKIE_SECURE=os.environ.get("NOPONTO_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        # Opcional: NOPONTO_EMAIL_DOMAIN=aluno.puc-rio.br restringe o cadastro.
        ALLOWED_EMAIL_DOMAIN=os.environ.get("NOPONTO_EMAIL_DOMAIN", ""),
        LOGIN_MAX_ATTEMPTS=5,
        LOGIN_WINDOW_SECONDS=15 * 60,
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        print(
            "AVISO: NOPONTO_SECRET_KEY não definida. Foi gerada uma chave temporária; "
            "todo mundo será deslogado quando o servidor reiniciar."
        )

    app.config["UPLOAD_DIR"] = str(Path(app.config["UPLOAD_DIR"]).resolve())
    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    app.extensions["limitador"] = LimitadorTentativas(
        app.config["LOGIN_MAX_ATTEMPTS"], app.config["LOGIN_WINDOW_SECONDS"]
    )
    # Hash de mentira: login com e-mail inexistente gasta o mesmo tempo que um real.
    app.extensions["hash_falso"] = generate_password_hash(secrets.token_hex(16))

    @app.teardown_appcontext
    def fechar_db(_erro):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        init_db()

    # ---------- proteções gerais ----------

    @app.before_request
    def verificar_origem():
        """Barra requisições que mudam dados vindas de outro site (reforça o SameSite)."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        origem = request.headers.get("Origin")
        if origem and urlparse(origem).netloc != request.host:
            return resposta_erro("Origem da requisição não permitida.", 403)
        return None

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.errorhandler(ErroApi)
    def tratar_erro_api(e: ErroApi):
        return resposta_erro(e.mensagem, e.status, e.campo)

    @app.errorhandler(404)
    def tratar_404(e):
        if request.path.startswith("/api/"):
            return resposta_erro("Recurso não encontrado.", 404)
        return e

    @app.errorhandler(405)
    def tratar_405(e):
        if request.path.startswith("/api/"):
            return resposta_erro("Método não permitido.", 405)
        return e

    @app.errorhandler(413)
    def tratar_413(_e):
        return resposta_erro("Arquivo grande demais.", 413, "foto")

    # ---------- páginas e arquivos ----------

    @app.get("/")
    def inicio():
        return redirect("/Login/login.html")

    @app.get("/uploads/<path:nome>")
    def foto_perfil(nome: str):
        return send_from_directory(app.config["UPLOAD_DIR"], nome)

    # ---------- API: cadastro e sessão ----------

    @app.post("/api/usuarios")
    def cadastrar():
        dados = dados_requisicao()
        nome = validar_nome(dados.get("nome"))
        email = validar_email(dados.get("email"))
        curso = validar_curso(dados.get("curso"))
        matricula = validar_matricula(dados.get("matricula"))
        senha = validar_senha(dados.get("senha"), "senha")

        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO usuarios (nome, email, curso, matricula, senha_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (nome, email, curso, matricula, generate_password_hash(senha)),
            )
            db.commit()
        except sqlite3.IntegrityError:
            raise ErroApi("Este e-mail já está cadastrado.", 409, "email")

        row = db.execute("SELECT * FROM usuarios WHERE id = ?", (cur.lastrowid,)).fetchone()
        return jsonify({"usuario": usuario_publico(row)}), 201

    @app.post("/api/login")
    def entrar():
        dados = dados_requisicao()
        email = texto(dados.get("email")).lower()
        senha = dados.get("senha")

        limitador: LimitadorTentativas = app.extensions["limitador"]
        chave = ("login", email, request.remote_addr or "")
        restante = limitador.restante(chave)
        if restante:
            raise ErroApi(mensagem_bloqueio(restante), 429)

        row = get_db().execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        hash_senha = row["senha_hash"] if row else app.extensions["hash_falso"]
        senha_ok = isinstance(senha, str) and check_password_hash(hash_senha, senha)

        if row is None or not senha_ok:
            limitador.registrar(chave)
            # Mesma mensagem nos dois casos: não revela se o e-mail existe.
            raise ErroApi("E-mail ou senha incorretos.", 401)

        limitador.limpar(chave)
        session.clear()  # evita fixação de sessão
        session["uid"] = row["id"]
        session.permanent = True
        return jsonify({"usuario": usuario_publico(row)})

    @app.post("/api/logout")
    def sair():
        session.clear()
        return jsonify({"ok": True})

    # ---------- API: conta do usuário logado ----------

    @app.get("/api/usuarios/me")
    @login_required
    def ver_perfil():
        return jsonify({"usuario": usuario_publico(g.usuario)})

    @app.put("/api/usuarios/<ident>")
    @login_required
    def editar_perfil(ident: str):
        usuario = g.usuario
        resolver_alvo(ident, usuario)
        dados = dados_requisicao()
        db = get_db()

        campos: dict = {}
        if "nome" in dados:
            campos["nome"] = validar_nome(dados.get("nome"))
        if "curso" in dados:
            campos["curso"] = validar_curso(dados.get("curso"))
        if "matricula" in dados:
            campos["matricula"] = validar_matricula(dados.get("matricula"))

        nova_senha = dados.get("novaSenha")
        if nova_senha:
            confirmar_senha(usuario, dados.get("senhaAtual"), "senhaAtual")
            validar_senha(nova_senha, "novaSenha")
            campos["senha_hash"] = generate_password_hash(nova_senha)

        foto_nova = None
        arquivo = request.files.get("foto")
        if arquivo and arquivo.filename:
            foto_nova = validar_foto(arquivo)
        remover_foto = str(dados.get("removerFoto", "")).lower() == "true"

        if not campos and foto_nova is None and not remover_foto:
            raise ErroApi("Nenhuma alteração informada.", 400)

        foto_antiga = usuario["foto"]
        arquivo_novo = None
        if foto_nova is not None:
            arquivo_novo = gravar_foto(*foto_nova)
            campos["foto"] = arquivo_novo
        elif remover_foto:
            campos["foto"] = None

        if campos:
            # As chaves de `campos` são nomes fixos definidos acima, nunca texto do usuário.
            definicoes = ", ".join(f"{coluna} = ?" for coluna in campos)
            try:
                db.execute(
                    f"UPDATE usuarios SET {definicoes} WHERE id = ?",
                    (*campos.values(), usuario["id"]),
                )
                db.commit()
            except Exception:
                apagar_foto(arquivo_novo)
                raise
            if "foto" in campos:
                apagar_foto(foto_antiga)

        row = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario["id"],)).fetchone()
        return jsonify({"usuario": usuario_publico(row)})

    @app.delete("/api/usuarios/<ident>")
    @login_required
    def excluir_conta(ident: str):
        usuario = g.usuario
        resolver_alvo(ident, usuario)
        dados = dados_requisicao()
        confirmar_senha(usuario, dados.get("senha"), "senha")

        db = get_db()
        db.execute("DELETE FROM usuarios WHERE id = ?", (usuario["id"],))
        db.commit()
        apagar_foto(usuario["foto"])
        session.clear()
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    create_app().run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("NOPONTO_DEBUG") == "1",
    )
