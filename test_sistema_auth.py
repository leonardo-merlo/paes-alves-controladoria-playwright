"""test_sistema_auth.py — testes da detecção de login. Rodar: python test_sistema_auth.py"""

from sistema_auth import (
    ESPERA_LOGIN_S,
    MAX_TENTATIVAS_LOGIN,
    SEM_DETECCAO_DE_LOGIN,
    _avaliar_login,
    _esgotou_as_tentativas,
    _tem_campo_de_senha,
    deve_tentar,
)

RUPE_LOGIN = "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe"
RUPE_INTERNO = "https://pe.tjmg.jus.br/rupe/portaljus/intranet/processo/processos.rupe?acao=0"

# campos visíveis lidos das telas de login reais em 31/07/2026
CAMPOS_LOGIN_RUPE = [
    {"type": "text", "id": "login", "name": "j_username"},
    {"type": "password", "id": "senha", "name": "j_password"},
    {"type": "submit", "id": "entrar", "name": ""},
]
CAMPOS_LOGIN_EPROC = [
    {"type": "text", "id": "sidebar-searchbox", "name": ""},
    {"type": "text", "id": "txtUsuario", "name": "txtUsuario"},
    {"type": "text", "id": "pwdSenha", "name": ""},
    {"type": "button", "id": "", "name": ""},
]
CAMPOS_PAGINA_INTERNA = [
    {"type": "text", "id": "txtNumProcesso", "name": "txtNumProcesso"},
    {"type": "submit", "id": "sbmPesquisar", "name": ""},
]


def test_pagina_de_login_com_formulario_nao_esta_logado():
    # bug original: a landing do RUPE tem o host e nenhuma keyword de logout na URL,
    # mas ainda exibe o formulário de login (campo senha) → NÃO está logado.
    assert _avaliar_login(RUPE_LOGIN, "pje_tjmg_2inst", tem_form_login=True) is False
    print("OK login_com_formulario")


def test_mesma_pagina_sem_formulario_esta_logado():
    assert _avaliar_login(RUPE_LOGIN, "pje_tjmg_2inst", tem_form_login=False) is True
    print("OK sem_formulario")


def test_pagina_interna_logada():
    assert _avaliar_login(RUPE_INTERNO, "pje_tjmg_2inst", tem_form_login=False) is True
    print("OK pagina_interna")


def test_indicador_de_logout_na_url():
    assert _avaliar_login("https://pe.tjmg.jus.br/rupe/login", "pje_tjmg_2inst", tem_form_login=False) is False
    print("OK indicador_logout")


def test_host_errado():
    assert _avaliar_login("https://google.com", "pje_tjmg_2inst", tem_form_login=False) is False
    print("OK host_errado")


def test_campo_password_comum_e_tela_de_login():
    assert _tem_campo_de_senha(CAMPOS_LOGIN_RUPE) is True
    print("OK campos_rupe")


def test_caixa_de_senha_do_eproc_e_type_text():
    # o eProc exibe a senha como type="text" com id "pwdSenha" e esconde o campo
    # password real com 0x0. Olhar só o type deixava o eProc passar por logado.
    assert _tem_campo_de_senha(CAMPOS_LOGIN_EPROC) is True
    print("OK campos_eproc")


def test_pagina_interna_nao_tem_campo_de_senha():
    assert _tem_campo_de_senha(CAMPOS_PAGINA_INTERNA) is False
    print("OK campos_pagina_interna")


def test_pagina_sem_campo_nenhum():
    assert _tem_campo_de_senha([]) is False
    print("OK sem_campos")


# ── quando tentar extrair cada sistema ────────────────────────────
# O eProc e o RUPE nao tem sinal de login para esperar: a tela de login mora na
# mesma URL da tela interna. Em 02/08/2026 isso fez o agente extrair aos 30s, sem
# ninguem logado, e devolver 17 processos a fila. Agora eles esperam e retentam.

def test_eproc_e_rupe_nao_tem_deteccao_por_url():
    assert "eproc_tjmg" in SEM_DETECCAO_DE_LOGIN
    assert "pje_tjmg_2inst" in SEM_DETECCAO_DE_LOGIN
    assert "pje_tjmg" not in SEM_DETECCAO_DE_LOGIN  # esse redireciona p/ login.seam
    print("OK sistemas_sem_deteccao")


def test_sistema_sem_deteccao_tenta_de_cara():
    # se a sessao ja estava de pe (Chrome aberto da rodada anterior), extrair na
    # hora em vez de cobrar espera de quem nao precisa.
    assert deve_tentar("eproc_tjmg", False, 0, 0) is True
    print("OK cego_primeira_imediata")


def test_sistema_sem_deteccao_nao_tenta_antes_da_hora():
    assert deve_tentar("eproc_tjmg", False, ESPERA_LOGIN_S - 1, 1) is False
    print("OK cego_antes_da_hora")


def test_sistema_sem_deteccao_tenta_quando_o_tempo_fecha():
    assert deve_tentar("eproc_tjmg", False, ESPERA_LOGIN_S, 1) is True
    print("OK cego_na_hora")


def test_espera_entre_tentativas_cobre_codigo_por_email():
    # o login do eProc/RUPE exige codigo temporario que chega por e-mail: a espera
    # tem de ser de minutos, nao de segundos, senao a retentativa recarrega a aba
    # em cima de quem esta colando o codigo.
    assert ESPERA_LOGIN_S >= 300
    print("OK espera_minima")


def test_sistema_sem_deteccao_para_apos_o_teto():
    assert deve_tentar("pje_tjmg_2inst", False, ESPERA_LOGIN_S * 9,
                       MAX_TENTATIVAS_LOGIN) is False
    print("OK cego_tentativas_esgotadas")


def test_pje_dispara_assim_que_o_login_aparece():
    # sem esperar os 3 min: o endereco do PJe diz a verdade.
    assert deve_tentar("pje_tjmg", True, 0, 0) is True
    assert deve_tentar("pje_tjmg", False, 0, 0) is False
    print("OK pje_imediato")


def test_pje_logado_mas_sem_sessao_nao_vira_laco_apertado():
    # detectado logado e ja tentou: precisa respeitar o intervalo, senao o agente
    # tentaria de 3 em 3 segundos ate o timeout.
    assert deve_tentar("pje_tjmg", True, 5, 1) is False
    assert deve_tentar("pje_tjmg", True, ESPERA_LOGIN_S, 1) is True
    print("OK pje_intervalo_minimo")


def test_espera_termina_quando_ninguem_tem_mais_tentativa():
    sistemas = ["eproc_tjmg", "pje_tjmg_2inst"]
    esgotadas = {s: MAX_TENTATIVAS_LOGIN for s in sistemas}
    assert _esgotou_as_tentativas(sistemas, set(), esgotadas) is True
    assert _esgotou_as_tentativas(sistemas, {"eproc_tjmg"}, esgotadas) is True
    print("OK espera_encerra")


def test_espera_continua_enquanto_alguem_pode_tentar():
    sistemas = ["eproc_tjmg", "pje_tjmg"]
    tentativas = {"eproc_tjmg": MAX_TENTATIVAS_LOGIN, "pje_tjmg": 0}
    assert _esgotou_as_tentativas(sistemas, set(), tentativas) is False
    print("OK espera_continua")


def test_tudo_processado_nao_conta_como_esgotado():
    # sem isto o laco anunciaria "login nao concluido" no fim de uma rodada boa.
    sistemas = ["eproc_tjmg"]
    assert _esgotou_as_tentativas(sistemas, {"eproc_tjmg"}, {"eproc_tjmg": 1}) is False
    print("OK sem_restantes")


if __name__ == "__main__":
    test_pagina_de_login_com_formulario_nao_esta_logado()
    test_mesma_pagina_sem_formulario_esta_logado()
    test_pagina_interna_logada()
    test_indicador_de_logout_na_url()
    test_host_errado()
    test_campo_password_comum_e_tela_de_login()
    test_caixa_de_senha_do_eproc_e_type_text()
    test_pagina_interna_nao_tem_campo_de_senha()
    test_pagina_sem_campo_nenhum()
    test_eproc_e_rupe_nao_tem_deteccao_por_url()
    test_sistema_sem_deteccao_tenta_de_cara()
    test_sistema_sem_deteccao_nao_tenta_antes_da_hora()
    test_sistema_sem_deteccao_tenta_quando_o_tempo_fecha()
    test_espera_entre_tentativas_cobre_codigo_por_email()
    test_sistema_sem_deteccao_para_apos_o_teto()
    test_pje_dispara_assim_que_o_login_aparece()
    test_pje_logado_mas_sem_sessao_nao_vira_laco_apertado()
    test_espera_termina_quando_ninguem_tem_mais_tentativa()
    test_espera_continua_enquanto_alguem_pode_tentar()
    test_tudo_processado_nao_conta_como_esgotado()
    print("Todos os testes passaram.")
