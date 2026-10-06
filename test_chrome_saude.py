"""test_chrome_saude.py — testes do retrato e da sondagem do Chrome. Rodar: python test_chrome_saude.py"""

import asyncio

from chrome_saude import (
    descrever_config,
    extrair_desempenho,
    resumir_sondagem,
    retrato_abas,
    sondar_abas,
)


def test_perfil_sem_ajuste_nao_afirma_desligado():
    """Bloco vazio é 'padrão do Chrome', não 'economia desligada' — o padrão
    muda entre versões, e afirmar o estado aqui seria chute."""
    desempenho = extrair_desempenho({"outra": 1}, {})
    frase = descrever_config(desempenho, "Chrome/152.0")
    assert "padrão do Chrome" in frase and "deslig" not in frase
    print("OK perfil_sem_ajuste_nao_afirma_desligado")


def test_ajuste_no_perfil_aparece_pelo_nome():
    desempenho = extrair_desempenho(
        {"performance_tuning": {"high_efficiency_mode": {"state": 2}}}, {})
    assert "high_efficiency_mode" in descrever_config(desempenho, None)
    print("OK ajuste_no_perfil_aparece_pelo_nome")


def test_arquivo_ilegivel_nao_quebra():
    assert extrair_desempenho(None, None) == {"local_state": {}, "preferencias": {}}
    print("OK arquivo_ilegivel_nao_quebra")


def test_retrato_guarda_host_e_id_curto():
    abas = [{"id": "F2485BE49498F1BE", "type": "page",
             "url": "https://www.uniaoseguradora.com.br/"}]
    assert retrato_abas(abas) == [
        {"id": "F2485BE4", "tipo": "page", "host": "www.uniaoseguradora.com.br"}]
    print("OK retrato_guarda_host_e_id_curto")


def test_aba_muda_vem_na_frente_da_frase():
    ok, frase = resumir_sondagem([
        {"id": "a", "host": "pje.tjmg.jus.br", "responde": True, "descartada": False},
        {"id": "b", "host": "eproc1g.tjmg.jus.br", "responde": False, "obs": "sem resposta em 5s"},
    ])
    assert not ok and "NÃO RESPONDEM: eproc1g.tjmg.jus.br" in frase
    print("OK aba_muda_vem_na_frente_da_frase")


def test_aba_descartada_conta_como_problema():
    ok, frase = resumir_sondagem([
        {"id": "a", "host": "eproc1g.tjmg.jus.br", "responde": True, "descartada": True}])
    assert not ok and "DESCARTADAS pelo Chrome: eproc1g.tjmg.jus.br" in frase
    print("OK aba_descartada_conta_como_problema")


def test_tudo_saudavel_e_ok():
    ok, _ = resumir_sondagem([{"id": "a", "host": "x", "responde": True, "descartada": False}])
    assert ok
    print("OK tudo_saudavel_e_ok")


def test_sondagem_sem_endereco_nao_vira_aba_muda():
    """Aba sem webSocketDebuggerUrl não foi perguntada — não dá para dizer que
    ficou muda."""
    resultados = asyncio.run(sondar_abas([{"id": "x", "type": "page", "url": "https://a.jus.br"}]))
    assert resultados[0]["responde"] is None
    print("OK sondagem_sem_endereco_nao_vira_aba_muda")


def test_sondagem_ignora_iframe_e_service_worker():
    resultados = asyncio.run(sondar_abas([{"id": "x", "type": "iframe"},
                                          {"id": "y", "type": "service_worker"}]))
    assert resultados == []
    print("OK sondagem_ignora_iframe_e_service_worker")


if __name__ == "__main__":
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith("test_"):
            funcao()
    print("\nTodos os testes de chrome_saude passaram.")
