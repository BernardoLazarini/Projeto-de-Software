# noPonto — Backend de autenticação

Cadastro, login, edição de perfil (com foto e troca de senha) e exclusão de conta.
Feito com **Flask + SQLite**. O mesmo servidor entrega as páginas da pasta `Site/`.

## Como rodar

```bash
cd Backend
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000 (redireciona para a tela de login).

Para rodar os testes:

```bash
python -m unittest -v
```

## Variáveis de ambiente (todas opcionais)

| Variável | Para que serve |
|---|---|
| `NOPONTO_SECRET_KEY` | Chave que assina o cookie de sessão. Se faltar, o servidor gera uma temporária e todo mundo é deslogado a cada reinício. Em produção, defina uma chave longa e fixa. |
| `NOPONTO_EMAIL_DOMAIN` | Ex.: `aluno.puc-rio.br`. Se definida, só aceita cadastro com esse domínio. |
| `NOPONTO_COOKIE_SECURE` | `1` quando o site rodar em HTTPS. |
| `NOPONTO_DATABASE` | Caminho do arquivo SQLite (padrão: `Backend/noponto.db`). |
| `NOPONTO_UPLOAD_DIR` | Pasta das fotos de perfil (padrão: `Backend/uploads`). |
| `PORT` | Porta do servidor (padrão: 5000). |

## Endpoints

| Método e rota | O que faz | Precisa de login |
|---|---|---|
| `POST /api/usuarios` | Cria a conta (`nome`, `email`, `curso`, `matricula`, `senha`) | Não |
| `POST /api/login` | Entra (`email`, `senha`) | Não |
| `POST /api/logout` | Sai | Não |
| `GET /api/usuarios/me` | Dados do usuário logado | Sim |
| `PUT /api/usuarios/me` | Edita nome, curso, matrícula, foto (`foto`, `removerFoto`) e senha (`senhaAtual`, `novaSenha`) | Sim |
| `DELETE /api/usuarios/me` | Exclui a conta (`senha`) | Sim |

`PUT` e `DELETE` também aceitam o id no lugar de `me` (`/api/usuarios/3`), mas só funciona com o id do próprio usuário. Erros voltam como `{"erro": "mensagem", "campo": "nome-do-campo"}`.

## Decisões de segurança

- Senhas guardadas só como hash (Werkzeug/scrypt). O hash nunca sai da API.
- Tudo é validado no servidor, além da validação do navegador.
- Sessão em cookie `HttpOnly` + `SameSite=Lax`, e requisições que alteram dados vindas de outro site são recusadas.
- Login com e-mail inexistente ou senha errada dá a mesma resposta, e há bloqueio temporário após 5 falhas.
- Trocar a senha e excluir a conta exigem a senha atual.
- Fotos: o tipo é conferido pelo conteúdo do arquivo (JPG, PNG ou WebP, até 2 MB) e o nome é gerado pelo servidor.

## O que ainda não existe

- Confirmação de cadastro por e-mail e recuperação de senha ("Esqueci minha senha" ainda está com `#`).
- O bloqueio de tentativas fica na memória do processo: reiniciar o servidor zera a contagem.
- Ao excluir a conta, apaga-se o usuário e a foto. Quando existirem avaliações e favoritos, a tabela deles deve usar `ON DELETE CASCADE` para sumirem junto.
