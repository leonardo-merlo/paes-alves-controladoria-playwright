"""test_chrome_recuperacao.py — a recuperação contra um Chrome de verdade.

Sobe um Chrome descartável (headless, perfil temporário, porta própria) por
teste, sem tocar no Chrome do robô. Pula se o Chrome não estiver instalado.
Rodar: python test_chrome_recuperacao.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from contextlib import contextmanager

from playwright.async_api import async_playwright

import chrome_saude
from sistema_auth import CHROME_PATH

PORTA = 9341
CDP = f"http://127.0.0.1:{PORTA}"
HOST = "127.0.0.1"                 # faz o papel do endereço do sistema
URL_SISTEMA = f"{CDP}/json/version"
ABA_COM_ALERTA = "data:text/html,<script>setTimeout(()=>alert('preso'),300)</script>"


@contextmanager
def chrome_descartavel():
    perfil = tempfile.mkdtemp(prefix="chrome-teste-")
    proc = subprocess.Popen([CHROME_PATH, f"--remote-debugging-port={PORTA}",
                             f"--user-data-dir={perfil}", "--headless=new",
                             "--no-first-run", "data:text/html,<h1>inicial</h1>"])
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"{CDP}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        yield
    finally:
        proc.kill()
        proc.wait()
        shutil.rmtree(perfil, ignore_errors=True)


def _abrir(url: str) -> None:
    urllib.request.urlopen(urllib.request.Request(f"{CDP}/json/new?{url}", method="PUT"),
                           timeout=3).close()


async def _conecta(prazo_ms: int = 8000) -> bool:
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(CDP, timeout=prazo_ms)
        await browser.close()
        return True
    except Exception:
        return False
    finally:
        await pw.stop()


def test_aba_presa_em_alerta_trava_e_a_recuperacao_destrava():
    with chrome_descartavel():
        _abrir(ABA_COM_ALERTA)
        time.sleep(2)
        travou_antes = not asyncio.run(_conecta())
        asyncio.run(chrome_saude.recuperar_conexao(HOST, URL_SISTEMA, CDP, prazo=3))
        assert travou_antes and asyncio.run(_conecta())
    print("OK alerta_trava_e_recuperacao_destrava")


def test_recuperacao_fecha_so_a_aba_muda():
    with chrome_descartavel():
        _abrir(ABA_COM_ALERTA)
        time.sleep(2)
        r = asyncio.run(chrome_saude.recuperar_conexao(HOST, URL_SISTEMA, CDP, prazo=3))
        restantes = [a["url"] for a in chrome_saude.listar_abas(CDP) if a.get("type") == "page"]
        assert len(r["fechadas"]) == 1 and any("inicial" in u for u in restantes)
    print("OK fecha_so_a_muda")


def test_sistema_sem_aba_ganha_uma_nova():
    with chrome_descartavel():
        abriu = asyncio.run(chrome_saude.garantir_aba(HOST, URL_SISTEMA, CDP, espera_s=5))
        assert abriu and chrome_saude.tem_aba_do_host(chrome_saude.listar_abas(CDP), HOST)
    print("OK sistema_sem_aba_ganha_uma")


def test_sistema_com_aba_nao_ganha_outra():
    with chrome_descartavel():
        _abrir(URL_SISTEMA)
        time.sleep(1)
        assert asyncio.run(chrome_saude.garantir_aba(HOST, URL_SISTEMA, CDP)) is False
    print("OK sistema_com_aba_nao_ganha_outra")


def test_aba_que_sumiu_no_meio_e_reaberta():
    with chrome_descartavel():
        _abrir(URL_SISTEMA)
        time.sleep(1)
        aba = next(a for a in chrome_saude.listar_abas(CDP)
                   if a.get("type") == "page" and HOST in (a.get("url") or ""))
        chrome_saude.fechar_aba(aba["id"], CDP)
        time.sleep(1)
        assert asyncio.run(chrome_saude.garantir_aba(HOST, URL_SISTEMA, CDP, espera_s=5))
    print("OK aba_sumida_reaberta")


if __name__ == "__main__":
    if not os.path.exists(CHROME_PATH):
        print(f"Chrome não encontrado em {CHROME_PATH} — testes pulados.")
    else:
        for nome, funcao in sorted(list(globals().items())):
            if nome.startswith("test_"):
                funcao()
        print("\nTodos os testes de recuperação com Chrome real passaram.")
