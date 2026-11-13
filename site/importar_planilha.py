"""
Atualiza o banco de dados do NoPonto! a partir de uma planilha do Excel.

Como usar (no terminal do Codespace, dentro da pasta "site"):

    python importar_planilha.py noponto_dados.xlsx --simular   # só mostra o que mudaria
    python importar_planilha.py noponto_dados.xlsx             # grava no banco
    python importar_planilha.py --exportar banco_atual.xlsx    # baixa o banco atual para uma planilha

A planilha precisa das abas "Estilos", "Restaurantes" e "Pratos" (veja a aba "Leia-me").

Regras:
- Nada é apagado. O script só cria o que não existe e atualiza o que já existe.
- Restaurantes, estilos e pratos são reconhecidos pelo nome (sem diferenciar maiúsculas/minúsculas).
- Célula vazia na aba "Restaurantes" = manter o valor que já está no banco.
- Rodar a mesma planilha duas vezes não duplica nada.
"""

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "noPonto.settings")
django.setup()

from django.db import transaction  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402

from noPonto.models import Cardapio, EstiloComida, Prato, Restaurante  # noqa: E402


class Simulacao(Exception):
    """Usada para desfazer tudo no modo --simular."""


def texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def ler_preco(valor):
    """Aceita 33.99, 33,99 ou 'R$ 33,99'."""
    if isinstance(valor, (int, float)):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    s = texto(valor).replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def ler_aba(wb, nome_aba, colunas):
    """Devolve (numero_da_linha, {coluna: valor}) para cada linha preenchida."""
    if nome_aba not in wb.sheetnames:
        raise SystemExit(f'ERRO: a planilha não tem a aba "{nome_aba}".')
    ws = wb[nome_aba]
    cabecalho = [texto(c.value).lower() for c in ws[1]]
    faltando = [c for c in colunas if c not in cabecalho]
    if faltando:
        raise SystemExit(f'ERRO: na aba "{nome_aba}" faltam as colunas: {", ".join(faltando)}')
    idx = {c: cabecalho.index(c) for c in colunas}
    for num, linha in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        dados = {c: linha[i] if i < len(linha) else None for c, i in idx.items()}
        if all(texto(v) == "" for v in dados.values()):
            continue
        yield num, dados


def importar(caminho):
    wb = load_workbook(caminho, data_only=True)
    resumo = {"estilos_novos": 0, "rest_novos": 0, "rest_atualizados": 0,
              "pratos_novos": 0, "pratos_atualizados": 0}
    avisos = []

    # ---------- Estilos ----------
    for num, d in ler_aba(wb, "Estilos", ["nome"]):
        nome = texto(d["nome"])
        if not EstiloComida.objects.filter(nome__iexact=nome).exists():
            EstiloComida.objects.create(nome=nome)
            resumo["estilos_novos"] += 1
            print(f"  + estilo novo: {nome}")

    # ---------- Restaurantes ----------
    for num, d in ler_aba(wb, "Restaurantes", ["nome", "estilo", "localizacao", "descricao"]):
        nome = texto(d["nome"])
        if not nome:
            avisos.append(f'Restaurantes, linha {num}: falta o nome. Linha ignorada.')
            continue

        estilo = None
        if texto(d["estilo"]):
            estilo = EstiloComida.objects.filter(nome__iexact=texto(d["estilo"])).first()
            if estilo is None:
                avisos.append(f'Restaurantes, linha {num}: estilo "{texto(d["estilo"])}" não existe '
                              f'(adicione na aba Estilos). Estilo não alterado.')

        r = Restaurante.objects.filter(nome__iexact=nome).first()
        if r is None:
            r = Restaurante.objects.create(
                nome=nome,
                descricao=texto(d["descricao"]),
                localizacao=texto(d["localizacao"]),
                estilo=estilo,
            )
            resumo["rest_novos"] += 1
            print(f"  + restaurante novo: {nome}")
        else:
            mudou = []
            for campo in ("localizacao", "descricao"):
                novo = texto(d[campo])
                if novo and novo != getattr(r, campo):
                    setattr(r, campo, novo)
                    mudou.append(campo)
            if estilo is not None and r.estilo_id != estilo.id:
                r.estilo = estilo
                mudou.append("estilo")
            if mudou:
                r.save()
                resumo["rest_atualizados"] += 1
                print(f"  ~ restaurante atualizado: {r.nome} ({', '.join(mudou)})")

    # ---------- Pratos ----------
    for num, d in ler_aba(wb, "Pratos", ["restaurante", "prato", "preco"]):
        nome_rest, nome_prato = texto(d["restaurante"]), texto(d["prato"])
        preco = ler_preco(d["preco"])
        if not nome_rest or not nome_prato:
            avisos.append(f"Pratos, linha {num}: falta o restaurante ou o nome do prato. Linha ignorada.")
            continue
        if preco is None:
            avisos.append(f'Pratos, linha {num}: preço "{texto(d["preco"])}" inválido. Linha ignorada.')
            continue
        if len(nome_prato) > 100:
            avisos.append(f"Pratos, linha {num}: nome do prato tem mais de 100 letras. Linha ignorada.")
            continue
        r = Restaurante.objects.filter(nome__iexact=nome_rest).first()
        if r is None:
            avisos.append(f'Pratos, linha {num}: restaurante "{nome_rest}" não existe '
                          f'(adicione na aba Restaurantes). Linha ignorada.')
            continue
        cardapio, _ = Cardapio.objects.get_or_create(restaurante=r)
        p = Prato.objects.filter(cardapio=cardapio, nome__iexact=nome_prato).first()
        if p is None:
            Prato.objects.create(cardapio=cardapio, nome=nome_prato, preco=preco)
            resumo["pratos_novos"] += 1
        elif p.preco != preco:
            p.preco = preco
            p.save()
            resumo["pratos_atualizados"] += 1
            print(f"  ~ preço atualizado: {r.nome} / {p.nome} -> R$ {preco}")

    return resumo, avisos


def exportar(caminho):
    wb = Workbook()
    negrito = Font(name="Arial", bold=True, color="FFFFFF")
    fundo = PatternFill("solid", fgColor="1B365D")

    def aba(ws, titulo, cabecalho, linhas, larguras):
        ws.title = titulo
        ws.append(cabecalho)
        for c in ws[1]:
            c.font, c.fill = negrito, fundo
        for linha in linhas:
            ws.append(linha)
        for col, w in zip("ABCD", larguras):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial")
        ws.freeze_panes = "A2"

    aba(wb.active, "Estilos", ["nome"],
        [[e.nome] for e in EstiloComida.objects.order_by("nome")], [30])
    aba(wb.create_sheet(), "Restaurantes", ["nome", "estilo", "localizacao", "descricao"],
        [[r.nome, r.estilo.nome if r.estilo else "", r.localizacao, r.descricao]
         for r in Restaurante.objects.select_related("estilo").order_by("nome")],
        [32, 20, 40, 80])
    pratos = Prato.objects.select_related("cardapio__restaurante").order_by(
        "cardapio__restaurante__nome", "id")
    aba(wb.create_sheet(), "Pratos", ["restaurante", "prato", "preco"],
        [[p.cardapio.restaurante.nome, p.nome, float(p.preco)] for p in pratos],
        [28, 70, 12])
    for c in wb["Pratos"]["C"][1:]:
        c.number_format = '"R$" #,##0.00'
    wb.save(caminho)
    print(f"Banco exportado para {caminho}: "
          f"{EstiloComida.objects.count()} estilos, {Restaurante.objects.count()} restaurantes, "
          f"{Prato.objects.count()} pratos.")


def main():
    ap = argparse.ArgumentParser(description="Importa/exporta dados do NoPonto! em planilhas do Excel.")
    ap.add_argument("planilha", nargs="?", help="arquivo .xlsx para importar")
    ap.add_argument("--simular", action="store_true", help="mostra o que mudaria, sem gravar nada")
    ap.add_argument("--exportar", metavar="ARQUIVO", help="salva o banco atual em uma planilha .xlsx")
    args = ap.parse_args()

    if args.exportar:
        exportar(args.exportar)
        return
    if not args.planilha:
        ap.error("informe a planilha para importar (ou use --exportar)")
    if not os.path.exists(args.planilha):
        raise SystemExit(f'ERRO: arquivo "{args.planilha}" não encontrado nesta pasta.')

    print(("SIMULAÇÃO (nada será gravado)" if args.simular else "Importando") + f": {args.planilha}")
    try:
        with transaction.atomic():
            resumo, avisos = importar(args.planilha)
            if args.simular:
                raise Simulacao
    except Simulacao:
        pass

    print("\nResumo:")
    print(f"  Estilos novos:            {resumo['estilos_novos']}")
    print(f"  Restaurantes novos:       {resumo['rest_novos']}")
    print(f"  Restaurantes atualizados: {resumo['rest_atualizados']}")
    print(f"  Pratos novos:             {resumo['pratos_novos']}")
    print(f"  Preços atualizados:       {resumo['pratos_atualizados']}")
    if avisos:
        print(f"\nAvisos ({len(avisos)}):")
        for a in avisos:
            print(f"  ! {a}")
    print("\nNada foi gravado (modo --simular)." if args.simular else "\nPronto! Banco atualizado.")


if __name__ == "__main__":
    main()
