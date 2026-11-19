"""Exportar e importar dados em JSON.

Importa o formato do sistema antigo (um arquivo HTML) e o formato novo.
A importação é "mesclar": rodar o mesmo arquivo duas vezes NÃO duplica nada.
"""
from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

import util
from modelos import GRAUS, Cliente, Pagamento, Receita, Venda

CAMPOS_RX = [f"{o}_{k}" for o in ("od", "oe") for k in GRAUS]


def exportar(s) -> dict:
    clientes = s.scalars(select(Cliente).options(
        selectinload(Cliente.receitas),
        selectinload(Cliente.vendas).selectinload(Venda.pagamentos)).order_by(Cliente.id)).all()
    iso = lambda d: d.isoformat() if d else None
    return {"versao": 2, "exportado_em": iso(util.hoje()), "clientes": [{
        "nome": c.nome, "cpf": c.cpf, "telefone": c.telefone, "nascimento": iso(c.nascimento),
        "endereco": c.endereco, "obs": c.obs,
        "receitas": [{"data": iso(r.data), "obs": r.obs, **{k: getattr(r, k) for k in CAMPOS_RX}} for r in c.receitas],
        "vendas": [{
            "descricao": v.descricao, "valor": v.valor, "data": iso(v.data),
            "entrega_prevista": iso(v.entrega_prevista), "entregue_em": iso(v.entregue_em),
            "pagamentos": [{"valor": p.valor, "forma": p.forma, "data": iso(p.data)} for p in v.pagamentos],
        } for v in c.vendas],
    } for c in clientes]}


# ---------- leitura tolerante ----------
def _txt(v, n):
    return str(v if v is not None else "").strip()[:n]


def _data(v):
    try:
        return util.parse_data(v)
    except ValueError:
        return None


def _cent(v):
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def _do_antigo(d: dict) -> list:
    """Converte o JSON do sistema antigo para a estrutura nova (clientes com receitas e vendas)."""
    vendas = {}
    for v in d.get("vendas") or []:
        vendas.setdefault(v.get("clienteId"), []).append(v)
    saida = []
    for c in d.get("clientes") or []:
        rx = c.get("rx") or {}
        receita = {}
        for o in ("od", "oe"):
            for k in GRAUS:
                receita[f"{o}_{k}"] = _txt((rx.get(o) or {}).get(k), 20)
        receitas = []
        if any(receita.values()):
            receitas.append({**receita, "data": c.get("ultimaConsulta") or c.get("criado"), "obs": ""})
        lista_v = []
        for v in vendas.get(c.get("id"), []):
            try:
                valor = round(float(v.get("valor") or 0) * 100)
                pago = round(float(v.get("pago") or 0) * 100)
            except (TypeError, ValueError):
                continue
            data = _data(v.get("data")) or util.hoje()
            prevista = _data(v.get("entrega"))
            # vendas antigas já entregues não devem aparecer como "entrega pendente"
            entregue = None if (prevista and prevista >= util.hoje()) else (prevista or data)
            lista_v.append({
                "descricao": v.get("desc"), "valor": valor, "data": data.isoformat(),
                "entrega_prevista": prevista.isoformat() if prevista else None,
                "entregue_em": entregue.isoformat() if entregue else None,
                "pagamentos": [{"valor": pago, "forma": v.get("forma") or "Outro", "data": data.isoformat()}] if pago > 0 else [],
            })
        saida.append({"nome": c.get("nome"), "cpf": c.get("cpf"), "telefone": c.get("tel"),
                      "nascimento": c.get("nasc"), "endereco": c.get("end"), "obs": c.get("obs"),
                      "receitas": receitas, "vendas": lista_v})
    return saida


def importar(s, dados) -> Counter:
    if not isinstance(dados, dict) or not isinstance(dados.get("clientes"), list):
        raise ValueError("Arquivo inválido. Use um arquivo exportado por este sistema ou pelo sistema antigo.")
    lista = dados["clientes"] if dados.get("versao") == 2 else _do_antigo(dados)

    existentes = s.scalars(select(Cliente).options(
        selectinload(Cliente.receitas),
        selectinload(Cliente.vendas).selectinload(Venda.pagamentos))).all()
    por_cpf = {c.cpf: c for c in existentes if c.cpf}
    por_nome_tel = {(util.norm(c.nome), util.so_digitos(c.telefone)): c for c in existentes}
    res = Counter()

    for d in lista:
        if not isinstance(d, dict) or not _txt(d.get("nome"), 120):
            res["ignorados"] += 1
            continue
        nome, tel = _txt(d.get("nome"), 120), _txt(d.get("telefone"), 30)
        cpf, obs = util.so_digitos(d.get("cpf")) or None, _txt(d.get("obs"), 2000)
        if cpf and len(cpf) != 11:                       # CPF digitado incompleto: não perde a informação
            obs = (obs + f"\nCPF informado: {d.get('cpf')}").strip()
            cpf = None
        c = por_cpf.get(cpf) if cpf else None
        if c is None:
            achado = por_nome_tel.get((util.norm(nome), util.so_digitos(tel)))
            if achado and (not cpf or not achado.cpf):
                c = achado
        if c is None:
            c = Cliente(nome=nome, cpf=cpf, telefone=tel, nascimento=_data(d.get("nascimento")),
                        endereco=_txt(d.get("endereco"), 200), obs=obs)
            s.add(c)
            s.flush()
            res["clientes_novos"] += 1
            if cpf:
                por_cpf[cpf] = c
            por_nome_tel[(util.norm(nome), util.so_digitos(tel))] = c

        vistas = {(r.data, *[getattr(r, k) for k in CAMPOS_RX]) for r in c.receitas}
        for r in d.get("receitas") or []:
            graus = {k: _txt(r.get(k), 20) for k in CAMPOS_RX}
            data = _data(r.get("data")) or util.hoje()
            chave = (data, *graus.values())
            if chave in vistas:
                continue
            vistas.add(chave)
            c.receitas.append(Receita(data=data, obs=_txt(r.get("obs"), 300), **graus))
            res["receitas_novas"] += 1

        vistas = {(v.data, util.norm(v.descricao), v.valor) for v in c.vendas}
        for v in d.get("vendas") or []:
            desc, valor, data = _txt(v.get("descricao"), 200), _cent(v.get("valor")), _data(v.get("data")) or util.hoje()
            if not desc:
                res["ignorados"] += 1
                continue
            chave = (data, util.norm(desc), valor)
            if chave in vistas:
                res["vendas_repetidas"] += 1
                continue
            vistas.add(chave)
            nova = Venda(descricao=desc, valor=valor, data=data,
                         entrega_prevista=_data(v.get("entrega_prevista")), entregue_em=_data(v.get("entregue_em")))
            for p in v.get("pagamentos") or []:
                if _cent(p.get("valor")) > 0:
                    nova.pagamentos.append(Pagamento(valor=_cent(p.get("valor")), forma=_txt(p.get("forma"), 30) or "Outro",
                                                     data=_data(p.get("data")) or data))
            c.vendas.append(nova)
            res["vendas_novas"] += 1
    s.commit()
    return res
