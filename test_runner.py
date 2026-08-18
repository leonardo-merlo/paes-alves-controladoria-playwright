"""test_runner.py — testes das decisões de desfecho da rodada. Rodar: python test_runner.py"""

from runner import (
    LIMITE_FALHAS_CDP,
    MOTIVO_CHROME,
    decidir_chrome_morreu,
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
    test_cdp_mudo_condena_na_primeira()
    test_chrome_vivo_nao_condena_a_rodada_na_primeira_falha()
    test_falha_repetida_com_chrome_vivo_ainda_condena()
    print("Todos os testes passaram.")
