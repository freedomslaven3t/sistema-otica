"""Vendas, pagamentos e entregas."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import banco
import util
from modelos import Cliente, Pagamento, Venda

bp = Blueprint("vendas", __name__)
S = banco.Sessao


def _venda(id) -> Venda:
    v = S.get(Venda, id)
    if not v:
        abort(404)
    return v


def _valor(texto, rotulo, erros, obrigatorio=True):
    if not str(texto or "").strip() and not obrigatorio:
        return 0
    try:
        return util.para_centavos(texto)
    except ValueError:
        erros.append(f"{rotulo} inválido. Use números, por exemplo 1.250,00.")
        return 0


def _data(texto, rotulo, erros, padrao=None):
    try:
        return util.parse_data(texto) or padrao
    except ValueError:
        erros.append(f"{rotulo} inválida.")
        return padrao


@bp.get("/vendas")
def lista():
    q, status = util.norm(request.args.get("q", "")).strip(), request.args.get("status", "")
    todas = S.scalars(select(Venda).options(selectinload(Venda.pagamentos), selectinload(Venda.cliente))
                      .order_by(Venda.data.desc(), Venda.id.desc())).all()

    def bate(v):
        if q and not ((q.isdigit() and int(q) == v.id) or q in util.norm(v.cliente.nome) or q in util.norm(v.descricao)):
            return False
        return {"aberto": not v.quitada, "quitadas": v.quitada, "entrega": not v.entregue_em}.get(status, True)

    achadas = [v for v in todas if bate(v)]
    return render_template("vendas.html", vendas=achadas, q=request.args.get("q", ""), status=status,
                           total=sum(v.valor for v in achadas), a_receber=sum(v.saldo for v in achadas))


def _form_venda(venda):
    clientes = S.scalars(select(Cliente)).all()
    clientes.sort(key=lambda c: util.norm(c.nome))
    if not clientes:
        flash("Cadastre um cliente primeiro.", "erro")
        return redirect(url_for("clientes.novo"))

    if request.method == "POST":
        f, erros = request.form, []
        cliente = S.get(Cliente, int(f["cliente_id"])) if f.get("cliente_id", "").isdigit() else None
        if not cliente:
            erros.append("Escolha o cliente.")
        desc = " ".join(f.get("descricao", "").split())
        if not desc:
            erros.append("Descreva a venda (armação, lentes, serviço...).")
        valor = _valor(f.get("valor"), "Valor total", erros)
        if valor <= 0 and "Valor total inválido" not in " ".join(erros):
            erros.append("O valor total precisa ser maior que zero.")
        data = _data(f.get("data"), "Data da venda", erros, util.hoje())
        prevista = _data(f.get("entrega_prevista"), "Previsão de entrega", erros)
        entrada = 0 if venda else _valor(f.get("entrada"), "Entrada", erros, obrigatorio=False)
        if entrada > valor:
            erros.append("A entrada é maior que o valor total.")
        if not erros:
            novo = venda is None
            venda = venda or Venda()
            venda.cliente_id, venda.descricao, venda.valor = cliente.id, desc[:200], valor
            venda.data, venda.entrega_prevista = data, prevista
            if novo and entrada > 0:
                venda.pagamentos.append(Pagamento(valor=entrada, forma=f.get("forma") or "Pix", data=data))
            S.add(venda)
            S.commit()
            flash("Venda salva.", "ok")
            return redirect(url_for(".ver", id=venda.id))
        for e in erros:
            flash(e, "erro")
        dados = f
    elif venda:
        dados = dict(cliente_id=venda.cliente_id, descricao=venda.descricao, valor=util.valor_campo(venda.valor),
                     data=venda.data.isoformat(),
                     entrega_prevista=venda.entrega_prevista.isoformat() if venda.entrega_prevista else "")
    else:
        dados = dict(cliente_id=request.args.get("cliente_id", ""), data=util.hoje().isoformat())
    return render_template("venda_form.html", f=dados, venda=venda, clientes=clientes)


@bp.route("/vendas/nova", methods=["GET", "POST"])
def nova():
    return _form_venda(None)


@bp.route("/vendas/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    return _form_venda(_venda(id))


@bp.get("/vendas/<int:id>")
def ver(id):
    return render_template("venda_ver.html", v=_venda(id))


@bp.post("/vendas/<int:id>/excluir")
def excluir(id):
    v = _venda(id)
    cid = v.cliente_id
    S.delete(v)
    S.commit()
    flash("Venda excluída.", "ok")
    return redirect(url_for("clientes.ver", id=cid))


@bp.post("/vendas/<int:id>/pagamentos")
def pagar(id):
    v, erros = _venda(id), []
    valor = _valor(request.form.get("valor"), "Valor do pagamento", erros)
    data = _data(request.form.get("data"), "Data do pagamento", erros, util.hoje())
    if not erros and valor <= 0:
        erros.append("O pagamento precisa ser maior que zero.")
    if not erros and valor > v.saldo:
        erros.append(f"O pagamento é maior que o saldo em aberto ({util.brl(v.saldo)}).")
    if erros:
        for e in erros:
            flash(e, "erro")
    else:
        v.pagamentos.append(Pagamento(valor=valor, forma=request.form.get("forma") or "Pix", data=data))
        S.commit()
        flash("Pagamento registrado." if v.saldo else "Pagamento registrado. Venda quitada!", "ok")
    return redirect(url_for(".ver", id=id))


@bp.post("/pagamentos/<int:id>/excluir")
def pagamento_excluir(id):
    p = S.get(Pagamento, id)
    if not p:
        abort(404)
    vid = p.venda_id
    S.delete(p)
    S.commit()
    flash("Pagamento excluído.", "ok")
    return redirect(url_for(".ver", id=vid))


@bp.post("/vendas/<int:id>/entregar")
def entregar(id):
    v = _venda(id)
    v.entregue_em = util.hoje()
    S.commit()
    flash("Venda marcada como entregue.", "ok")
    voltar = request.form.get("voltar", "")
    seguro = voltar.startswith("/") and not voltar.startswith(("//", "/\\"))
    return redirect(voltar if seguro else url_for(".ver", id=id))


@bp.post("/vendas/<int:id>/desfazer-entrega")
def desfazer_entrega(id):
    v = _venda(id)
    v.entregue_em = None
    S.commit()
    flash("Entrega desfeita.", "ok")
    return redirect(url_for(".ver", id=id))
