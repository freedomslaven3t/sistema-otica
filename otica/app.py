"""Sistema Ótica. Para abrir: python app.py  (ou clique em iniciar.bat)"""
import os
import sys
import threading
import webbrowser

from flask import Flask, render_template

import banco
import seguranca
import util


def criar_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024        # arquivos de importação até 20 MB
    seguranca.iniciar(app)
    banco.criar_tabelas()
    app.before_request(banco.backup_diario)
    app.teardown_appcontext(lambda erro: banco.Sessao.remove())
    app.jinja_env.filters.update(brl=util.brl, dbr=util.dbr, campo=util.valor_campo)
    app.jinja_env.globals.update(hoje=util.hoje, FORMAS=util.FORMAS, whatsapp=util.whatsapp)

    from rotas import clientes, sistema, vendas
    for modulo in (sistema, clientes, vendas):
        app.register_blueprint(modulo.bp)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def erro(e):
        msg = {404: "Página não encontrada.", 413: "Arquivo grande demais (máximo 20 MB)."}.get(e.code, e.description)
        return render_template("erro.html", msg=msg), e.code

    return app


app = criar_app()

if __name__ == "__main__":
    host, porta = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "5000"))
    local = host in ("127.0.0.1", "localhost")
    if not local and not seguranca.senha():
        sys.exit("ERRO: para aceitar acesso de outros computadores (HOST=%s) defina a senha em OTICA_SENHA." % host)
    if os.getenv("DEBUG") == "1":
        app.run(host=host, port=porta, debug=True)
    else:
        from waitress import serve
        if local and os.getenv("ABRIR_NAVEGADOR", "1") == "1":
            threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{porta}")).start()
        print(f"Sistema Ótica rodando em http://localhost:{porta}  (Ctrl+C para encerrar)")
        serve(app, host=host, port=porta, threads=8)
