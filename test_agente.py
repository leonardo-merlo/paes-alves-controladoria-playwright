"""test_agente.py — testes do agente local. Rodar: python test_agente.py"""

import tempfile
from pathlib import Path

from agente import (
    NOME_ARQUIVO_PAUSA,
    _resumo_para_status,
    esta_pausado,
    proximo_pendente,
)


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


def test_resumo_anuncia_analise_recuperada():
    # rascunho que a varredura salvou não é extração desta rodada, mas precisa
    # aparecer: é processo que o Henrique já dava por visto e voltou a ter prazo.
    _, msg = _resumo_para_status(
        {"total": 1, "processados": 1, "erros": 0, "reanalisados": 2}
    )
    assert "2 análise(s) recuperada(s)" in msg
    print("OK resumo_analise_recuperada")


def test_resumo_sem_reanalise_nao_polui_mensagem():
    _, msg = _resumo_para_status({"total": 1, "processados": 1, "erros": 0})
    assert "recuperada" not in msg
    print("OK resumo_sem_reanalise")


# ── pausa por máquina ─────────────────────────────────────────────
# Serve para rodar as extracoes noutro computador sem que a maquina do Henrique
# dispute os comandos. Precisa sobreviver a reinicio do Windows, por isso e um
# arquivo em disco e nao um estado em memoria.

def test_sem_arquivo_o_agente_trabalha():
    with tempfile.TemporaryDirectory() as tmp:
        assert esta_pausado(Path(tmp)) is False
    print("OK pausa_ausente")


def test_com_arquivo_o_agente_para():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / NOME_ARQUIVO_PAUSA).write_text("pausado em 04/08", encoding="utf-8")
        assert esta_pausado(Path(tmp)) is True
    print("OK pausa_presente")


def test_apagar_o_arquivo_religa():
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / NOME_ARQUIVO_PAUSA
        alvo.write_text("x", encoding="utf-8")
        alvo.unlink()
        assert esta_pausado(Path(tmp)) is False
    print("OK pausa_removida")


if __name__ == "__main__":
    test_proximo_pendente_escolhe_mais_antigo()
    test_proximo_pendente_sem_pendentes_retorna_none()
    test_resumo_nada_pendente()
    test_resumo_sucesso()
    test_resumo_tudo_falhou_eh_erro()
    test_resumo_parcial()
    test_resumo_anuncia_analise_recuperada()
    test_resumo_sem_reanalise_nao_polui_mensagem()
    test_sem_arquivo_o_agente_trabalha()
    test_com_arquivo_o_agente_para()
    test_apagar_o_arquivo_religa()
    print("Todos os testes passaram.")
