"""Funções pequenas de apoio: datas, dinheiro, busca e WhatsApp."""
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote
from zoneinfo import ZoneInfo

FORMAS = ["Pix", "Dinheiro", "Cartão débito", "Cartão crédito", "Carnê", "Outro"]


def hoje() -> date:
    """Data de hoje no fuso da loja (evita virar o dia às 21h, como acontecia com UTC)."""
    try:
        return datetime.now(ZoneInfo(os.getenv("FUSO", "America/Sao_Paulo"))).date()
    except Exception:
        return date.today()


def norm(texto) -> str:
    """Minúsculas e sem acento, para buscas."""
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def para_centavos(texto) -> int:
    """'1.234,56' ou '1234.56' -> 123456. Levanta ValueError se não for um valor válido."""
    t = str(texto or "").replace("R$", "").replace(" ", "").strip()
    if not t:
        raise ValueError("vazio")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", t):
        t = t.replace(".", "")          # 1.500 e 1.234.567 são milhares
    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValueError("inválido")
    if v < 0 or v >= Decimal("100000000"):
        raise ValueError("fora do limite")
    return int((v * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def brl(centavos) -> str:
    c = int(centavos or 0)
    reais = f"{abs(c) // 100:,}".replace(",", ".")
    return f"{'-' if c < 0 else ''}R$ {reais},{abs(c) % 100:02d}"


def valor_campo(centavos) -> str:
    """Centavos -> texto para preencher um campo de formulário ('1234,50')."""
    return "" if centavos is None else f"{int(centavos) // 100},{int(centavos) % 100:02d}"


def dbr(d) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def parse_data(texto):
    """'2026-11-14' -> date; vazio -> None; inválido -> ValueError."""
    t = str(texto or "").strip()
    return date.fromisoformat(t) if t else None


def whatsapp(telefone, mensagem="") -> str | None:
    d = so_digitos(telefone)
    if len(d) in (10, 11):
        d = "55" + d
    if not (len(d) in (12, 13) and d.startswith("55")):
        return None
    return f"https://wa.me/{d}" + (f"?text={quote(mensagem)}" if mensagem else "")
