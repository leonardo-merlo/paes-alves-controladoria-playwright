"""test_runner.py — testes das decisões de desfecho da rodada. Rodar: python test_runner.py"""

from runner import (
    LIMITE_FALHAS_CDP,
    MOTIVO_CHROME,
    AVISO_MAX_LINHAS,
    STATUS_TRATADO_MANUAL,
    abas_vazadas,
    aviso_publicacao_ignorada,
    decidir_chrome_morreu,
    resumir_abas,
    motivo_de_nao_reinserir,
    duracao_segundos,
    eh_chrome_inacessivel,
    eh_nada_novo,
    eh_queda_de_sessao,
    motivo_devolucao,
    ordenar_sistemas,
    resumir_motivos,
)

MOTIVO_CERTIFICADO = (
    "PJe recusou o acesso: O acesso à íntegra dos autos por advogados não "
    "vinculados ao processo somente é permitido mediante login com certificado digital."
)


def test_certificado_nao_vira_pergunta_sobre_login():
    # a rodada de 16/08 tinha os 4 erros em certificado e o painel perguntava
    # "Login não concluído?" — mandava conferir justamente o que estava certo
    assert resumir_motivos([MOTIVO_CERTIFICADO] * 3) == "os processos exigem certificado digital"
    print("OK motivo_certificado")


def test_motivo_mais_frequente_vence():
    motivos = [MOTIVO_CERTIFICADO, MOTIVO_CERTIFICADO, "sessao_expirada"]
    assert resumir_motivos(motivos) == "os processos exigem certificado digital"
    print("OK motivo_mais_frequente")


def test_sessao_caida_continua_sendo_dita():
    # o conserto não é esconder o problema de login, é parar de chutá-lo
    assert resumir_motivos(["sessao_expirada", "sessao_expirada"]) == "a sessão caiu"
    print("OK motivo_sessao")


def test_sem_motivo_reconhecivel_nao_inventa():
    assert resumir_motivos(["explodiu de um jeito novo"]) is None
    assert resumir_motivos([]) is None
    print("OK motivo_desconhecido")

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


# ── devolver à fila sem apagar o diagnóstico ──────────────────────
# A rodada de 17/08: o Henrique perguntou por que os erros de ontem tinham
# sumido. Tinham virado "pendente — o Chrome parou de responder".

def test_devolucao_preserva_o_motivo_anterior():
    texto = motivo_devolucao(MOTIVO_CHROME, MOTIVO_CERTIFICADO)
    assert texto.startswith(MOTIVO_CHROME)
    assert "certificado digital" in texto
    print("OK devolucao_preserva_motivo")


def test_devolucao_sem_motivo_anterior_nao_inventa():
    assert motivo_devolucao(MOTIVO_CHROME, None) == MOTIVO_CHROME
    assert motivo_devolucao(MOTIVO_CHROME, "") == MOTIVO_CHROME
    print("OK devolucao_sem_anterior")


def test_devolucao_nao_repete_o_mesmo_motivo():
    # duas rodadas seguidas morrendo pelo Chrome não viram "Chrome (antes: Chrome)"
    assert motivo_devolucao(MOTIVO_CHROME, MOTIVO_CHROME) == MOTIVO_CHROME
    print("OK devolucao_sem_repeticao")


def test_devolucao_nao_empilha_camadas():
    # a causa raiz é o que interessa: rodada após rodada não pode encher os 400
    # caracteres do campo com '(antes: (antes: ...))'
    uma = motivo_devolucao(MOTIVO_CHROME, MOTIVO_CERTIFICADO)
    duas = motivo_devolucao(MOTIVO_CHROME, uma)
    assert duas == uma
    assert duas.count("(antes:") == 1
    print("OK devolucao_sem_empilhar")


def test_devolucao_cabe_no_campo():
    assert len(motivo_devolucao(MOTIVO_CHROME, "x" * 900)) <= 400
    print("OK devolucao_truncada")


# ── limpeza das abas que a extração deixa para trás ───────────────
# Medido nos logs de 18 e 19/08: 5 abas no início da rodada, 46 no fim do bloco
# do PJe. A partir daí toda rodada seguinte morria no timeout de 180s.

def _aba(id_, tipo="page", url="https://pje.tjmg.jus.br/pje/x.seam"):
    return {"id": id_, "type": tipo, "url": url}


def test_aba_aberta_pela_extracao_e_fechada():
    inicio = {"a"}
    agora = [_aba("a"), _aba("b"), _aba("c")]
    assert sorted(abas_vazadas(agora, inicio)) == ["b", "c"]
    print("OK abas_vazadas")


def test_aba_que_ja_estava_aberta_nao_e_tocada():
    # o login do Henrique estava lá antes da rodada e não pode ser fechado
    agora = [_aba("a"), _aba("b")]
    assert abas_vazadas(agora, {"a", "b"}) == []
    print("OK abas_preexistentes")


def test_aba_do_henrique_em_outro_site_nao_e_tocada():
    # ele abriu o Gmail no meio da rodada — não é nossa
    agora = [_aba("novo", url="https://mail.google.com/")]
    assert abas_vazadas(agora, set()) == []
    print("OK aba_de_fora")


def test_so_pagina_e_fechada():
    # iframe e service worker não se fecham por este endpoint
    agora = [_aba("i", tipo="iframe"), _aba("w", tipo="service_worker"), _aba("p")]
    assert abas_vazadas(agora, set()) == ["p"]
    print("OK so_page")


def test_todos_os_sistemas_contam_como_judiciais():
    for url in ("https://eproc1g.tjmg.jus.br/x", "https://pe.tjmg.jus.br/rupe/x",
                "https://eproc2g.trf6.jus.br/x", "https://tjrj.pje.jus.br/x"):
        assert abas_vazadas([_aba("n", url=url)], set()) == ["n"], url
    print("OK hosts_judiciais")


def test_aba_que_foi_parar_no_login_do_tribunal_tambem_e_fechada():
    # medido em 19/08 num Chrome de teste: abrir pje.tjmg.jus.br termina em
    # sso.cloud.pje.jus.br. Com lista fechada de hosts, a aba vazada escapava
    # justamente por ter ido para o login — que é onde ela mais para.
    agora = [_aba("sso", url="https://sso.cloud.pje.jus.br/auth/realms/pje/protocol")]
    assert abas_vazadas(agora, set()) == ["sso"]
    print("OK aba_no_sso")


def test_resumo_diz_de_que_sao_as_abas():
    resumo = resumir_abas([_aba("a"), _aba("b"), _aba("i", tipo="iframe")])
    assert resumo.startswith("3 aba(s)")
    assert "page 2" in resumo and "iframe 1" in resumo
    print("OK resumo_abas")


def test_resumo_sem_aba_nenhuma():
    assert resumir_abas([]) == "0 aba(s)"
    print("OK resumo_vazio")


# ── uma falha de CDP não condena a rodada ─────────────────────────

def test_cdp_mudo_condena_na_primeira():
    # Chrome que não responde nem ao endereço de debug não volta sozinho:
    # insistir custaria 180s por processo sem extrair nada
    assert decidir_chrome_morreu(cdp_responde=False, falhas_cdp=1) is True
    print("OK cdp_mudo_condena")


def test_chrome_vivo_nao_condena_a_rodada_na_primeira_falha():
    # o caso de 17/08: uma falha no primeiro CNJ do PJe jogou 17 processos de
    # dois sistemas de volta para a fila sem nenhum deles ter sido tentado
    assert decidir_chrome_morreu(cdp_responde=True, falhas_cdp=1) is False
    print("OK chrome_vivo_segue")


# ── reinserção por e-mail não desfaz decisão de gente ─────────────

def test_processo_tratado_na_mao_nao_volta_para_a_fila():
    # publicação nova de um processo que o gestor assumiu na mão desligaria o
    # tratamento manual dele sozinho, sem aviso — ver spec da edição manual
    assert motivo_de_nao_reinserir(STATUS_TRATADO_MANUAL) is not None
    print("OK tratado_manual_nao_reinsere")


def test_pendente_continua_sem_ser_reinserido():
    assert motivo_de_nao_reinserir("pendente") is not None
    print("OK pendente_nao_reinsere")


def test_aviso_registra_a_pauta_que_chegou():
    # o processo saiu da fila, mas continua andando no tribunal — sem este
    # registro nada dizia ao Henrique que chegou publicação nova
    texto = aviso_publicacao_ignorada("2026-08-19", None)
    assert "19/08/2026" in texto
    assert "tratado na mão" in texto
    print("OK aviso_registra_pauta")


def test_aviso_aceita_pauta_no_formato_brasileiro():
    # lote_id aparece nos dois formatos no banco — ver resolverDataAgrupamento
    assert "19/08/2026" in aviso_publicacao_ignorada("19/08/2026", None)
    print("OK aviso_formato_br")


def test_aviso_mais_recente_vem_primeiro():
    antigo = aviso_publicacao_ignorada("2026-08-18", None)
    novo = aviso_publicacao_ignorada("2026-08-19", antigo)
    assert novo.splitlines()[0].count("19/08/2026") == 1
    assert "18/08/2026" in novo
    print("OK aviso_ordem")


def test_aviso_nao_repete_a_mesma_pauta():
    # rodada reprocessada não pode virar dez linhas iguais
    uma = aviso_publicacao_ignorada("2026-08-19", None)
    duas = aviso_publicacao_ignorada("2026-08-19", uma)
    assert uma == duas
    print("OK aviso_sem_repeticao")


def test_aviso_nao_cresce_para_sempre():
    texto = None
    for dia in range(1, 20):
        texto = aviso_publicacao_ignorada(f"2026-07-{dia:02d}", texto)
    assert len(texto.splitlines()) == AVISO_MAX_LINHAS
    print("OK aviso_limitado")


def test_aviso_preserva_observacao_que_ja_estava_la():
    texto = aviso_publicacao_ignorada("2026-08-19", "anotação escrita à mão")
    assert "anotação escrita à mão" in texto
    print("OK aviso_preserva_anotacao")


def test_erro_e_processado_continuam_podendo_voltar():
    # erro merece nova tentativa amanhã, e processado precisa da pauta nova
    assert motivo_de_nao_reinserir("erro_browser") is None
    assert motivo_de_nao_reinserir("processado") is None
    assert motivo_de_nao_reinserir(None) is None
    print("OK outros_podem_voltar")


def test_falha_repetida_com_chrome_vivo_ainda_condena():
    # o limite existe para não gastar 180s por CNJ contra um Chrome que responde
    # ao HTTP mas não deixa o Playwright anexar — a fila de 20 viraria uma hora
    assert decidir_chrome_morreu(cdp_responde=True, falhas_cdp=LIMITE_FALHAS_CDP) is True
    print("OK falha_repetida_condena")


if __name__ == "__main__":
    test_certificado_nao_vira_pergunta_sobre_login()
    test_motivo_mais_frequente_vence()
    test_sessao_caida_continua_sendo_dita()
    test_sem_motivo_reconhecivel_nao_inventa()
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
    test_devolucao_preserva_o_motivo_anterior()
    test_devolucao_sem_motivo_anterior_nao_inventa()
    test_devolucao_nao_repete_o_mesmo_motivo()
    test_devolucao_nao_empilha_camadas()
    test_devolucao_cabe_no_campo()
    test_aba_aberta_pela_extracao_e_fechada()
    test_aba_que_ja_estava_aberta_nao_e_tocada()
    test_aba_do_henrique_em_outro_site_nao_e_tocada()
    test_so_pagina_e_fechada()
    test_todos_os_sistemas_contam_como_judiciais()
    test_aba_que_foi_parar_no_login_do_tribunal_tambem_e_fechada()
    test_resumo_diz_de_que_sao_as_abas()
    test_resumo_sem_aba_nenhuma()
    test_cdp_mudo_condena_na_primeira()
    test_chrome_vivo_nao_condena_a_rodada_na_primeira_falha()
    test_falha_repetida_com_chrome_vivo_ainda_condena()
    test_processo_tratado_na_mao_nao_volta_para_a_fila()
    test_pendente_continua_sem_ser_reinserido()
    test_erro_e_processado_continuam_podendo_voltar()
    test_aviso_registra_a_pauta_que_chegou()
    test_aviso_aceita_pauta_no_formato_brasileiro()
    test_aviso_mais_recente_vem_primeiro()
    test_aviso_nao_repete_a_mesma_pauta()
    test_aviso_nao_cresce_para_sempre()
    test_aviso_preserva_observacao_que_ja_estava_la()
    print("Todos os testes passaram.")
