"""test_runner.py — testes das decisões de desfecho da rodada. Rodar: python test_runner.py"""

from runner import eh_nada_novo, eh_queda_de_sessao, eh_chrome_inacessivel

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


if __name__ == "__main__":
    test_zero_documentos_em_extracao_incremental_nao_e_erro()
    test_zero_documentos_na_primeira_extracao_e_erro()
    test_documentos_novos_nao_sao_nada_novo()
    test_sessao_expirada_e_queda_de_sessao()
    test_erro_de_extracao_comum_nao_e_queda_de_sessao()
    test_resultado_ausente_nao_e_queda_de_sessao()
    test_timeout_de_cdp_e_chrome_inacessivel()
    test_sessao_expirada_nao_e_chrome_inacessivel()
    test_resultado_ausente_nao_e_chrome_inacessivel()
    print("Todos os testes passaram.")
