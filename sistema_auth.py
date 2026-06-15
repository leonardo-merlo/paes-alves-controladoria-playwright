"""
sistema_auth.py — Detecta autenticação por sistema e abre abas no Chrome via CDP.
"""

import asyncio
from playwright.async_api import async_playwright, Browser, Page

CDP_URL = "http://localhost:9222"

# URL base de cada sistema para abrir no Chrome
SISTEMA_URLS = {
    "pje_tjmg":       "https://pje.tjmg.jus.br/pje/Processo/ConsultaProcesso/listView.seam",
    "eproc_tjmg":     "https://eproc1g.tjmg.jus.br/eproc/",
    "pje_tjmg_2inst": "https://pe.tjmg.jus.br/rupe/portaljus/intranet/principal.rupe",
    "pje_tjrj":       "https://tjrj.pje.jus.br/",
    "eproc_trf2":     "https://eproc.trf2.jus.br/",
    "eproc_trf6":     "https://eproc1g.trf6.jus.br/eproc/",
}

# Fragmento de URL que indica sessão ativa (sem redirecionamento para login)
SISTEMA_HOST = {
    "pje_tjmg":       "pje.tjmg.jus.br",
    "eproc_tjmg":     "eproc1g.tjmg.jus.br",
    "pje_tjmg_2inst": "pe.tjmg.jus.br",
    "pje_tjrj":       "tjrj.pje.jus.br",
    "eproc_trf2":     "eproc.trf2.jus.br",
    "eproc_trf6":     "eproc1g.trf6.jus.br",
}

# eProc redireciona para externo_controlador quando a sessão cai
INDICADORES_DESLOGADO = ["/login", "/Login", "login.seam", "token_invalid",
                         "sessao_expirada", "externo_controlador"]


def _avaliar_login(url: str, sistema: str, tem_form_login: bool) -> bool:
    """
    Decide se uma aba está logada, a partir de sinais não-intrusivos (sem navegar).

    Lógica pura e testável:
      - precisa estar no host do sistema;
      - a URL não pode conter indicador de deslogado;
      - a página não pode exibir formulário de login (campo de senha).

    O terceiro critério é o que corrige o falso-positivo: a landing de login de
    alguns sistemas (ex.: RUPE) está no mesmo host e sem keyword de logout na URL,
    mas ainda mostra o formulário de login.
    """
    host = SISTEMA_HOST.get(sistema, "")
    if host not in url:
        return False
    if any(ind in url for ind in INDICADORES_DESLOGADO):
        return False
    if tem_form_login:
        return False
    return True


async def _tem_form_login(page: Page) -> bool:
    """True se houver campo de senha em qualquer frame da página (sem navegar)."""
    for frame in page.frames:
        try:
            if await frame.evaluate("!!document.querySelector('input[type=password]')"):
                return True
        except Exception:
            continue
    return False


async def _esta_logado(page: Page, sistema: str) -> bool:
    tem_form = await _tem_form_login(page)
    return _avaliar_login(page.url, sistema, tem_form)


async def verificar_autenticacoes(sistemas: list[str]) -> dict[str, bool]:
    """
    Conecta ao Chrome e verifica se cada sistema já tem sessão ativa.
    Retorna {sistema: True/False}.
    """
    status: dict[str, bool] = {s: False for s in sistemas}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            for ctx in browser.contexts:
                for page in ctx.pages:
                    for sistema in sistemas:
                        if not status[sistema] and await _esta_logado(page, sistema):
                            status[sistema] = True
            await browser.close()
    except Exception as e:
        print(f"  Aviso: não foi possível conectar ao Chrome — {e}")

    return status


async def abrir_abas_para_auth(sistemas_nao_autenticados: list[str]) -> None:
    """
    Abre uma nova aba no Chrome para cada sistema que precisa de autenticação.
    """
    if not sistemas_nao_autenticados:
        return

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            for sistema in sistemas_nao_autenticados:
                url = SISTEMA_URLS.get(sistema)
                if url:
                    page = await ctx.new_page()
                    await page.goto(url)
                    print(f"  Aba aberta: {url}")
            await browser.close()
    except Exception as e:
        print(f"  Aviso: erro ao abrir abas — {e}")
        print("  Abra manualmente as URLs abaixo:")
        for s in sistemas_nao_autenticados:
            print(f"    {SISTEMA_URLS.get(s, s)}")


async def aguardar_login_automatico(
    sistemas: list[str],
    timeout_s: int = 600,
    intervalo_s: int = 3,
) -> bool:
    """
    Fica observando o Chrome e dispara sozinho quando TODOS os sistemas
    necessários tiverem sessão ativa. Não pede Enter.

    Retorna True quando todos logaram; False se estourar o timeout.
    """
    loop = asyncio.get_event_loop()
    inicio = loop.time()
    ja_avisados: set[str] = set()

    print(f"\nAguardando login (extração começa sozinha). Sistemas: {', '.join(sistemas)}")
    print(f"Faça login em cada aba. Timeout: {timeout_s // 60} min.\n")

    while True:
        status = await verificar_autenticacoes(sistemas)

        # avisa cada sistema que acabou de logar, uma única vez
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
                      assim que todos os sistemas logarem (as abas já foram
                      abertas por iniciar.py).
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
