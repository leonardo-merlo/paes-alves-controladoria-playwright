"""test_agente.py — testes do agente local. Rodar: python test_agente.py"""

import tempfile
from pathlib import Path

from agente import (
    ACOES,
    NOME_ARQUIVO_PAUSA,
    _resumo_abertura_para_status,
    _resumo_para_status,
    deve_imprimir,
    esta_pausado,
    proximo_pendente,
    resumir_erro_do_loop,
)


def test_acao_antiga_continua_valida():
    # o painel velho só sabe mandar 'iniciar'; um agente atualizado antes dele
    # não pode recusar o único comando que o Henrique consegue disparar hoje
    assert "iniciar" in ACOES
    print("OK acao_iniciar_preservada")


def test_abertura_diz_o_que_fazer_agora():
    status, msg = _resumo_abertura_para_status(
        {"sistemas": ["pje_tjmg_2inst", "pje_tjmg"], "cdp_falhou": False}
    )
    assert status == "concluido"
    assert "RUPE" in msg and "PJe TJMG" in msg
    # a mensagem existe para dizer ao Henrique qual é o próximo passo dele
    assert "Iniciar extração" in msg
    print("OK abertura_ok")


def test_abertura_sem_pendente_nao_pede_login():
    status, msg = _resumo_abertura_para_status({"sistemas": [], "cdp_falhou": False})
    assert status == "concluido" and "Nenhum processo pendente" in msg
    print("OK abertura_sem_pendente")


def test_abertura_sem_chrome_e_erro():
    status, _ = _resumo_abertura_para_status({"sistemas": ["pje_tjmg"], "cdp_falhou": True})
    assert status == "erro"
    print("OK abertura_cdp_falhou")


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


# ── janela do agente: erro de rede não vira parede de texto ───────

def test_erro_de_rede_vira_texto_de_gente():
    # mensagem real capturada na máquina do Henrique em 15/08/2026
    erro = "[Errno 11001] getaddrinfo failed"
    assert resumir_erro_do_loop(erro) == "Sem conexão com a internet — aguardando a rede voltar..."
    print("OK erro_rede_traduzido")


def test_conexao_derrubada_tambem_conta_como_rede():
    assert "internet" in resumir_erro_do_loop("WinError 10054 Connection reset by peer")
    print("OK conexao_derrubada")


def test_erro_desconhecido_aparece_inteiro():
    # erro que não é de rede não pode ser escondido — é diagnóstico
    assert resumir_erro_do_loop("KeyError: 'numero_cnj'") == "Erro no loop do agente: KeyError: 'numero_cnj'"
    print("OK erro_desconhecido_visivel")


def test_erro_repetido_imprime_uma_vez_so():
    msg = "Sem conexão com a internet — aguardando a rede voltar..."
    assert deve_imprimir(msg, None) is True
    assert deve_imprimir(msg, msg) is False
    print("OK erro_repetido_calado")


def test_erro_diferente_volta_a_imprimir():
    assert deve_imprimir("Erro no loop do agente: outro", "Sem conexão com a internet — aguardando a rede voltar...") is True
    print("OK erro_novo_aparece")


if __name__ == "__main__":
    test_acao_antiga_continua_valida()
    test_abertura_diz_o_que_fazer_agora()
    test_abertura_sem_pendente_nao_pede_login()
    test_abertura_sem_chrome_e_erro()
    test_erro_de_rede_vira_texto_de_gente()
    test_conexao_derrubada_tambem_conta_como_rede()
    test_erro_desconhecido_aparece_inteiro()
    test_erro_repetido_imprime_uma_vez_so()
    test_erro_diferente_volta_a_imprimir()
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
