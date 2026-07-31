"""test_sistema_auth.py — testes da detecção de login. Rodar: python test_sistema_auth.py"""

from sistema_auth import _avaliar_login, _tem_campo_de_senha

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
    print("Todos os testes passaram.")
