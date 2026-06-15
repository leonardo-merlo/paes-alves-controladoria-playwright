"""
extrator_dispatch.py — Mapeia sistema → função extratora.

Quando um novo sistema for implementado, basta adicionar aqui.
"""

from pje_extractor import extrair_processo as _extrair_pje_tjmg
from eproc_extractor import extrair_processo as _extrair_eproc_tjmg
from rupe_extractor import extrair_processo as _extrair_rupe

# sistemas implementados
EXTRATORES = {
    "pje_tjmg":       _extrair_pje_tjmg,
    "eproc_tjmg":     _extrair_eproc_tjmg,
    "eproc_trf6":     _extrair_eproc_tjmg,  # mesmo extrator — host resolvido pelo CNJ
    "pje_tjmg_2inst": _extrair_rupe,        # 2ª instância TJMG (RUPE)
}

# sistemas conhecidos mas ainda não implementados
SISTEMAS_PENDENTES = {
    "pje_tjrj":       "PJE TJRJ",
    "eproc_trf2":     "eProc TRF2",
}


def obter_extrator(sistema: str):
    """Retorna a função extratora ou None se não implementado."""
    return EXTRATORES.get(sistema)


def esta_implementado(sistema: str) -> bool:
    return sistema in EXTRATORES


def descricao_pendente(sistema: str) -> str:
    return SISTEMAS_PENDENTES.get(sistema, sistema)
