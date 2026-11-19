"""Tabelas do banco. Dinheiro sempre em centavos (inteiro), nunca em decimal."""
from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import util

GRAUS = ("esf", "cil", "eixo", "add", "dnp")


class Base(DeclarativeBase):
    pass


class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    cpf: Mapped[Optional[str]] = mapped_column(String(11), unique=True)
    telefone: Mapped[str] = mapped_column(String(30), default="")
    nascimento: Mapped[Optional[date]]
    endereco: Mapped[str] = mapped_column(String(200), default="")
    obs: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[date] = mapped_column(default=util.hoje)

    receitas: Mapped[list["Receita"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan",
        order_by="Receita.data.desc(), Receita.id.desc()")
    vendas: Mapped[list["Venda"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan",
        order_by="Venda.data.desc(), Venda.id.desc()")

    @property
    def ultima_consulta(self):
        return self.receitas[0].data if self.receitas else None

    @property
    def comprado(self):
        return sum(v.valor for v in self.vendas)

    @property
    def em_aberto(self):
        return sum(v.saldo for v in self.vendas)


class Receita(Base):
    """Cada consulta gera uma receita nova: o histórico de graus não se perde."""
    __tablename__ = "receitas"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    data: Mapped[date] = mapped_column(default=util.hoje)
    od_esf: Mapped[str] = mapped_column(String(20), default="")
    od_cil: Mapped[str] = mapped_column(String(20), default="")
    od_eixo: Mapped[str] = mapped_column(String(20), default="")
    od_add: Mapped[str] = mapped_column(String(20), default="")
    od_dnp: Mapped[str] = mapped_column(String(20), default="")
    oe_esf: Mapped[str] = mapped_column(String(20), default="")
    oe_cil: Mapped[str] = mapped_column(String(20), default="")
    oe_eixo: Mapped[str] = mapped_column(String(20), default="")
    oe_add: Mapped[str] = mapped_column(String(20), default="")
    oe_dnp: Mapped[str] = mapped_column(String(20), default="")
    obs: Mapped[str] = mapped_column(String(300), default="")
    cliente: Mapped[Cliente] = relationship(back_populates="receitas")


class Venda(Base):
    __tablename__ = "vendas"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    descricao: Mapped[str] = mapped_column(String(200))
    valor: Mapped[int] = mapped_column(BigInteger)          # centavos
    data: Mapped[date] = mapped_column(default=util.hoje)
    entrega_prevista: Mapped[Optional[date]]
    entregue_em: Mapped[Optional[date]]

    cliente: Mapped[Cliente] = relationship(back_populates="vendas")
    pagamentos: Mapped[list["Pagamento"]] = relationship(
        back_populates="venda", cascade="all, delete-orphan",
        order_by="Pagamento.data, Pagamento.id")

    @property
    def pago(self):
        return sum(p.valor for p in self.pagamentos)

    @property
    def saldo(self):
        return max(0, self.valor - self.pago)

    @property
    def quitada(self):
        return self.saldo == 0

    @property
    def atrasada(self):
        return bool(not self.entregue_em and self.entrega_prevista and self.entrega_prevista < util.hoje())


class Pagamento(Base):
    """Entrada, parcela do carnê, acerto na retirada... cada pagamento é uma linha."""
    __tablename__ = "pagamentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    venda_id: Mapped[int] = mapped_column(ForeignKey("vendas.id", ondelete="CASCADE"), index=True)
    valor: Mapped[int] = mapped_column(BigInteger)          # centavos
    forma: Mapped[str] = mapped_column(String(30), default="Pix")
    data: Mapped[date] = mapped_column(default=util.hoje)
    venda: Mapped[Venda] = relationship(back_populates="pagamentos")
