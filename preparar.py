"""
preparar.py — Abre o Chrome com as abas dos sistemas necessários para extração.

Consulta processos pendentes no Supabase, identifica os sistemas e abre o Chrome
com CDP já nas URLs corretas. Henrique só precisa fazer login e rodar /extrair.

Uso:
  python preparar.py
"""

import subprocess
import sys
from supabase_writer import _get_client, _carregar_env
from cnj_router import rotear

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_DEBUG_DIR = r"C:\chrome-debug"
CDP_PORT = 9222


def main() -> None:
    _carregar_env()
    client = _get_client()

    res = client.table("processos").select("numero_cnj").eq("pje_status", "pendente").eq("duplicata", False).execute()
    pendentes = res.data or []

    if not pendentes:
        print("Nenhum processo pendente. Nada a fazer.")
        return

    urls_por_sistema: dict[str, str] = {}
    sem_url: list[str] = []

    for row in pendentes:
        cnj = row["numero_cnj"]
        info = rotear(cnj)
        if info.url:
            urls_por_sistema[info.sistema] = info.url
        else:
            sem_url.append(f"{cnj} ({info.sistema})")

    if sem_url:
        print(f"Atenção: {len(sem_url)} CNJ(s) sem sistema mapeado — serão ignorados pelo extrator:")
        for s in sem_url:
            print(f"  {s}")

    if not urls_por_sistema:
        print("Nenhum sistema com URL mapeada. Verifique cnj_router.py.")
        return

    urls = list(urls_por_sistema.values())
    print(f"\nAbrindo Chrome com {len(urls)} aba(s):")
    for sistema, url in urls_por_sistema.items():
        print(f"  {sistema}: {url}")

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={CHROME_DEBUG_DIR}",
        *urls,
    ]
    subprocess.Popen(cmd)
    print("\nChrome aberto. Faça login em cada aba e depois rode: python runner.py")


if __name__ == "__main__":
    main()
