import re
from dataclasses import dataclass


CNJ_PATTERN = re.compile(
    r'^(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})$'
)

# J (segmento de justiça) → descrição
SEGMENTO = {
    "1": "STF",
    "2": "CNJ",
    "3": "STJ",
    "4": "Federal TRF",
    "5": "Trabalhista",
    "6": "Eleitoral",
    "7": "Militar Federal",
    "8": "Estadual",
    "9": "Militar Estadual",
}

# (J, TT) → sistema base
SISTEMAS = {
    ("8", "13"): "pje_tjmg",
    ("8", "19"): "pje_tjrj",
    ("4", "02"): "eproc_trf2",
    ("4", "06"): "eproc_trf6",
}

URLS = {
    "pje_tjmg":        "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam",
    "eproc_tjmg":      "https://eproc1g.tjmg.jus.br/eproc/",
    "pje_tjmg_2inst":  "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe",
    "pje_tjrj":        "https://tjrj.pje.jus.br/",
    "eproc_trf2":      "https://eproc.trf2.jus.br/",
    "eproc_trf6":      "https://eproc1g.trf6.jus.br/eproc/",   # JFMG — 1ª instância federal
    "eproc_trf6_2g":   "https://eproc2g.trf6.jus.br/eproc/",   # TRF6 — 2ª instância federal
}

IMPLEMENTADOS = {"pje_tjmg", "eproc_tjmg", "eproc_trf6", "eproc_trf6_2g", "pje_tjmg_2inst"}


@dataclass
class CNJInfo:
    numero_cnj: str
    sequencial: str
    digito: str
    ano: str
    segmento: str
    tribunal: str
    origem: str
    sistema: str
    url: str
    implementado: bool
    erro: str | None = None


def rotear(numero_cnj: str, sistema_hint: str | None = None) -> CNJInfo:
    numero_cnj = numero_cnj.strip()
    m = CNJ_PATTERN.match(numero_cnj)
    if not m:
        return CNJInfo(
            numero_cnj=numero_cnj,
            sequencial="", digito="", ano="",
            segmento="", tribunal="", origem="",
            sistema="desconhecido", url="",
            implementado=False,
            erro=f"Formato CNJ inválido: '{numero_cnj}'",
        )

    sequencial, digito, ano, j, tt, origem = m.groups()

    chave = (j, tt)
    sistema_base = SISTEMAS.get(chave)

    # TJMG: PJE, eProc e RUPE compartilham o mesmo segmento .8.13.
    # origem 0000 = tribunal/2ª instância (RUPE). Caso contrário, o primeiro
    # dígito do sequencial define o sistema: 1xxxxxx → eProc | demais → PJE.
    if chave == ("8", "13"):
        if origem == "0000":
            sistema_base = "pje_tjmg_2inst"
        else:
            sistema_base = "eproc_tjmg" if sequencial.startswith("1") else "pje_tjmg"

    # TRF6: origem 0000 = TRF6 2ª instância (eproc2g) | demais = JFMG 1ª instância (eproc1g)
    if chave == ("4", "06"):
        sistema_base = "eproc_trf6_2g" if origem == "0000" else "eproc_trf6"

    if not sistema_base:
        sistema = f"nao_mapeado_J{j}_TT{tt}"
        url = ""
        implementado = False
    else:
        sistema = sistema_base
        url = URLS.get(sistema, "")
        implementado = sistema in IMPLEMENTADOS

    # Override explícito vindo do banco (coluna `sistema`): força um sistema
    # quando o CNJ sozinho não revela a instância — ex.: recurso em Câmara Cível
    # (origem != 0000) que tramita na 2ª instância (RUPE / pje_tjmg_2inst).
    if sistema_hint and sistema_hint in IMPLEMENTADOS:
        sistema = sistema_hint
        url = URLS.get(sistema, "")
        implementado = True

    return CNJInfo(
        numero_cnj=numero_cnj,
        sequencial=sequencial,
        digito=digito,
        ano=ano,
        segmento=SEGMENTO.get(j, j),
        tribunal=tt,
        origem=origem,
        sistema=sistema,
        url=url,
        implementado=implementado,
    )


def rotear_lista(numeros: list[str], hints: dict[str, str] | None = None) -> list[CNJInfo]:
    hints = hints or {}
    vistos: set[str] = set()
    resultado = []
    for n in numeros:
        n = n.strip()
        if not n or n.startswith("#"):
            continue
        if n in vistos:
            continue  # duplicata ignorada
        vistos.add(n)
        resultado.append(rotear(n, hints.get(n)))
    return resultado
