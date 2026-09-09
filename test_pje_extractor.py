"""test_pje_extractor.py — testes da escolha de aba do PJe. Rodar: python test_pje_extractor.py

Existe por causa de 09/09/2026. Até esta data `encontrar_aba_pje` tinha um
fallback que, quando não achava aba do PJe, devolvia `ctx.pages[0]` — uma aba
qualquer, de qualquer sistema. E quem recebe essa aba chama `verificar_sessao`,
que faz `page.goto(PJE_URL)`. Ou seja: não era só usar a aba errada, era
**navegar a aba de outro sistema**, destruindo-a.

É o único mecanismo no projeto capaz de fazer a aba do eProc sumir do Chrome, e
"Nenhuma aba do eProc" foi o erro que segurou 35 processos de 19/08 a 09/09.

O fallback disparava porque o `if` só reconhecia `pje.tjmg.jus.br`, e antes do
login a aba do PJe fica no SSO (`sso.cloud.pje.jus.br`) — medido em 09/09 às
10:47:26. Então o PJe não achava a própria aba e pegava a do vizinho. Por isso
os dois casos são testados juntos: tirar só o fallback deixaria o PJe sem achar
a aba dele quando ela está no SSO.
"""

from pje_extractor import encontrar_aba_pje
import asyncio

SSO = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/auth?client_id=pje-tjmg-1g"
PJE = "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam"
EPROC = "https://eproc1g.tjmg.jus.br/eproc/controlador.php?acao=painel_adv_listar"
RUPE = "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe"


class FakePage:
    def __init__(self, url):
        self.url = url


class FakeContext:
    def __init__(self, urls):
        self.pages = [FakePage(u) for u in urls]


class FakeBrowser:
    def __init__(self, *contextos):
        self.contexts = [FakeContext(urls) for urls in contextos]


def achar(*contextos):
    return asyncio.run(encontrar_aba_pje(FakeBrowser(*contextos)))


def erro_ao_achar(*contextos):
    try:
        achar(*contextos)
    except RuntimeError as e:
        return str(e)
    return None


def test_acha_a_aba_do_pje_pelo_host_principal():
    assert achar([EPROC, PJE, RUPE]).url == PJE
    print("OK acha_a_aba_do_pje_pelo_host_principal")


def test_acha_a_aba_do_pje_quando_ela_esta_no_sso():
    """Antes do login a aba do PJe fica no SSO. Continua sendo a aba dele."""
    assert achar([EPROC, SSO, RUPE]).url == SSO
    print("OK acha_a_aba_do_pje_quando_ela_esta_no_sso")


def test_prefere_o_host_principal_quando_existem_os_dois():
    """Aba já logada vale mais que a do SSO, que pode ter ficado para trás."""
    assert achar([SSO, EPROC, PJE]).url == PJE
    print("OK prefere_o_host_principal_quando_existem_os_dois")


def test_nao_rouba_a_aba_de_outro_sistema():
    """O caso que sumia com a aba do eProc: sem aba do PJe, é erro, não roubo."""
    msg = erro_ao_achar([EPROC, RUPE])
    assert msg is not None, "devolveu uma aba de outro sistema em vez de falhar"
    assert "Nenhuma aba do PJe" in msg, msg
    print("OK nao_rouba_a_aba_de_outro_sistema")


def test_nao_rouba_nem_quando_ha_uma_aba_so():
    msg = erro_ao_achar([EPROC])
    assert msg is not None, "roubou a única aba aberta, que era do eProc"
    print("OK nao_rouba_nem_quando_ha_uma_aba_so")


def test_chrome_sem_aba_nenhuma():
    assert erro_ao_achar([]) is not None
    print("OK chrome_sem_aba_nenhuma")


def test_procura_em_todos_os_contextos():
    assert achar([EPROC], [RUPE, PJE]).url == PJE
    print("OK procura_em_todos_os_contextos")


if __name__ == "__main__":
    test_acha_a_aba_do_pje_pelo_host_principal()
    test_acha_a_aba_do_pje_quando_ela_esta_no_sso()
    test_prefere_o_host_principal_quando_existem_os_dois()
    test_nao_rouba_a_aba_de_outro_sistema()
    test_nao_rouba_nem_quando_ha_uma_aba_so()
    test_chrome_sem_aba_nenhuma()
    test_procura_em_todos_os_contextos()
    print("Todos os testes passaram.")
