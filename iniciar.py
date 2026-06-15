"""
iniciar.py — Comando único: abre o Chrome nos sistemas necessários e, assim que
o login é detectado, dispara a extração automaticamente. Sem Enter, sem segundo
comando.

Substitui o par preparar.py + runner.py para o uso do dia a dia.

Uso:
  python iniciar.py
"""

import asyncio
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright

from cnj_router import rotear
from runner import modo_supabase
from supabase_writer import _get_client, _carregar_env

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_DEBUG_DIR = r"C:\chrome-debug"
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"


def _coletar_urls_pendentes() -> list[str]:
    """Consulta os pendentes no Supabase e devolve as URLs únicas a abrir."""
    _carregar_env()
    client = _get_client()
    res = (
        client.table("processos")
        .select("numero_cnj")
        .in_("pje_status", ["pendente", "erro_browser", "captcha_bloqueado"])
        .eq("duplicata", False)
        .execute()
    )
    pendentes = res.data or []

    urls_por_sistema: dict[str, str] = {}
    for row in pendentes:
        info = rotear(row["numero_cnj"])
        if info.url:
            urls_por_sistema[info.sistema] = info.url

    if urls_por_sistema:
        print(f"Abrindo Chrome com {len(urls_por_sistema)} aba(s):")
        for sistema, url in urls_por_sistema.items():
            print(f"  {sistema}: {url}")

    return list(urls_por_sistema.values())


async def _aguardar_cdp_pronto(tentativas: int = 30, intervalo_s: float = 0.5) -> bool:
    """Espera o Chrome subir e aceitar conexão CDP antes de prosseguir."""
    async with async_playwright() as p:
        for _ in range(tentativas):
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
                await browser.close()
                return True
            except Exception:
                await asyncio.sleep(intervalo_s)
    return False


async def main() -> dict:
    urls = _coletar_urls_pendentes()
    if not urls:
        print("Nenhum processo pendente. Nada a fazer.")
        return {"total": 0, "processados": 0, "erros": 0}

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={CHROME_DEBUG_DIR}",
        *urls,
    ]
    subprocess.Popen(cmd)

    if not await _aguardar_cdp_pronto():
        print("Não foi possível conectar ao Chrome (CDP). Verifique se ele abriu.")
        return {"total": 0, "processados": 0, "erros": 0, "cdp_falhou": True}

    # modo_auto=True: observa o login e dispara a extração sozinho.
    return await modo_supabase(modo_auto=True)


if __name__ == "__main__":
    asyncio.run(main())
