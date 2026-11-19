"""Login opcional por senha única + proteção contra formulários forjados (CSRF).

Offline (só no seu computador) não precisa de senha. Online, defina OTICA_SENHA.
"""
import hmac
import os
import secrets
import time
from datetime import timedelta

from flask import abort, flash, redirect, render_template, request, session, url_for

import banco

LIVRES = {"sistema.login", "static"}
_falhas = {}            # ip -> (quantidade, instante da última falha)
MAX_FALHAS, BLOQUEIO = 5, 300


def senha() -> str:
    return os.getenv("OTICA_SENHA", "")


def token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def _chave_secreta() -> str:
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    arq = banco.DADOS / "segredo.key"
    banco.DADOS.mkdir(parents=True, exist_ok=True)
    if not arq.exists():
        arq.write_text(secrets.token_hex(32))
    return arq.read_text().strip()


def _verificar():
    if request.method == "POST":
        enviado = request.form.get("csrf", "")
        if not hmac.compare_digest(session.get("csrf", ""), enviado):
            abort(400, "A página ficou aberta por muito tempo. Volte, recarregue e tente de novo.")
    if senha() and not session.get("logado") and request.endpoint not in LIVRES:
        return redirect(url_for("sistema.login", prox=request.path))


def _destino_seguro(prox: str) -> str:
    return prox if prox.startswith("/") and not prox.startswith(("//", "/\\")) else url_for("sistema.inicio")


def tentar_login():
    ip = request.remote_addr or "?"
    qtd, quando = _falhas.get(ip, (0, 0))
    if qtd >= MAX_FALHAS and time.time() - quando < BLOQUEIO:
        flash("Muitas tentativas erradas. Aguarde alguns minutos.", "erro")
        return None
    if hmac.compare_digest(request.form.get("senha", ""), senha()):
        _falhas.pop(ip, None)
        session.clear()
        session["logado"] = True
        session.permanent = True
        return redirect(_destino_seguro(request.args.get("prox", "/")))
    _falhas[ip] = (qtd + 1 if time.time() - quando < BLOQUEIO else 1, time.time())
    time.sleep(1)
    flash("Senha incorreta.", "erro")
    return None


def iniciar(app):
    app.secret_key = _chave_secreta()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SEGURO") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    app.jinja_env.globals["csrf_token"] = token
    app.jinja_env.globals["com_senha"] = lambda: bool(senha())
    app.before_request(_verificar)
