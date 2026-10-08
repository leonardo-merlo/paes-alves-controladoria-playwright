"""test_rodada_recuperacao.py — a rodada inteira quando a conexão com o Chrome trava.

Extrator, Chrome e banco são falsos: o que se testa é a decisão da rodada.
Rodar: python test_rodada_recuperacao.py
"""

import asyncio

import runner
from cnj_router import CNJInfo

ERRO_CDP = ("Não foi possível conectar ao Chrome via CDP (http://127.0.0.1:9222): "
            "BrowserType.connect_over_cdp: Timeout 30000ms exceeded.")

EPROC = ["e1", "e2", "e3"]
PJE = ["p1", "p2"]


def _info(cnj: str, sistema: str) -> CNJInfo:
    return CNJInfo(numero_cnj=cnj, sequencial="", digito="", ano="", segmento="",
                   tribunal="", origem="", sistema=sistema, url="", implementado=True)


class Cenario:
    """Monta o mundo falso e roda uma rodada nele."""

    def __init__(self, travar: dict[str, int], chrome_vivo: bool = True):
        # quantas vezes cada CNJ falha na conexão antes de dar certo
        self.travar = dict(travar)
        self.chrome_vivo = chrome_vivo
        self.recuperacoes = 0
        self.marcados: list[tuple[list[str], str, str | None]] = []
        self.etapas: list[str] = []

    async def _processar_cnj(self, info, data_str, prefixo, data_corte=None):
        if self.travar.get(info.numero_cnj, 0) > 0:
            self.travar[info.numero_cnj] -= 1
            return {"erro": ERRO_CDP, "numero_cnj": info.numero_cnj, "duracao_extracao_s": 30}
        return {"numero_cnj": info.numero_cnj, "total_documentos": 3, "duracao_extracao_s": 1}

    async def _recuperar_conexao(self, host, url, *a, **k):
        self.recuperacoes += 1
        return {"mudas": ["pje.tjmg.jus.br"], "fechadas": ["pje.tjmg.jus.br"],
                "abriu": True, "agiu": True}

    async def _garantir_aba(self, *a, **k):
        return False

    def rodar(self):
        originais = (runner.processar_cnj, runner.chrome_responde, runner._get_abas_chrome,
                     runner.marcar_supabase, runner.gravar_duracao, runner.obs.registrar,
                     runner.chrome_saude.recuperar_conexao, runner.chrome_saude.garantir_aba)
        runner.processar_cnj = self._processar_cnj
        runner.chrome_responde = lambda: self.chrome_vivo
        runner._get_abas_chrome = lambda: []
        runner.marcar_supabase = lambda ids, status, motivo=None: self.marcados.append(
            (list(ids), status, motivo))
        runner.gravar_duracao = lambda *a: None
        runner.obs.registrar = lambda etapa, **k: self.etapas.append(etapa)
        runner.chrome_saude.recuperar_conexao = self._recuperar_conexao
        runner.chrome_saude.garantir_aba = self._garantir_aba
        try:
            cnjs = [_info(c, "eproc_tjmg") for c in EPROC] + [_info(c, "pje_tjmg") for c in PJE]
            ids_map = {c: c for c in EPROC + PJE}
            ok, erro, _, _, _, devolvidos = asyncio.run(runner.processar_por_sistema(
                cnjs, "2026-10-08", ids_map, {}, modo=runner.MODO_ASSUMIR_LOGADO))
            return set(ok), set(erro), devolvidos
        finally:
            (runner.processar_cnj, runner.chrome_responde, runner._get_abas_chrome,
             runner.marcar_supabase, runner.gravar_duracao, runner.obs.registrar,
             runner.chrome_saude.recuperar_conexao, runner.chrome_saude.garantir_aba) = originais

    def motivo_de(self, cnj: str) -> str | None:
        for ids, status, motivo in reversed(self.marcados):
            if cnj in ids:
                return motivo
        return None


def test_travou_uma_vez_recupera_e_ninguem_fica_para_tras():
    c = Cenario(travar={"e2": 1})
    ok, _, devolvidos = c.rodar()
    assert ok == set(EPROC + PJE) and not devolvidos
    print("OK travou_uma_vez_recupera")


def test_recuperacao_acontece_uma_vez_por_travamento():
    c = Cenario(travar={"e2": 1})
    c.rodar()
    assert c.recuperacoes == 1 and "chrome.recuperacao" in c.etapas
    print("OK recuperacao_uma_vez")


def test_sistema_que_nao_destrava_nao_derruba_o_pje():
    # o caso de 02 a 07/10, invertido: o eProc trava de vez e o PJe, último da
    # fila, roda inteiro mesmo assim
    c = Cenario(travar={"e2": 99})
    ok, _, _ = c.rodar()
    assert set(PJE) <= ok and "rodada.abortada" not in c.etapas
    print("OK pje_roda_mesmo_com_eproc_travado")


def test_sistema_abandonado_devolve_o_resto_com_motivo_proprio():
    c = Cenario(travar={"e2": 99})
    _, _, devolvidos = c.rodar()
    assert devolvidos == {"e2", "e3"} and c.motivo_de("e3") == runner.MOTIVO_SISTEMA_TRAVOU
    print("OK abandonado_com_motivo")


def test_chrome_morto_para_a_rodada_sem_tentar_recuperar():
    c = Cenario(travar={"e2": 99}, chrome_vivo=False)
    _, _, devolvidos = c.rodar()
    assert devolvidos == {"e2", "e3", "p1", "p2"} and c.recuperacoes == 0
    print("OK chrome_morto_para_tudo")


if __name__ == "__main__":
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith("test_"):
            funcao()
    print("\nTodos os testes da rodada com recuperação passaram.")
