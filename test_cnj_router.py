"""test_cnj_router.py — testes do roteamento por número CNJ. Rodar: python test_cnj_router.py"""

from cnj_router import rotear


# ── casos reais que falharam na máquina do Henrique em 15/08/2026 ──

def test_processo_federal_trf6_nao_vai_para_o_eproc_estadual():
    # 1002485-27...4.06... começa com "1" e a tabela de dígito do TJMG mandava
    # para o eproc_tjmg. Processo federal procurado no tribunal de Minas: errou
    # 3x por rodada, em 3 rodadas seguidas.
    info = rotear("1002485-27.2023.4.06.3821", "eproc")
    assert info.sistema == "eproc_trf6", info.sistema
    assert "trf6" in info.url
    print("OK federal_nao_vai_para_estadual")


def test_federal_trf6_com_digito_6_continua_no_trf6():
    # os que já funcionavam não podem quebrar
    assert rotear("6006056-47.2025.4.06.3821").sistema == "eproc_trf6"
    assert rotear("6002699-25.2026.4.06.3821", "eproc").sistema == "eproc_trf6"
    print("OK federal_digito_6")


def test_rotulo_nao_atravessa_tribunal():
    # TRF1 rotulado 'pje_2g' pela skill do Gmail ia parar no RUPE, que é do TJMG
    info = rotear("1001571-06.2020.4.01.3821", "pje_2g")
    assert info.sistema.startswith("nao_mapeado"), info.sistema
    assert info.implementado is False
    print("OK rotulo_nao_atravessa_tribunal")


# ── comportamento que já existia e não pode regredir ──

def test_tjmg_primeira_instancia_pelo_digito():
    assert rotear("5013121-43.2025.8.13.0439").sistema == "pje_tjmg"
    assert rotear("1002833-70.2026.8.13.0439").sistema == "eproc_tjmg"
    print("OK tjmg_digito")


def test_origem_0000_e_segunda_instancia():
    assert rotear("2817393-23.2026.8.13.0000").sistema == "pje_tjmg_2inst"
    print("OK origem_0000")


def test_rotulo_forte_vence_dentro_do_mesmo_tribunal():
    # 'pje_2g' num processo do TJMG continua mandando para o RUPE: a ausência da
    # palavra "vara" é sinal que o CNJ sozinho não revela.
    assert rotear("5015870-33.2025.8.13.0439", "pje_2g").sistema == "pje_tjmg_2inst"
    print("OK rotulo_forte_mesmo_tribunal")


def test_rotulo_fraco_nao_vence_o_digito():
    # 'pje' e 'eproc' são o palpite genérico da skill — o dígito é mais confiável
    assert rotear("1002848-39.2026.8.13.0439", "pje").sistema == "eproc_tjmg"
    print("OK rotulo_fraco")


def test_cnj_invalido_nao_explode():
    info = rotear("123-abc")
    assert info.implementado is False
    assert info.erro is not None
    print("OK cnj_invalido")


if __name__ == "__main__":
    test_processo_federal_trf6_nao_vai_para_o_eproc_estadual()
    test_federal_trf6_com_digito_6_continua_no_trf6()
    test_rotulo_nao_atravessa_tribunal()
    test_tjmg_primeira_instancia_pelo_digito()
    test_origem_0000_e_segunda_instancia()
    test_rotulo_forte_vence_dentro_do_mesmo_tribunal()
    test_rotulo_fraco_nao_vence_o_digito()
    test_cnj_invalido_nao_explode()
    print("Todos os testes passaram.")
