"""test_cnj_router.py — testes do roteamento por número CNJ. Rodar: python test_cnj_router.py"""

from cnj_router import rotear, nome_sistema, motivo_sem_extrator


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
    # Processo federal rotulado 'pje_2g' pela skill do Gmail ia parar no RUPE,
    # que é do TJMG. O que este teste guarda é isso — o rótulo não atravessa
    # tribunal —, e não "não tem extrator": ele afirmava as duas coisas juntas
    # porque em 15/08 elas coincidiam. Desde 16/08 a origem mineira tem destino
    # (TRF6), então a segunda afirmação deixou de valer para este número.
    for cnj in ("1001571-06.2020.4.01.3821", "1001571-06.2020.4.01.9999"):
        info = rotear(cnj, "pje_2g")
        assert info.sistema != "pje_tjmg_2inst", info.sistema
        assert not info.sistema.startswith("pje_"), info.sistema
    # sem origem conhecida continua sem destino nenhum
    assert rotear("1001571-06.2020.4.01.9999", "pje_2g").implementado is False
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


def test_nome_de_sistema_nao_mapeado_mostra_o_tribunal():
    # na Justiça Federal o código do tribunal é o número do TRF — dizer
    # "nao_mapeado_J4_TT03" ou "tribunal 4.03" no painel não ajuda ninguém
    assert nome_sistema("nao_mapeado_J4_TT03") == "TRF3"
    assert nome_sistema("nao_mapeado_J8_TT26") == "tribunal 8.26"
    assert nome_sistema("pje_tjmg_2inst") == "RUPE (TJMG 2ª inst.)"
    print("OK nome_sistema")


def test_mensagem_do_trf1_ensina_a_conferir_o_trf6():
    # "Sistema não implementado" é beco sem saída: quem lê fecha a tela. O de
    # Muriaé passou rodadas assim e estava no TRF6 o tempo todo.
    msg = motivo_sem_extrator("1001571-06.2020.4.01.9999")
    assert "TRF1" in msg
    assert "TRF6" in msg
    assert "9999" in msg  # a origem, que é o que ele precisa me passar
    print("OK mensagem_trf1")


def test_mensagem_de_outro_tribunal_continua_curta():
    # só o TRF1 tem a história do TRF6; inventar isso para o TJRJ seria ruído
    msg = motivo_sem_extrator("1000000-00.2024.8.19.0001")
    assert "TRF6" not in msg
    assert "Sistema não implementado" in msg
    print("OK mensagem_outro_tribunal")


def test_processo_mineiro_antigo_vai_para_o_trf6():
    # numerado 4.01 porque é de 2020, antes de o TRF6 existir; a unidade (origem
    # 3821, Muriaé) é mineira e hoje quem cuida dela é o TRF6. Medido em 16/08:
    # o processo está lá, com 6 documentos.
    info = rotear("1001571-06.2020.4.01.3821")
    assert info.sistema == "eproc_trf6"
    assert info.implementado is True
    print("OK mineiro_antigo_trf6")


def test_rotulo_do_email_nao_desvia_o_mineiro_antigo():
    # o e-mail rotulou 'pje_2g' por ler "Turma Recursal"; acertou a instância e
    # errou o tribunal — o RUPE é do TJMG
    assert rotear("1001571-06.2020.4.01.3821", "pje_2g").sistema == "eproc_trf6"
    print("OK mineiro_antigo_ignora_rotulo")


def test_trf1_de_outro_estado_continua_sem_extrator():
    # o TRF1 ainda cobre 13 estados; só Minas migrou para o TRF6. Origem
    # desconhecida não pode ser chutada para lá.
    info = rotear("1001571-06.2020.4.01.9999")
    assert info.sistema == "nao_mapeado_J4_TT01"
    assert info.implementado is False
    print("OK trf1_outro_estado")


def test_sistema_pelo_numero_ignora_o_rotulo_do_email():
    # é o que o painel usa para dizer "pelo número, parece X": sem hint nenhum.
    # Origem 9999 não é mineira, então segue TRF1 sem extrator — o caso de Muriaé
    # mudou de desfecho, ver test_processo_mineiro_antigo_vai_para_o_trf6.
    assert rotear("1001571-06.2020.4.01.9999").sistema == "nao_mapeado_J4_TT01"
    assert rotear("2817393-23.2026.8.13.0000").sistema == "pje_tjmg_2inst"
    print("OK sistema_pelo_numero")


if __name__ == "__main__":
    test_mensagem_do_trf1_ensina_a_conferir_o_trf6()
    test_mensagem_de_outro_tribunal_continua_curta()
    test_processo_mineiro_antigo_vai_para_o_trf6()
    test_rotulo_do_email_nao_desvia_o_mineiro_antigo()
    test_trf1_de_outro_estado_continua_sem_extrator()
    test_nome_de_sistema_nao_mapeado_mostra_o_tribunal()
    test_sistema_pelo_numero_ignora_o_rotulo_do_email()
    test_processo_federal_trf6_nao_vai_para_o_eproc_estadual()
    test_federal_trf6_com_digito_6_continua_no_trf6()
    test_rotulo_nao_atravessa_tribunal()
    test_tjmg_primeira_instancia_pelo_digito()
    test_origem_0000_e_segunda_instancia()
    test_rotulo_forte_vence_dentro_do_mesmo_tribunal()
    test_rotulo_fraco_nao_vence_o_digito()
    test_cnj_invalido_nao_explode()
    print("Todos os testes passaram.")
