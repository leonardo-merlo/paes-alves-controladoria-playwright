"""test_agente.py — testes do agente local. Rodar: python test_agente.py"""

from agente import proximo_pendente, _resumo_para_status


def test_proximo_pendente_escolhe_mais_antigo():
    comandos = [
        {"id": "b", "status": "pendente", "criado_em": "2026-06-15T10:00:00Z"},
        {"id": "a", "status": "pendente", "criado_em": "2026-06-15T09:00:00Z"},
        {"id": "c", "status": "concluido", "criado_em": "2026-06-15T08:00:00Z"},
    ]
    assert proximo_pendente(comandos)["id"] == "a"
    print("OK escolhe_mais_antigo")


def test_proximo_pendente_sem_pendentes_retorna_none():
    comandos = [{"id": "x", "status": "concluido", "criado_em": "2026-06-15T08:00:00Z"}]
    assert proximo_pendente(comandos) is None
    print("OK sem_pendentes")


def test_resumo_nada_pendente():
    assert _resumo_para_status({"total": 0, "processados": 0, "erros": 0})[0] == "concluido"
    print("OK resumo_nada_pendente")


def test_resumo_sucesso():
    status, msg = _resumo_para_status({"total": 1, "processados": 1, "erros": 0})
    assert status == "concluido" and "1 processado" in msg
    print("OK resumo_sucesso")


def test_resumo_tudo_falhou_eh_erro():
    # o bug original: extração falhou mas comando ficava "concluído".
    status, _ = _resumo_para_status({"total": 1, "processados": 0, "erros": 1})
    assert status == "erro"
    print("OK resumo_tudo_falhou")


def test_resumo_parcial():
    status, msg = _resumo_para_status({"total": 2, "processados": 1, "erros": 1})
    assert status == "concluido" and "com erro" in msg
    print("OK resumo_parcial")


if __name__ == "__main__":
    test_proximo_pendente_escolhe_mais_antigo()
    test_proximo_pendente_sem_pendentes_retorna_none()
    test_resumo_nada_pendente()
    test_resumo_sucesso()
    test_resumo_tudo_falhou_eh_erro()
    test_resumo_parcial()
    print("Todos os testes passaram.")
