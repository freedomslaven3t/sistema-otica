"""Início, login e backup."""
import json
from datetime import timedelta

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import banco
import importacao
import seguranca
import util
from modelos import Cliente, Venda

bp = Blueprint("sistema", __name__)
S = banco.Sessao


@bp.get("/")
def inicio():
    hoje = util.hoje()
    vendas = S.scalars(select(Venda).options(selectinload(Venda.pagamentos), selectinload(Venda.cliente))).all()
    do_mes = [v for v in vendas if (v.data.year, v.data.month) == (hoje.year, hoje.month)]

    pendentes = [v for v in vendas if not v.entregue_em]
    pendentes.sort(key=lambda v: (v.entrega_prevista is None, v.entrega_prevista or hoje))

    limite = hoje - timedelta(days=365)
    clientes = S.scalars(select(Cliente).options(selectinload(Cliente.receitas))).all()
    retornos = sorted((c for c in clientes if c.ultima_consulta and c.ultima_consulta < limite),
                      key=lambda c: c.ultima_consulta)

    return render_template(
        "inicio.html",
        total_clientes=len(clientes),
        vendido_mes=sum(v.valor for v in do_mes), vendas_mes=len(do_mes),
        a_receber=sum(v.saldo for v in vendas),
        entregas=pendentes[:10], total_pendentes=len(pendentes), retornos=retornos[:10], total_retornos=len(retornos))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not seguranca.senha():
        return redirect(url_for(".inicio"))
    if request.method == "POST":
        resposta = seguranca.tentar_login()
        if resposta:
            return resposta
    return render_template("login.html")


@bp.post("/sair")
def sair():
    session.clear()
    return redirect(url_for(".login"))


@bp.get("/backup")
def backup():
    return render_template("backup.html", sqlite=banco.SQLITE, backups=banco.listar_backups())


@bp.get("/backup/banco")
def baixar_banco():
    if not banco.SQLITE:
        flash("Este sistema usa PostgreSQL. Faça o backup pelo provedor do banco ou use o arquivo JSON.", "erro")
        return redirect(url_for(".backup"))
    return Response(banco.copia_do_banco(), mimetype="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=otica_{util.hoje().isoformat()}.db"})


@bp.get("/backup/json")
def baixar_json():
    texto = json.dumps(importacao.exportar(S), ensure_ascii=False, indent=2)
    return Response(texto, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename=otica_dados_{util.hoje().isoformat()}.json"})


@bp.post("/backup/importar")
def importar():
    arq = request.files.get("arquivo")
    if not arq or not arq.filename:
        flash("Escolha um arquivo .json primeiro.", "erro")
        return redirect(url_for(".backup"))
    try:
        dados = json.loads(arq.read().decode("utf-8-sig"))
        r = importacao.importar(S, dados)
    except (ValueError, UnicodeDecodeError) as e:      # JSON inválido também é ValueError
        S.rollback()
        flash(str(e) if "Arquivo inválido" in str(e) else "Arquivo inválido. Use um arquivo exportado por este sistema ou pelo sistema antigo.", "erro")
        return redirect(url_for(".backup"))
    flash(f"Importação concluída: {r['clientes_novos']} cliente(s), {r['receitas_novas']} receita(s) e "
          f"{r['vendas_novas']} venda(s) novas. Já existiam {r['vendas_repetidas']} venda(s); ignorados: {r['ignorados']}.", "ok")
    return redirect(url_for(".backup"))
