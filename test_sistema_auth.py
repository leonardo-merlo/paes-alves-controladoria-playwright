"""test_sistema_auth.py — testes da detecção de login. Rodar: python test_sistema_auth.py"""

from sistema_auth import _avaliar_login

RUPE_LOGIN = "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe"
RUPE_INTERNO = "https://pe.tjmg.jus.br/rupe/portaljus/intranet/processo/processos.rupe?acao=0"


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


if __name__ == "__main__":
    test_pagina_de_login_com_formulario_nao_esta_logado()
    test_mesma_pagina_sem_formulario_esta_logado()
    test_pagina_interna_logada()
    test_indicador_de_logout_na_url()
    test_host_errado()
    print("Todos os testes passaram.")
