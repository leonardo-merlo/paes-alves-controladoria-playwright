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

# Unidades da Justiça Federal em Minas Gerais, pela origem (4 últimos dígitos do
# CNJ). O TRF6 foi criado em 2022 e assumiu Minas, que até então era do TRF1 —
# então processo mineiro antigo nasceu numerado 4.01 e hoje quem cuida dele é o
# TRF6. A origem identifica a UNIDADE e não muda com a criação do tribunal.
#
# Medido em 16/08/2026: a origem 3821 (Vara Cível e JEF Adjunto de Muriaé)
# aparece nos dois — 4.01 em 2020, 4.06 de 2023 em diante — e o processo
# 1001571-06.2020.4.01.3821 foi encontrado no eProc do TRF6 com 6 documentos,
# depois de uma rodada inteira dado como "sistema não implementado".
#
# Lista curta de propósito: só entra origem com evidência. Unidade mineira ainda
# não vista continua caindo em "sem extrator", igual a hoje — nada piora, e o
# painel agora mostra "TRF1", que é a pista para alguém reparar.
ORIGENS_JF_MINAS = {"3821"}  # Muriaé

# Como cada sistema se chama para quem não é programador. Aparece na janela do
# agente e no painel. O espelho disto em TypeScript vive em lib/cnj.ts do painel —
# mexeu aqui, mexa lá.
NOME_SISTEMA = {
    "pje_tjmg":       "PJe TJMG",
    "pje_tjmg_2inst": "RUPE (TJMG 2ª inst.)",
    "eproc_tjmg":     "eProc TJMG",
    "pje_tjrj":       "PJe TJRJ",
    "eproc_trf2":     "eProc TRF2",
    "eproc_trf6":     "eProc JFMG (1ª inst.)",
    "eproc_trf6_2g":  "eProc TRF6 (2ª inst.)",
}


def nome_sistema(sistema: str) -> str:
    """
    Nome legível do sistema. `nao_mapeado_J4_TT01` vira 'TRF1'.

    Na Justiça Federal o código do tribunal É o número do TRF, então dá para
    nomear sem tabela. "tribunal 4.01" não dizia nada a quem lê o painel.
    """
    if sistema in NOME_SISTEMA:
        return NOME_SISTEMA[sistema]
    m = re.match(r"^nao_mapeado_J(\d)_TT(\d{2})$", sistema)
    if m:
        segmento, tribunal = m.group(1), m.group(2)
        if segmento == "4":
            return f"TRF{int(tribunal)}"
        return f"tribunal {segmento}.{tribunal}"
    return sistema

# A que tribunal cada sistema pertence. Serve para impedir que o rótulo vindo do
# e-mail atravesse um processo de um tribunal para outro — ver `rotear`.
TRIBUNAL_DO_SISTEMA = {
    "pje_tjmg":       ("8", "13"),
    "pje_tjmg_2inst": ("8", "13"),
    "eproc_tjmg":     ("8", "13"),
    "pje_tjrj":       ("8", "19"),
    "eproc_trf2":     ("4", "02"),
    "eproc_trf6":     ("4", "06"),
    "eproc_trf6_2g":  ("4", "06"),
}


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


def motivo_sem_extrator(numero_cnj: str) -> str:
    """
    O que gravar em `motivo_ignorado` quando não há extrator. Função pura.

    Existe porque "Sistema não implementado" é um beco sem saída: quem lê fecha a
    tela e segue. O processo 1001571-06.2020.4.01.3821 passou rodadas assim, e
    estava o tempo todo no eProc do TRF6 — a mensagem é que não dizia isso.
    Para o TRF1 a mensagem passa a ensinar a conferência, com a origem na mão.
    """
    info = rotear(numero_cnj)
    nome = nome_sistema(info.sistema)
    if info.tribunal == "01" and info.segmento == SEGMENTO["4"]:
        return (
            f"{nome} não tem extrator. Se este processo for mineiro e anterior a "
            f"2022, ele provavelmente está no eProc do TRF6 — o TRF6 assumiu Minas "
            f"naquele ano. Confira lá e, se estiver, avise: basta acrescentar a "
            f"origem {info.origem} na lista de unidades mineiras."
        )
    return f"Sistema não implementado ({nome})"


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

    # TJMG: o 1º dígito do sequencial distingue eProc de PJe. É a mesma regra da
    # skill do Gmail. Dígito fora da tabela = não identificado (não adivinha).
    DIGITO_TJMG = {"1": "eproc_tjmg", "5": "pje_tjmg"}
    if chave == ("8", "13"):
        if origem == "0000":
            # origem 0000 é 2ª instância (RUPE) independente do dígito — o
            # sequencial da 2ª instância não segue a convenção 1/5 da 1ª.
            sistema_base = "pje_tjmg_2inst"
        else:
            sistema_base = DIGITO_TJMG.get(sequencial[0])
    elif chave == ("4", "06"):
        # Justiça Federal: todo processo 4.06 é do TRF6, qualquer que seja o
        # dígito. A tabela do dígito é do TJMG e aplicá-la aqui mandava
        # 1002485-27.2023.4.06.3821 para o eProc ESTADUAL — processo federal
        # procurado no tribunal de Minas, que nunca ia achar. Errou 3x por
        # rodada, em três rodadas seguidas, até ser medido em 15/08/2026.
        sistema_base = "eproc_trf6"
    elif chave == ("4", "01") and origem in ORIGENS_JF_MINAS:
        # Processo mineiro numerado antes de o TRF6 existir. Ver ORIGENS_JF_MINAS.
        sistema_base = "eproc_trf6"

    if not sistema_base:
        sistema = f"nao_mapeado_J{j}_TT{tt}"
        url = ""
        implementado = False
    else:
        sistema = sistema_base
        url = URLS.get(sistema, "")
        implementado = sistema in IMPLEMENTADOS

    # Override explícito vindo do banco (coluna `sistema`): a skill do Gmail
    # deriva isso do texto da Vara — ausência da palavra "vara" = 2ª instância
    # (pje_2g) — sinal que o CNJ sozinho não tem como revelar, então SEMPRE vence.
    # Hints fracos ('pje', 'eproc') são o default genérico da skill quando ela
    # não tem certeza do 1º dígito e não devem sobrepor a tabela de dígito acima.
    #
    # LIMITE do override: o número do processo manda no TRIBUNAL, o rótulo só
    # escolhe o sistema DENTRO dele. Sem esta trava, 1001571-06.2020.4.01.3821
    # (TRF1) rotulado 'pje_2g' ia parar no RUPE, que é do TJMG — processo federal
    # procurado no tribunal estadual, 3 tentativas por rodada, sempre em vão.
    # Bloqueado, ele cai em "sistema não implementado", que é a verdade: o TRF1
    # não tem extrator. Vira aviso honesto no painel em vez de erro repetido.
    _ALIAS = {"pje": "pje_tjmg", "pje_2g": "pje_tjmg_2inst", "eproc": "eproc_tjmg"}
    _ALIAS_FRACOS = {"pje", "eproc"}
    hint_norm = _ALIAS.get(sistema_hint, sistema_hint) if sistema_hint else None
    eh_digito_deterministico = (
        chave in (("8", "13"), ("4", "06"))
        and sistema_base is not None
        and sistema_hint in _ALIAS_FRACOS
    )
    mesmo_tribunal = TRIBUNAL_DO_SISTEMA.get(hint_norm) == chave
    if (hint_norm and hint_norm in IMPLEMENTADOS and mesmo_tribunal
            and not eh_digito_deterministico):
        sistema = hint_norm
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
