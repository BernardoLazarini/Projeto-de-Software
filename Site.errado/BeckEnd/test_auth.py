"""
Testes de autenticação do noPonto (cadastro, login, edição e exclusão de conta).

Rodar a partir da pasta Backend:
    python -m unittest -v
"""
import io
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

USUARIO = {
    "nome": "Lucas Silveira",
    "email": "lucas@aluno.puc-rio.br",
    "curso": "Engenharia",
    "matricula": "2311234",
    "senha": "senhaSegura123",
}


class BaseTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "chave-de-teste",
                "DATABASE": str(self.tmp / "teste.db"),
                "UPLOAD_DIR": str(self.tmp / "uploads"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- atalhos ---
    def cadastrar(self, client=None, **mudancas):
        dados = {**USUARIO, **mudancas}
        return (client or self.client).post("/api/usuarios", json=dados)

    def entrar(self, client=None, email=USUARIO["email"], senha=USUARIO["senha"]):
        return (client or self.client).post("/api/login", json={"email": email, "senha": senha})

    def cadastrar_e_entrar(self, **mudancas):
        self.assertEqual(self.cadastrar(**mudancas).status_code, 201)
        email = mudancas.get("email", USUARIO["email"])
        self.assertEqual(self.entrar(email=email).status_code, 200)


class TesteCadastro(BaseTeste):
    def test_cadastro_valido(self):
        r = self.cadastrar()
        self.assertEqual(r.status_code, 201)
        usuario = r.get_json()["usuario"]
        self.assertEqual(usuario["email"], USUARIO["email"])
        self.assertNotIn("senha", usuario)
        self.assertNotIn("senha_hash", usuario)

    def test_senha_fica_salva_como_hash(self):
        self.cadastrar()
        db = sqlite3.connect(self.app.config["DATABASE"])
        (guardado,) = db.execute("SELECT senha_hash FROM usuarios").fetchone()
        db.close()
        self.assertNotEqual(guardado, USUARIO["senha"])
        self.assertNotIn(USUARIO["senha"], guardado)

    def test_email_duplicado_ignora_maiusculas(self):
        self.cadastrar()
        r = self.cadastrar(email="LUCAS@aluno.puc-rio.br")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["campo"], "email")

    def test_campos_invalidos(self):
        casos = [
            ({"nome": "Lu"}, "nome"),
            ({"email": "isso-nao-e-email"}, "email"),
            ({"curso": "Astrologia"}, "curso"),
            ({"matricula": "23 11!"}, "matricula"),
            ({"senha": "curta"}, "senha"),
        ]
        for mudanca, campo in casos:
            with self.subTest(campo=campo):
                r = self.cadastrar(**mudanca)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.get_json()["campo"], campo)

    def test_corpo_que_nao_e_json_e_rejeitado(self):
        r = self.client.post("/api/usuarios", data="qualquer coisa")
        self.assertEqual(r.status_code, 400)

    def test_restricao_de_dominio_opcional(self):
        self.app.config["ALLOWED_EMAIL_DOMAIN"] = "aluno.puc-rio.br"
        self.assertEqual(self.cadastrar(email="alguem@gmail.com").status_code, 400)
        self.assertEqual(self.cadastrar().status_code, 201)


class TesteLogin(BaseTeste):
    def test_login_correto_e_perfil(self):
        self.cadastrar()
        self.assertEqual(self.entrar().status_code, 200)
        r = self.client.get("/api/usuarios/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["usuario"]["nome"], USUARIO["nome"])

    def test_login_aceita_email_com_maiusculas(self):
        self.cadastrar()
        self.assertEqual(self.entrar(email="  LUCAS@Aluno.PUC-Rio.br ").status_code, 200)

    def test_senha_errada_e_email_inexistente_dao_a_mesma_resposta(self):
        self.cadastrar()
        errada = self.entrar(senha="senhaErrada999")
        inexistente = self.entrar(email="ninguem@aluno.puc-rio.br")
        self.assertEqual(errada.status_code, 401)
        self.assertEqual(inexistente.status_code, 401)
        self.assertEqual(errada.get_json(), inexistente.get_json())

    def test_perfil_exige_login(self):
        self.assertEqual(self.client.get("/api/usuarios/me").status_code, 401)

    def test_logout(self):
        self.cadastrar_e_entrar()
        self.assertEqual(self.client.post("/api/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/usuarios/me").status_code, 401)

    def test_bloqueio_apos_varias_falhas(self):
        self.cadastrar()
        limite = self.app.config["LOGIN_MAX_ATTEMPTS"]
        for _ in range(limite):
            self.assertEqual(self.entrar(senha="errada-errada").status_code, 401)
        # Depois do limite, até a senha certa fica bloqueada por um tempo.
        self.assertEqual(self.entrar().status_code, 429)


class TesteEdicao(BaseTeste):
    def test_editar_dados(self):
        self.cadastrar_e_entrar()
        r = self.client.put(
            "/api/usuarios/me",
            json={"nome": "Lucas S. Silveira", "curso": "Design", "matricula": ""},
        )
        self.assertEqual(r.status_code, 200)
        usuario = r.get_json()["usuario"]
        self.assertEqual(usuario["nome"], "Lucas S. Silveira")
        self.assertEqual(usuario["curso"], "Design")
        self.assertEqual(usuario["matricula"], "")

    def test_email_nao_pode_ser_alterado(self):
        self.cadastrar_e_entrar()
        self.client.put("/api/usuarios/me", json={"nome": "Outro Nome", "email": "novo@x.com"})
        r = self.client.get("/api/usuarios/me")
        self.assertEqual(r.get_json()["usuario"]["email"], USUARIO["email"])

    def test_editar_exige_login(self):
        r = self.client.put("/api/usuarios/me", json={"nome": "Alguém Qualquer"})
        self.assertEqual(r.status_code, 401)

    def test_nao_edita_conta_de_outra_pessoa(self):
        self.cadastrar_e_entrar()
        outro = self.app.test_client()
        r = self.cadastrar(client=outro, email="maria@aluno.puc-rio.br", nome="Maria Souza")
        id_outra = r.get_json()["usuario"]["id"]
        r = self.client.put(f"/api/usuarios/{id_outra}", json={"nome": "Hackeada Aqui"})
        self.assertEqual(r.status_code, 403)

    def test_trocar_senha(self):
        self.cadastrar_e_entrar()
        r = self.client.put(
            "/api/usuarios/me",
            json={"senhaAtual": USUARIO["senha"], "novaSenha": "outraSenha456"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.entrar().status_code, 401)  # senha antiga não vale mais
        self.assertEqual(self.entrar(senha="outraSenha456").status_code, 200)

    def test_trocar_senha_exige_senha_atual_correta(self):
        self.cadastrar_e_entrar()
        r = self.client.put(
            "/api/usuarios/me",
            json={"senhaAtual": "chute-errado", "novaSenha": "outraSenha456"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["campo"], "senhaAtual")
        self.assertEqual(self.entrar().status_code, 200)  # senha original continua valendo

    def test_nova_senha_curta(self):
        self.cadastrar_e_entrar()
        r = self.client.put(
            "/api/usuarios/me",
            json={"senhaAtual": USUARIO["senha"], "novaSenha": "curta"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["campo"], "novaSenha")

    def test_requisicao_de_outra_origem_e_barrada(self):
        self.cadastrar_e_entrar()
        r = self.client.put(
            "/api/usuarios/me",
            json={"nome": "Nome Alterado"},
            headers={"Origin": "http://site-malicioso.example"},
        )
        self.assertEqual(r.status_code, 403)


class TesteFoto(BaseTeste):
    def enviar_foto(self, conteudo, nome_arquivo="foto.png"):
        return self.client.put(
            "/api/usuarios/me",
            data={"nome": USUARIO["nome"], "foto": (io.BytesIO(conteudo), nome_arquivo)},
            content_type="multipart/form-data",
        )

    def arquivos_salvos(self):
        return list(Path(self.app.config["UPLOAD_DIR"]).iterdir())

    def test_enviar_foto_valida(self):
        self.cadastrar_e_entrar()
        r = self.enviar_foto(PNG)
        self.assertEqual(r.status_code, 200)
        url = r.get_json()["usuario"]["fotoUrl"]
        self.assertTrue(url.startswith("/uploads/"))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(len(self.arquivos_salvos()), 1)

    def test_arquivo_que_nao_e_imagem_e_rejeitado_mesmo_com_nome_png(self):
        self.cadastrar_e_entrar()
        r = self.enviar_foto(b"<script>alert(1)</script>", "foto.png")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["campo"], "foto")
        self.assertEqual(self.arquivos_salvos(), [])

    def test_imagem_grande_demais(self):
        self.cadastrar_e_entrar()
        grande = PNG + b"\x00" * (2 * 1024 * 1024 + 10)
        r = self.enviar_foto(grande)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(self.arquivos_salvos(), [])

    def test_trocar_foto_apaga_a_antiga(self):
        self.cadastrar_e_entrar()
        self.enviar_foto(PNG)
        self.enviar_foto(PNG + b"\x01")
        self.assertEqual(len(self.arquivos_salvos()), 1)

    def test_remover_foto(self):
        self.cadastrar_e_entrar()
        self.enviar_foto(PNG)
        r = self.client.put("/api/usuarios/me", data={"removerFoto": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["usuario"]["fotoUrl"])
        self.assertEqual(self.arquivos_salvos(), [])


class TesteExclusao(BaseTeste):
    def test_excluir_com_senha_errada_nao_exclui(self):
        self.cadastrar_e_entrar()
        r = self.client.delete("/api/usuarios/me", json={"senha": "senha-errada-1"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/api/usuarios/me").status_code, 200)

    def test_excluir_sem_senha(self):
        self.cadastrar_e_entrar()
        r = self.client.delete("/api/usuarios/me", json={})
        self.assertEqual(r.status_code, 403)

    def test_excluir_exige_login(self):
        self.assertEqual(self.client.delete("/api/usuarios/me", json={"senha": "x"}).status_code, 401)

    def test_excluir_conta(self):
        self.cadastrar_e_entrar()
        r = self.client.delete("/api/usuarios/me", json={"senha": USUARIO["senha"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/usuarios/me").status_code, 401)
        self.assertEqual(self.entrar().status_code, 401)
        # O e-mail volta a ficar livre para um novo cadastro.
        self.assertEqual(self.cadastrar().status_code, 201)

    def test_excluir_conta_apaga_a_foto(self):
        self.cadastrar_e_entrar()
        self.client.put(
            "/api/usuarios/me",
            data={"foto": (io.BytesIO(PNG), "foto.png")},
            content_type="multipart/form-data",
        )
        self.client.delete("/api/usuarios/me", json={"senha": USUARIO["senha"]})
        self.assertEqual(list(Path(self.app.config["UPLOAD_DIR"]).iterdir()), [])

    def test_nao_exclui_conta_de_outra_pessoa(self):
        self.cadastrar_e_entrar()
        outro = self.app.test_client()
        r = self.cadastrar(client=outro, email="maria@aluno.puc-rio.br", nome="Maria Souza")
        id_outra = r.get_json()["usuario"]["id"]
        r = self.client.delete(f"/api/usuarios/{id_outra}", json={"senha": USUARIO["senha"]})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.entrar(client=outro, email="maria@aluno.puc-rio.br").status_code, 200)


class TesteGeral(BaseTeste):
    def test_raiz_redireciona_para_o_login(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/Login/login.html"))

    def test_rota_inexistente_da_api_devolve_json(self):
        r = self.client.get("/api/nao-existe")
        self.assertEqual(r.status_code, 404)
        self.assertIn("erro", r.get_json())


if __name__ == "__main__":
    unittest.main()
