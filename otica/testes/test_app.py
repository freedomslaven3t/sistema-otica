"""Testes do Sistema Ótica. Rodar na pasta do projeto:  python -m unittest discover -s testes -v

Usam um banco temporário. Para testar no PostgreSQL, defina TEST_DATABASE_URL (use um banco vazio de teste).
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import timedelta

TMP = tempfile.mkdtemp()
os.environ["DADOS_DIR"] = TMP
os.environ.pop("OTICA_SENHA", None)
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import banco, util                      # noqa: E402
from app import app                     # noqa: E402
from modelos import Base, Cliente, Venda  # noqa: E402


class Base_(unittest.TestCase):
    def setUp(self):
        banco.Sessao.remove()
        Base.metadata.drop_all(banco.engine)
        Base.metadata.create_all(banco.engine)
        self.c = app.test_client()
        with self.c.session_transaction() as s:
            s["csrf"] = "tok"

    def post(self, url, **dados):
        return self.c.post(url, data={"csrf": "tok", **dados}, follow_redirects=True)

    def texto(self, r):
        return r.get_data(as_text=True)

    def cliente(self, nome="Maria Souza", **extra):
        self.post("/clientes/novo", nome=nome, **extra)
        return banco.Sessao.query(Cliente).filter_by(nome=nome).one()


class TestUtil(unittest.TestCase):
    def test_centavos(self):
        self.assertEqual(util.para_centavos("1.234,56"), 123456)
        self.assertEqual(util.para_centavos("1234.56"), 123456)
        self.assertEqual(util.para_centavos("1.500"), 150000)      # milhar, não 1,5
        self.assertEqual(util.para_centavos("12.5"), 1250)
        self.assertEqual(util.para_centavos("R$ 99,9"), 9990)
        self.assertEqual(util.para_centavos("0,1") + util.para_centavos("0,2"), 30)   # sem erro de ponto flutuante
        for ruim in ("", "abc", "-5", "1,2,3"):
            with self.assertRaises(ValueError):
                util.para_centavos(ruim)

    def test_brl_e_whatsapp(self):
        self.assertEqual(util.brl(123456), "R$ 1.234,56")
        self.assertEqual(util.brl(0), "R$ 0,00")
        self.assertEqual(util.whatsapp("(65) 99999-8888"), "https://wa.me/5565999998888")
        self.assertIsNone(util.whatsapp("123"))

    def test_busca_sem_acento(self):
        self.assertEqual(util.norm("José AÇÃO"), "jose acao")

    def test_hoje_usa_fuso_da_loja(self):
        os.environ["FUSO"] = "Pacific/Kiritimati"       # UTC+14: quase sempre um dia à frente do Brasil
        d1 = util.hoje()
        os.environ["FUSO"] = "Pacific/Pago_Pago"        # UTC-11
        d2 = util.hoje()
        os.environ.pop("FUSO")
        self.assertGreaterEqual((d1 - d2).days, 1)


class TestClientes(Base_):
    def test_criar_buscar_e_cpf_duplicado(self):
        c = self.cliente("José Ação", cpf="123.456.789-09", telefone="(65) 99999-8888")
        self.assertEqual(c.cpf, "12345678909")
        self.assertIn("José Ação", self.texto(self.c.get("/clientes?q=jose")))        # sem acento
        self.assertIn("José Ação", self.texto(self.c.get("/clientes?q=99999")))       # por telefone
        self.assertIn("José Ação", self.texto(self.c.get("/clientes?q=12345678909"))) # por CPF
        r = self.post("/clientes/novo", nome="Outro", cpf="12345678909")
        self.assertIn("Já existe um cliente com este CPF", self.texto(r))
        self.assertEqual(banco.Sessao.query(Cliente).count(), 1)

    def test_validacoes(self):
        self.assertIn("Informe o nome", self.texto(self.post("/clientes/novo", nome="  ")))
        self.assertIn("11 números", self.texto(self.post("/clientes/novo", nome="X", cpf="123")))

    def test_receitas_mantem_historico(self):
        c = self.cliente()
        self.post(f"/clientes/{c.id}/receitas/nova", data="2024-01-10", od_esf="-1.00", oe_esf="-1.25")
        self.post(f"/clientes/{c.id}/receitas/nova", data="2025-02-20", od_esf="-1.50", oe_esf="-1.75")
        c = banco.Sessao.get(Cliente, c.id)
        self.assertEqual([r.od_esf for r in c.receitas], ["-1.50", "-1.00"])      # a antiga não foi sobrescrita
        self.assertEqual(c.ultima_consulta.isoformat(), "2025-02-20")

    def test_excluir_cliente_leva_vendas(self):
        c = self.cliente()
        self.post("/vendas/nova", cliente_id=c.id, descricao="Óculos", valor="500,00")
        self.post(f"/clientes/{c.id}/excluir")
        self.assertEqual(banco.Sessao.query(Cliente).count(), 0)
        self.assertEqual(banco.Sessao.query(Venda).count(), 0)

    def test_html_digitado_e_escapado(self):
        self.cliente("<script>alert(1)</script>")
        html = self.texto(self.c.get("/clientes"))
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class TestVendas(Base_):
    def test_entrada_pagamentos_e_quitacao(self):
        c = self.cliente()
        self.post("/vendas/nova", cliente_id=c.id, descricao="Óculos completo", valor="1.200,00", entrada="200,00", forma="Pix")
        v = banco.Sessao.query(Venda).one()
        self.assertEqual((v.valor, v.pago, v.saldo), (120000, 20000, 100000))
        r = self.post(f"/vendas/{v.id}/pagamentos", valor="2.000,00", forma="Pix")
        self.assertIn("maior que o saldo", self.texto(r))
        self.post(f"/vendas/{v.id}/pagamentos", valor="400,00", forma="Carnê")
        self.post(f"/vendas/{v.id}/pagamentos", valor="600,00", forma="Carnê")
        v = banco.Sessao.get(Venda, v.id)
        self.assertTrue(v.quitada)
        self.assertEqual(len(v.pagamentos), 3)

    def test_valor_e_entrada_invalidos(self):
        c = self.cliente()
        self.assertIn("inválido", self.texto(self.post("/vendas/nova", cliente_id=c.id, descricao="X", valor="abc")))
        self.assertIn("maior que o valor total", self.texto(self.post("/vendas/nova", cliente_id=c.id, descricao="X", valor="100", entrada="150")))
        self.assertEqual(banco.Sessao.query(Venda).count(), 0)

    def test_entrega_e_atraso(self):
        c = self.cliente()
        ontem = (util.hoje() - timedelta(days=1)).isoformat()
        self.post("/vendas/nova", cliente_id=c.id, descricao="Lente", valor="300", entrega_prevista=ontem)
        v = banco.Sessao.query(Venda).one()
        self.assertTrue(v.atrasada)
        self.assertIn("Lente", self.texto(self.c.get("/")))                            # aparece nas pendentes
        self.post(f"/vendas/{v.id}/entregar")
        v = banco.Sessao.get(Venda, v.id)
        self.assertFalse(v.atrasada)
        self.assertEqual(v.entregue_em, util.hoje())

    def test_filtros_e_sem_cliente(self):
        self.assertIn("Cadastre um cliente", self.texto(self.c.get("/vendas/nova", follow_redirects=True)))
        c = self.cliente()
        self.post("/vendas/nova", cliente_id=c.id, descricao="Quitada", valor="100", entrada="100")
        self.post("/vendas/nova", cliente_id=c.id, descricao="Pendente", valor="100")
        aberto = self.texto(self.c.get("/vendas?status=aberto"))
        self.assertIn("Pendente", aberto)
        self.assertNotIn("Quitada</td>", aberto)

    def test_redirecionamento_externo_bloqueado(self):
        c = self.cliente()
        self.post("/vendas/nova", cliente_id=c.id, descricao="X", valor="10")
        v = banco.Sessao.query(Venda).one()
        r = self.c.post(f"/vendas/{v.id}/entregar", data={"csrf": "tok", "voltar": "//evil.com"})
        self.assertNotIn("evil.com", r.headers["Location"])


class TestImportacao(Base_):
    ANTIGO = {
        "clientes": [
            {"id": 1, "nome": "Ana Lima", "cpf": "111.222.333-44", "tel": "(65) 98888-7777", "nasc": "1990-05-10",
             "end": "Rua A", "obs": "", "ultimaConsulta": "2023-03-01",
             "rx": {"od": {"esf": "-2.00", "cil": "", "eixo": "", "add": "", "dnp": ""}, "oe": {"esf": "-2.25"}}},
            {"id": 2, "nome": "Sem CPF", "cpf": "", "tel": "", "nasc": "", "end": "", "obs": "", "rx": {"od": {}, "oe": {}}},
        ],
        "vendas": [
            {"id": 1, "clienteId": 1, "desc": "Óculos", "valor": 450.5, "pago": 200, "forma": "Pix", "data": "2023-03-01", "entrega": "2023-03-10"},
            {"id": 2, "clienteId": 1, "desc": "Lente extra", "valor": 100, "pago": 0, "forma": "Dinheiro", "data": "2023-04-01", "entrega": ""},
        ],
        "seq": {"c": 2, "v": 2}, "ultimoBackup": None,
    }

    def importar(self, dados):
        return self.c.post("/backup/importar", data={"csrf": "tok", "arquivo": (io.BytesIO(json.dumps(dados).encode()), "a.json")},
                           content_type="multipart/form-data", follow_redirects=True)

    def test_importa_formato_antigo_sem_duplicar(self):
        r = self.importar(self.ANTIGO)
        self.assertIn("Importação concluída", self.texto(r))
        s = banco.Sessao
        self.assertEqual(s.query(Cliente).count(), 2)
        v = s.query(Venda).filter_by(descricao="Óculos").one()
        self.assertEqual((v.valor, v.pago), (45050, 20000))         # reais -> centavos
        self.assertIsNotNone(v.entregue_em)                          # venda antiga não vira "entrega pendente"
        ana = s.query(Cliente).filter_by(nome="Ana Lima").one()
        self.assertEqual(ana.receitas[0].od_esf, "-2.00")
        self.assertEqual(ana.receitas[0].data.isoformat(), "2023-03-01")
        for _ in range(2):                                           # importar de novo não duplica (clientes sem CPF também)
            self.importar(self.ANTIGO)
        self.assertEqual(s.query(Cliente).count(), 2)
        self.assertEqual(s.query(Venda).count(), 2)

    def test_exporta_e_reimporta_formato_novo(self):
        self.importar(self.ANTIGO)
        exportado = json.loads(self.c.get("/backup/json").data)
        self.assertEqual(exportado["versao"], 2)
        Base.metadata.drop_all(banco.engine); Base.metadata.create_all(banco.engine)
        banco.Sessao.remove()
        self.importar(exportado)
        self.assertEqual(banco.Sessao.query(Cliente).count(), 2)
        v = banco.Sessao.query(Venda).filter_by(descricao="Óculos").one()
        self.assertEqual((v.valor, v.pago), (45050, 20000))

    def test_arquivo_invalido(self):
        r = self.c.post("/backup/importar", data={"csrf": "tok", "arquivo": (io.BytesIO(b"isto nao e json"), "a.json")},
                        content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("Arquivo inválido", self.texto(r))
        self.assertIn("Arquivo inválido", self.texto(self.importar({"foo": 1})))


class TestPaginasEBackup(Base_):
    def test_todas_as_telas_abrem(self):
        c = self.cliente(telefone="65999990000")
        self.post("/vendas/nova", cliente_id=c.id, descricao="X", valor="10")
        v = banco.Sessao.query(Venda).one()
        for url in ("/", "/clientes", "/clientes/novo", f"/clientes/{c.id}", f"/clientes/{c.id}/editar",
                    f"/clientes/{c.id}/receitas/nova", "/vendas", "/vendas/nova", f"/vendas/{v.id}", f"/vendas/{v.id}/editar", "/backup"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/clientes/999").status_code, 404)

    def test_backup_do_banco(self):
        if not banco.SQLITE:
            self.skipTest("backup .db só existe no SQLite")
        self.cliente()
        r = self.c.get("/backup/banco")
        self.assertTrue(r.data.startswith(b"SQLite format 3"))
        banco._dia_do_backup = None
        banco.backup_diario()
        self.assertEqual(len(banco.listar_backups()), 1)


class TestSeguranca(Base_):
    def test_post_sem_token_e_barrado(self):
        r = self.c.post("/clientes/novo", data={"nome": "Hacker"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(banco.Sessao.query(Cliente).count(), 0)

    def test_login_com_senha(self):
        os.environ["OTICA_SENHA"] = "segredo123"
        try:
            c = app.test_client()
            self.assertEqual(c.get("/clientes").status_code, 302)                       # exige login
            self.assertIn("/login", c.get("/clientes").headers["Location"])
            c.get("/login")
            with c.session_transaction() as s:
                tok = s["csrf"]
            r = c.post("/login", data={"csrf": tok, "senha": "errada"})
            self.assertIn("Senha incorreta", r.get_data(as_text=True))
            r = c.post("/login?prox=//evil.com", data={"csrf": tok, "senha": "segredo123"})
            self.assertEqual(r.status_code, 302)
            self.assertNotIn("evil.com", r.headers["Location"])
            self.assertEqual(c.get("/clientes").status_code, 200)
        finally:
            os.environ.pop("OTICA_SENHA")
            from seguranca import _falhas
            _falhas.clear()


if __name__ == "__main__":
    unittest.main()
