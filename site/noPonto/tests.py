import re

from django.test import Client
from django.test import TestCase

from .models import Aluno


class CadastroTests(TestCase):
    def test_formulario_aceita_token_csrf_renderizado(self):
        client = Client(enforce_csrf_checks=True)
        pagina = client.get("/cadastro/")
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            pagina.content,
        )

        self.assertIsNotNone(token)
        resposta = client.post(
            "/cadastro/",
            {
                "csrfmiddlewaretoken": token.group(1).decode(),
                "nome": "Pessoa Teste",
                "email": "csrf@example.com",
                "senha": "senha-segura-123",
                "confirmarSenha": "senha-segura-123",
            },
        )

        self.assertEqual(resposta.status_code, 302)

    def test_cadastra_contas_com_emails_diferentes(self):
        Aluno.objects.create(nome="Conta legada", username="", password="")
        dados_cadastro = {
            "nome": "Pessoa Teste",
            "senha": "senha-segura-123",
            "confirmarSenha": "senha-segura-123",
        }

        primeira_resposta = self.client.post(
            "/cadastro/",
            {**dados_cadastro, "email": "primeira@example.com"},
        )
        segunda_resposta = self.client.post(
            "/cadastro/",
            {**dados_cadastro, "email": "segunda@example.com"},
        )

        self.assertEqual(primeira_resposta.status_code, 302)
        self.assertEqual(segunda_resposta.status_code, 302)
        self.assertSetEqual(
            set(Aluno.objects.values_list("username", flat=True)),
            {"", "primeira@example.com", "segunda@example.com"},
        )

    def test_email_ja_usado_por_aluno_sem_usuario_exibe_erro(self):
        Aluno.objects.create(
            nome="Conta legada",
            username="legado@example.com",
            password="",
        )

        resposta = self.client.post(
            "/cadastro/",
            {
                "nome": "Pessoa Teste",
                "email": "legado@example.com",
                "senha": "senha-segura-123",
                "confirmarSenha": "senha-segura-123",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Esse e-mail já está cadastrado.")
