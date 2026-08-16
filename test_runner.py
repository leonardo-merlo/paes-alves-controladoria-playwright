"""test_runner.py — testes das decisões de desfecho da rodada. Rodar: python test_runner.py"""

from runner import (
    duracao_segundos,
    eh_chrome_inacessivel,
    eh_nada_novo,
    eh_queda_de_sessao,
    ordenar_sistemas,
)

# mensagem real do Playwright quando o Chrome empilha abas demais e para de
# responder — capturada na maquina do Henrique e reproduzida em 31/07/2026
ERRO_CDP_REAL = (
    "Não foi possível conectar ao Chrome via CDP (http://localhost:9222): "
    "BrowserType.connect_over_cdp: Timeout 180000ms exceeded."
)

CORTE = "2026-07-28T17:34:22.892611+00:00"


def test_zero_documentos_em_extracao_incremental_nao_e_erro():
    # o processo já tinha sido extraído e voltou à fila numa pauta nova:
    # 0 documentos significa "nada mudou", não falha.
    assert eh_nada_novo(0, CORTE) is True
    print("OK zero_documentos_incremental")


def test_zero_documentos_na_primeira_extracao_e_erro():
    assert eh_nada_novo(0, None) is False
    print("OK zero_documentos_primeira_extracao")


def test_documentos_novos_nao_sao_nada_novo():
    assert eh_nada_novo(3, CORTE) is False
    print("OK documentos_novos")


def test_sessao_expirada_e_queda_de_sessao():
    assert eh_queda_de_sessao({"erro": "sessao_expirada"}) is True
    print("OK sessao_expirada")


def test_nenhuma_aba_e_queda_de_sessao():
    # mensagens reais gravadas em motivo_ignorado na rodada de 14/08/2026, quando
    # as abas foram abertas numa segunda instância do Chrome, invisível ao agente.
    # Tratar como erro do processo queimava a fila inteira antes do login.
    assert eh_queda_de_sessao(
        {"erro": "Nenhuma aba do eProc (eproc1g.tjmg.jus.br) encontrada no Chrome conectado"}
    ) is True
    assert eh_queda_de_sessao(
        {"erro": "Nenhuma aba do RUPE (pe.tjmg.jus.br) encontrada no Chrome conectado"}
    ) is True
    print("OK nenhuma_aba")


def test_nenhuma_aba_nao_e_chrome_inacessivel():
    # o CDP respondeu — o que faltou foi aba do sistema. Confundir os dois mandava
    # o operador fechar o Chrome quando bastava logar.
    assert eh_chrome_inacessivel(
        {"erro": "Nenhuma aba do eProc (eproc1g.tjmg.jus.br) encontrada no Chrome conectado"}
    ) is False
    print("OK nenhuma_aba_nao_e_chrome")


def test_erro_de_extracao_comum_nao_e_queda_de_sessao():
    assert eh_queda_de_sessao({"erro": "sem_documentos"}) is False
    print("OK erro_comum")


def test_resultado_ausente_nao_e_queda_de_sessao():
    assert eh_queda_de_sessao(None) is False
    print("OK resultado_ausente")


def test_timeout_de_cdp_e_chrome_inacessivel():
    assert eh_chrome_inacessivel({"erro": ERRO_CDP_REAL}) is True
    print("OK chrome_inacessivel")


def test_sessao_expirada_nao_e_chrome_inacessivel():
    # são desfechos diferentes: um pede login, o outro pede fechar o Chrome.
    assert eh_chrome_inacessivel({"erro": "sessao_expirada"}) is False
    print("OK sessao_nao_e_chrome")


def test_resultado_ausente_nao_e_chrome_inacessivel():
    assert eh_chrome_inacessivel(None) is False
    print("OK chrome_resultado_ausente")


# ── cronômetro por processo ───────────────────────────────────────
# Alimenta a métrica de tempo médio no painel. Ver a spec de 2026-08-06.

def test_duracao_arredonda_para_segundos_inteiros():
    assert duracao_segundos(100.0, 112.4) == 12
    print("OK duracao_arredonda")


def test_duracao_nunca_e_negativa():
    # relógio monotônico não anda para trás, mas gravar número negativo
    # envenenaria a média no painel para sempre
    assert duracao_segundos(200.0, 100.0) == 0
    print("OK duracao_nao_negativa")


def test_duracao_de_processo_instantaneo_e_zero():
    assert duracao_segundos(50.0, 50.0) == 0
    print("OK duracao_zero")


def test_rupe_vai_na_frente():
    # a sessão do RUPE cai antes das outras: ser o último da fila é o que mais
    # tempo deixa ela envelhecendo
    assert ordenar_sistemas(["pje_tjmg", "eproc_tjmg", "pje_tjmg_2inst"]) == [
        "pje_tjmg_2inst", "pje_tjmg", "eproc_tjmg",
    ]
    print("OK rupe_na_frente")


def test_sem_rupe_a_ordem_nao_muda():
    # reordenar o que não precisa só tornaria a rodada difícil de comparar
    assert ordenar_sistemas(["pje_tjmg", "eproc_tjmg"]) == ["pje_tjmg", "eproc_tjmg"]
    print("OK ordem_estavel")


def test_rupe_sozinho_continua_sozinho():
    assert ordenar_sistemas(["pje_tjmg_2inst"]) == ["pje_tjmg_2inst"]
    assert ordenar_sistemas([]) == []
    print("OK rupe_sozinho")


if __name__ == "__main__":
    test_rupe_vai_na_frente()
    test_sem_rupe_a_ordem_nao_muda()
    test_rupe_sozinho_continua_sozinho()
    test_zero_documentos_em_extracao_incremental_nao_e_erro()
    test_zero_documentos_na_primeira_extracao_e_erro()
    test_documentos_novos_nao_sao_nada_novo()
    test_sessao_expirada_e_queda_de_sessao()
    test_nenhuma_aba_e_queda_de_sessao()
    test_nenhuma_aba_nao_e_chrome_inacessivel()
    test_erro_de_extracao_comum_nao_e_queda_de_sessao()
    test_resultado_ausente_nao_e_queda_de_sessao()
    test_timeout_de_cdp_e_chrome_inacessivel()
    test_sessao_expirada_nao_e_chrome_inacessivel()
    test_resultado_ausente_nao_e_chrome_inacessivel()
    test_duracao_arredonda_para_segundos_inteiros()
    test_duracao_nunca_e_negativa()
    test_duracao_de_processo_instantaneo_e_zero()
    print("Todos os testes passaram.")
