"""Clientes e receitas."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

import banco
import util
from modelos import GRAUS, Cliente, Receita, Venda

bp = Blueprint("clientes", __name__)
S = banco.Sessao


def _cliente(id) -> Cliente:
    c = S.get(Cliente, id)
    if not c:
        abort(404)
    return c


@bp.get("/clientes")
def lista():
    q = util.norm(request.args.get("q", "")).strip()
    qd = util.so_digitos(q)
    todos = S.scalars(select(Cliente).options(
        selectinload(Cliente.vendas).selectinload(Venda.pagamentos),
        selectinload(Cliente.receitas))).all()

    def bate(c):
        return (not q or (q.isdigit() and int(q) == c.id) or q in util.norm(c.nome)
                or (qd and (qd in (c.cpf or "") or qd in util.so_digitos(c.telefone))))

    achados = sorted((c for c in todos if bate(c)), key=lambda c: util.norm(c.nome))
    return render_template("clientes.html", clientes=achados, q=request.args.get("q", ""))


def _ler(form, atual):
    """Valida o formulário. Devolve (dados, lista de erros)."""
    erros = []
    nome = " ".join(form.get("nome", "").split())
    if not nome:
        erros.append("Informe o nome do cliente.")
    cpf = util.so_digitos(form.get("cpf")) or None
    if cpf and len(cpf) != 11:
        erros.append("O CPF precisa ter 11 números (ou deixe em branco).")
        cpf = None
    if cpf:
        outro = S.scalar(select(Cliente).where(Cliente.cpf == cpf, Cliente.id != (atual.id if atual else 0)))
        if outro:
            erros.append(f"Já existe um cliente com este CPF: #{outro.id} {outro.nome}.")
    try:
        nasc = util.parse_data(form.get("nascimento"))
    except ValueError:
        erros.append("Data de nascimento inválida.")
        nasc = None
    return dict(nome=nome[:120], cpf=cpf, telefone=form.get("telefone", "").strip()[:30], nascimento=nasc,
                endereco=form.get("endereco", "").strip()[:200], obs=form.get("obs", "").strip()), erros


def _form_cliente(cliente):
    if request.method == "POST":
        dados, erros = _ler(request.form, cliente)
        if not erros:
            novo = cliente is None
            cliente = cliente or Cliente()
            for k, v in dados.items():
                setattr(cliente, k, v)
            if novo:
                S.add(cliente)
            try:
                S.commit()
                flash("Cliente salvo.", "ok")
                return redirect(url_for(".ver", id=cliente.id))
            except IntegrityError:
                S.rollback()
                erros.append("Já existe um cliente com este CPF.")
        for e in erros:
            flash(e, "erro")
        f = request.form
    else:
        f = {} if cliente is None else dict(
            nome=cliente.nome, cpf=cliente.cpf or "", telefone=cliente.telefone,
            nascimento=cliente.nascimento.isoformat() if cliente.nascimento else "",
            endereco=cliente.endereco, obs=cliente.obs)
    return render_template("cliente_form.html", f=f, cliente=cliente)


@bp.route("/clientes/novo", methods=["GET", "POST"])
def novo():
    return _form_cliente(None)


@bp.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    return _form_cliente(_cliente(id))


@bp.get("/clientes/<int:id>")
def ver(id):
    return render_template("cliente_ver.html", c=_cliente(id))


@bp.post("/clientes/<int:id>/excluir")
def excluir(id):
    c = _cliente(id)
    S.delete(c)
    S.commit()
    flash("Cliente excluído.", "ok")
    return redirect(url_for(".lista"))


# ---------- receitas ----------
def _receita(id) -> Receita:
    r = S.get(Receita, id)
    if not r:
        abort(404)
    return r


def _form_receita(cliente, receita):
    if request.method == "POST":
        try:
            data = util.parse_data(request.form.get("data")) or util.hoje()
        except ValueError:
            flash("Data da consulta inválida.", "erro")
            return render_template("receita_form.html", c=cliente, f=request.form, receita=receita, GRAUS=GRAUS)
        dados = {f"{o}_{k}": request.form.get(f"{o}_{k}", "").strip()[:20] for o in ("od", "oe") for k in GRAUS}
        receita = receita or Receita(cliente_id=cliente.id)
        receita.data, receita.obs = data, request.form.get("obs", "").strip()[:300]
        for k, v in dados.items():
            setattr(receita, k, v)
        S.add(receita)
        S.commit()
        flash("Receita salva.", "ok")
        return redirect(url_for(".ver", id=cliente.id))
    f = {"data": util.hoje().isoformat()} if receita is None else {
        "data": receita.data.isoformat(), "obs": receita.obs,
        **{f"{o}_{k}": getattr(receita, f"{o}_{k}") for o in ("od", "oe") for k in GRAUS}}
    return render_template("receita_form.html", c=cliente, f=f, receita=receita, GRAUS=GRAUS)


@bp.route("/clientes/<int:id>/receitas/nova", methods=["GET", "POST"])
def receita_nova(id):
    return _form_receita(_cliente(id), None)


@bp.route("/receitas/<int:id>/editar", methods=["GET", "POST"])
def receita_editar(id):
    r = _receita(id)
    return _form_receita(r.cliente, r)


@bp.post("/receitas/<int:id>/excluir")
def receita_excluir(id):
    r = _receita(id)
    cid = r.cliente_id
    S.delete(r)
    S.commit()
    flash("Receita excluída.", "ok")
    return redirect(url_for(".ver", id=cid))
