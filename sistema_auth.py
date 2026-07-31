"""
sistema_auth.py — Detecta autenticação por sistema e abre abas no Chrome via CDP.
"""

import asyncio
import json
import time
import urllib.request
import urllib.parse
from typing import Callable, Awaitable

CDP_URL = "http://localhost:9222"

# A leitura do DOM abre uma conexão Playwright; a cada 3s seria desperdício.
# 12s mantém a detecção de login rápida sem pesar no loop de espera.
INTERVALO_LEITURA_DOM_S = 12.0

# URL base de cada sistema para abrir no Chrome
SISTEMA_URLS = {
    "pje_tjmg":       "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam",
    "eproc_tjmg":     "https://eproc1g.tjmg.jus.br/eproc/",
    "pje_tjmg_2inst": "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe",
    "pje_tjrj":       "https://tjrj.pje.jus.br/",
    "eproc_trf2":     "https://eproc.trf2.jus.br/",
    "eproc_trf6":     "https://eproc1g.trf6.jus.br/eproc/",   # JFMG — 1ª instância federal
    "eproc_trf6_2g":  "https://eproc2g.trf6.jus.br/eproc/",   # TRF6 — 2ª instância federal
}

# Host esperado na URL quando a sessão está ativa
SISTEMA_HOST = {
    "pje_tjmg":       "pje.tjmg.jus.br",
    "eproc_tjmg":     "eproc1g.tjmg.jus.br",
    "pje_tjmg_2inst": "pe.tjmg.jus.br",
    "pje_tjrj":       "tjrj.pje.jus.br",
    "eproc_trf2":     "eproc.trf2.jus.br",
    "eproc_trf6":     "eproc1g.trf6.jus.br",    # JFMG — 1ª instância
    "eproc_trf6_2g":  "eproc2g.trf6.jus.br",    # TRF6 — 2ª instância
}

# Fragmentos de URL que indicam sessão encerrada ou tela de login
INDICADORES_DESLOGADO = ["/login", "/Login", "login.seam", "token_invalid",
                         "sessao_expirada", "externo_controlador"]


def _get_abas_chrome() -> list[dict]:
    """Lista as abas abertas no Chrome via CDP HTTP — sem Playwright, sem Avast."""
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json", timeout=2) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


# Campo de senha visível = a página ainda está pedindo login, por mais que o
# endereço pareça o de dentro do sistema. Foi exatamente assim que eProc, TRF6 e
# RUPE eram dados como logados no instante zero: o Chrome abre já no endereço
# certo e a extração começava antes de o Henrique digitar a senha.
JS_TEM_FORM_LOGIN = """() => {
    for (const campo of document.querySelectorAll('input[type="password"]')) {
        const r = campo.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) return true;
    }
    return false;
}"""

_ultima_leitura_dom: float = 0.0
_forms_login: dict[str, bool] = {}
_avisou_falha_dom: bool = False


def _avaliar_login(url: str, sistema: str, tem_form_login: bool) -> bool:
    """Decide se a aba representa uma sessão ativa. Função pura — ver test_sistema_auth.py."""
    host = SISTEMA_HOST.get(sistema, "")
    if not host or host not in url:
        return False
    if any(ind in url for ind in INDICADORES_DESLOGADO):
        return False
    return not tem_form_login


async def _ler_forms_login(hosts: set[str]) -> dict[str, bool]:
    """
    Para cada aba dos hosts pedidos, diz se há campo de senha visível.
    SÓ LÊ a página: nunca navega e nunca clica, porque roda enquanto o Henrique
    está digitando a senha. Devolve {} se não der para ler.
    """
    # import local: o loop de espera não deve pagar o custo do Playwright
    # quando não há nenhuma aba a conferir.
    from playwright.async_api import async_playwright

    playwright = None
    browser = None
    leitura: dict[str, bool] = {}
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.connect_over_cdp(CDP_URL)
        for ctx in browser.contexts:
            for page in ctx.pages:
                if not any(h in page.url for h in hosts):
                    continue
                try:
                    leitura[page.url] = bool(await page.evaluate(JS_TEM_FORM_LOGIN))
                except Exception:
                    pass  # aba navegando: fica de fora e a URL decide sozinha
        return leitura
    except Exception:
        return {}
    finally:
        if browser:
            try:
                await browser.close()  # CDP: close() apenas desconecta
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass


async def verificar_autenticacoes(sistemas: list[str]) -> dict[str, bool]:
    """
    Verifica quais sistemas têm sessão ativa: endereço da aba (via CDP HTTP) mais
    a confirmação de que a página não está exibindo formulário de login.
    """
    global _ultima_leitura_dom, _forms_login, _avisou_falha_dom

    status: dict[str, bool] = {s: False for s in sistemas}
    abas = _get_abas_chrome()
    hosts = {SISTEMA_HOST[s] for s in sistemas if s in SISTEMA_HOST}

    agora = time.monotonic()
    if hosts and agora - _ultima_leitura_dom >= INTERVALO_LEITURA_DOM_S:
        _forms_login = await _ler_forms_login(hosts)
        _ultima_leitura_dom = agora
        if not _forms_login and not _avisou_falha_dom:
            # sem a leitura do DOM a checagem vira só o endereço — que é o
            # comportamento antigo, e o antigo errava. Melhor dizer em voz alta.
            print("  Aviso: não foi possível ler a página das abas — "
                  "detecção de login caiu para o endereço apenas.")
            _avisou_falha_dom = True

    for aba in abas:
        url = aba.get("url", "")
        tem_form = _forms_login.get(url, False)
        for sistema in sistemas:
            if not status[sistema] and _avaliar_login(url, sistema, tem_form):
                status[sistema] = True
    return status


async def abrir_abas_para_auth(sistemas_nao_autenticados: list[str]) -> None:
    """
    Abre uma aba no Chrome para cada sistema que precisa de login,
    usando o endpoint CDP HTTP — sem Playwright.
    Não abre se já existe uma aba para aquele sistema.
    """
    if not sistemas_nao_autenticados:
        return
    abas_existentes = _get_abas_chrome()
    for sistema in sistemas_nao_autenticados:
        url = SISTEMA_URLS.get(sistema)
        if not url:
            continue
        host = SISTEMA_HOST.get(sistema, "")
        if any(host in aba.get("url", "") for aba in abas_existentes):
            print(f"  Aba já aberta: {sistema}")
            continue
        try:
            urllib.request.urlopen(f"{CDP_URL}/json/new?{url}", timeout=2).close()
            print(f"  Aba aberta: {url}")
        except Exception as e:
            print(f"  Aviso: erro ao abrir aba {sistema} — {e}")
            print(f"  Abra manualmente: {url}")


async def monitorar_logins_e_processar(
    sistemas: list[str],
    ao_logar: Callable[[str], Awaitable[None]],
    timeout_s: int = 600,
    intervalo_s: int = 3,
) -> set[str]:
    """
    Abre abas para os sistemas que precisam de login e fica monitorando.
    Assim que cada sistema logar, dispara a extração dele imediatamente —
    sem esperar os outros. Sistemas que não logarem dentro do timeout são
    pulados e marcados para retentativa automática.
    Retorna o conjunto de sistemas que foram processados.
    """
    loop = asyncio.get_running_loop()
    inicio = loop.time()
    processados: set[str] = set()
    ja_avisados: set[str] = set()

    print("\nVerificando autenticação nos sistemas...")
    status = await verificar_autenticacoes(sistemas)
    ja_logados = [s for s, ok in status.items() if ok]
    nao_logados = [s for s, ok in status.items() if not ok]

    if ja_logados:
        print(f"  Sessão ativa: {', '.join(ja_logados)}")
    if nao_logados:
        print(f"  Necessita login: {', '.join(nao_logados)}")
        await abrir_abas_para_auth(nao_logados)

    print(f"\nA extração inicia em cada sistema assim que o login for detectado.")
    print(f"Timeout por sistema: {timeout_s // 60} min.\n")

    # se há sistemas com sessão ativa E sistemas aguardando login, dar uma janela
    # para o usuário concluir os logins antes de processar qualquer sistema —
    # evita processar um sistema com sessão aparentemente ativa que na verdade expirou
    GRACA_S = 30
    if ja_logados and nao_logados:
        print(f"  Aguardando {GRACA_S}s para que você conclua os logins pendentes...")
        await asyncio.sleep(GRACA_S)
        status = await verificar_autenticacoes(sistemas)
        ja_logados  = [s for s, ok in status.items() if ok]
        nao_logados = [s for s, ok in status.items() if not ok]
        if nao_logados:
            await abrir_abas_para_auth(nao_logados)

    for sistema in ja_logados:
        ja_avisados.add(sistema)
        processados.add(sistema)
        await ao_logar(sistema)

    # zera o relógio antes de esperar os sistemas pendentes: o tempo gasto
    # extraindo os sistemas já logados acima não deve consumir a janela de
    # login dos que ainda faltam (senão um sistema logado a tempo é pulado).
    inicio = loop.time()

    while len(processados) < len(sistemas):
        if loop.time() - inicio > timeout_s:
            restantes = [s for s in sistemas if s not in processados]
            print(f"\nTimeout: {', '.join(restantes)} não respondeu — pulando.")
            break

        restantes = [s for s in sistemas if s not in processados]
        status = await verificar_autenticacoes(restantes)

        for sistema, ok in status.items():
            if ok and sistema not in ja_avisados:
                ja_avisados.add(sistema)
                print(f"  ✓ Login detectado: {sistema}")
            if ok and sistema not in processados:
                processados.add(sistema)
                await ao_logar(sistema)
                # zerar o contador após cada extração — o usuário tem tempo cheio
                # para logar no próximo sistema, independente de quanto demorou a extração anterior
                inicio = loop.time()

        if any(s not in processados for s in sistemas):
            await asyncio.sleep(intervalo_s)

    return processados


async def aguardar_login_automatico(
    sistemas: list[str],
    timeout_s: int = 600,
    intervalo_s: int = 3,
) -> bool:
    """Aguarda todos os sistemas logarem. Usado no modo manual (Enter)."""
    loop = asyncio.get_event_loop()
    inicio = loop.time()
    ja_avisados: set[str] = set()

    print(f"\nAguardando login (extração começa sozinha). Sistemas: {', '.join(sistemas)}")
    print(f"Faça login em cada aba. Timeout: {timeout_s // 60} min.\n")

    while True:
        status = await verificar_autenticacoes(sistemas)

        for sistema, ok in status.items():
            if ok and sistema not in ja_avisados:
                ja_avisados.add(sistema)
                print(f"  ✓ Login detectado: {sistema}")

        if all(status.values()):
            print("\nTodos os sistemas logados. Iniciando extração automaticamente.\n")
            return True

        if loop.time() - inicio > timeout_s:
            faltando = [s for s, ok in status.items() if not ok]
            print(f"\nTimeout: login não concluído em {', '.join(faltando)}.")
            return False

        await asyncio.sleep(intervalo_s)


async def preparar_autenticacao(sistemas: list[str], modo_auto: bool = False) -> bool:
    """
    Verifica autenticação e aguarda o login do usuário.

    modo_auto=False → abre as abas faltantes e espera Enter (fluxo antigo).
    modo_auto=True  → não pede Enter; observa o Chrome e dispara sozinho
                      assim que todos os sistemas logarem.
    """
    print("\nVerificando autenticação nos sistemas...")
    status = await verificar_autenticacoes(sistemas)

    ja_logados = [s for s, ok in status.items() if ok]
    nao_logados = [s for s, ok in status.items() if not ok]

    if ja_logados:
        print(f"  Sessao ativa: {', '.join(ja_logados)}")

    if not nao_logados:
        print("Autenticacao confirmada. Iniciando extracoes.\n")
        return True

    print(f"  Necessita login: {', '.join(nao_logados)}")

    if modo_auto:
        return await aguardar_login_automatico(sistemas)

    print("\nAbrindo abas no Chrome...")
    await abrir_abas_para_auth(nao_logados)
    print("\nFaca login nos sistemas indicados.")
    print("Pressione Enter quando estiver pronto (ou Ctrl+C para cancelar)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelado.")
        return False

    print("Autenticacao confirmada. Iniciando extracoes.\n")
    return True
