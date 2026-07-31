"""test_runner.py — testes das decisões de desfecho da rodada. Rodar: python test_runner.py"""

from runner import eh_nada_novo, eh_queda_de_sessao

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


if __name__ == "__main__":
    test_zero_documentos_em_extracao_incremental_nao_e_erro()
    test_zero_documentos_na_primeira_extracao_e_erro()
    test_documentos_novos_nao_sao_nada_novo()
    test_sessao_expirada_e_queda_de_sessao()
    test_erro_de_extracao_comum_nao_e_queda_de_sessao()
    test_resultado_ausente_nao_e_queda_de_sessao()
    print("Todos os testes passaram.")
