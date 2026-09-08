"""
Testes das funções puras da observabilidade e do pré-voo.

Só o que é decidível sem Chrome: formatação da linha, resumo de abas e o
veredito do pré-voo a partir de uma lista de abas dada. A gravação em si (que
fala com o Supabase) não é testada aqui de propósito — o que ela precisa
garantir é "nunca levantar exceção", e isso está coberto pelo `except` largo
do módulo, não por asserção.

Rodar: venv\\Scripts\\python.exe test_observabilidade.py
"""

from observabilidade import _linha_console, resumir_urls
from runner import estado_de_previvo


def _aba(url: str, tipo: str = "page") -> dict:
    return {"url": url, "type": tipo, "id": url}


# ── linha do console ──────────────────────────────────────────────

def test_linha_de_sucesso_usa_ponto():
    linha = _linha_console("cnj.fim", True, "eproc_tjmg", "123", "3 documentos")
    assert linha.startswith("[ok] cnj.fim")
    assert "[eproc_tjmg]" in linha and "123" in linha and "3 documentos" in linha
    print("OK linha_de_sucesso_usa_ponto")


def test_linha_de_falha_marca_diferente():
    assert _linha_console("cnj.fim", False, None, None, None).startswith("[FALHA] cnj.fim")
    print("OK linha_de_falha_marca_diferente")


def test_linha_sem_extras_nao_deixa_lixo():
    assert _linha_console("abrir.inicio", True, None, None, None) == "[ok] abrir.inicio"
    print("OK linha_sem_extras_nao_deixa_lixo")


# ── resumo de abas ────────────────────────────────────────────────

def test_sem_aba_diz_que_nao_ha_nenhuma():
    assert resumir_urls([]) == "nenhuma aba aberta"
    print("OK sem_aba_diz_que_nao_ha_nenhuma")


def test_lista_as_urls_abertas():
    texto = resumir_urls([_aba("https://eproc1g.tjmg.jus.br/eproc/"),
                          _aba("https://pje.tjmg.jus.br/pje/")])
    assert "eproc1g.tjmg.jus.br" in texto and "pje.tjmg.jus.br" in texto
    print("OK lista_as_urls_abertas")


def test_lista_longa_e_cortada_mas_avisa_quantas_sobraram():
    texto = resumir_urls([_aba(f"https://x{i}.jus.br") for i in range(20)], limite=5)
    assert "(+15)" in texto
    print("OK lista_longa_e_cortada_mas_avisa_quantas_sobraram")


def test_aba_que_nao_e_pagina_nao_conta_como_url():
    texto = resumir_urls([_aba("https://x.jus.br", tipo="iframe")])
    assert "nenhuma do tipo página" in texto
    print("OK aba_que_nao_e_pagina_nao_conta_como_url")


# ── pré-voo ───────────────────────────────────────────────────────

def test_previvo_sem_aba_do_sistema_reprova():
    tem_aba, frase = estado_de_previvo([_aba("https://pje.tjmg.jus.br/pje/")], "eproc_tjmg")
    assert tem_aba is False
    assert "SEM ABA" in frase
    print("OK previvo_sem_aba_do_sistema_reprova")


def test_previvo_com_aba_do_sistema_aprova():
    tem_aba, _ = estado_de_previvo([_aba("https://eproc1g.tjmg.jus.br/eproc/")], "eproc_tjmg")
    assert tem_aba is True
    print("OK previvo_com_aba_do_sistema_aprova")


def test_previvo_nao_finge_saber_login_do_eproc():
    """eProc e RUPE estão em SEM_DETECCAO_DE_LOGIN: a URL não distingue."""
    _, frase = estado_de_previvo([_aba("https://eproc1g.tjmg.jus.br/eproc/")], "eproc_tjmg")
    assert "não é detectável" in frase
    print("OK previvo_nao_finge_saber_login_do_eproc")


def test_previvo_ve_tela_de_login_do_pje():
    _, frase = estado_de_previvo([_aba("https://pje.tjmg.jus.br/pje/login.seam")], "pje_tjmg")
    assert "tela de login" in frase
    print("OK previvo_ve_tela_de_login_do_pje")


def test_previvo_ve_pje_logado():
    _, frase = estado_de_previvo(
        [_aba("https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam")],
        "pje_tjmg")
    assert "cara de logada" in frase
    print("OK previvo_ve_pje_logado")


def test_previvo_ignora_aba_que_nao_e_pagina():
    """Um iframe do tribunal não é a aba do operador — não pode contar como presente."""
    tem_aba, _ = estado_de_previvo(
        [_aba("https://eproc1g.tjmg.jus.br/eproc/", tipo="iframe")], "eproc_tjmg")
    assert tem_aba is False
    print("OK previvo_ignora_aba_que_nao_e_pagina")




# ── conferência de abertura: "não sei" não pode virar "não tem" ────

def test_leitura_vazia_nao_acusa_todos_os_sistemas():
    """
    Se a leitura das abas falha (devolve lista vazia) logo depois de o CDP ter
    respondido, isso é "não consegui conferir" — não "nenhum sistema abriu".
    Acusar todos seria trocar uma mentira otimista por uma pessimista.
    """
    from iniciar import sistemas_presentes
    assert sistemas_presentes([], ["eproc_tjmg", "pje_tjmg"]) == set()
    print("OK leitura_vazia_nao_acusa_todos_os_sistemas")


def test_presentes_reconhece_cada_sistema_pelo_dominio():
    from iniciar import sistemas_presentes
    urls = ["https://eproc1g.tjmg.jus.br/eproc/", "https://pe.tjmg.jus.br/rupe/x"]
    assert sistemas_presentes(urls, ["eproc_tjmg", "pje_tjmg_2inst", "pje_tjmg"]) == {
        "eproc_tjmg", "pje_tjmg_2inst"}
    print("OK presentes_reconhece_cada_sistema_pelo_dominio")


def test_eproc_tjmg_e_trf6_nao_se_confundem():
    """Os dois eProc moram em domínios parecidos — trocar um pelo outro faria
    o sistema achar que abriu o que não abriu (o caso de 08/09)."""
    from iniciar import sistemas_presentes
    assert sistemas_presentes(["https://eproc1g.trf6.jus.br/eproc/"],
                              ["eproc_tjmg", "eproc_trf6"]) == {"eproc_trf6"}
    print("OK eproc_tjmg_e_trf6_nao_se_confundem")


if __name__ == "__main__":
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith("test_"):
            funcao()
    print("\nTodos os testes de observabilidade passaram.")
