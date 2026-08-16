"""
iniciar.py — Abre o Chrome nos sistemas necessários e extrai.

Três entradas, para os três comandos que o painel pode mandar:

  abrir_sistemas()  abre o Chrome e as abas, e para aí. O login é feito com calma,
                    sem nenhum relógio correndo.
  extrair()         extrai assumindo que os logins já foram feitos.
  main()            os dois colados, com detecção de login no meio — é o
                    comportamento antigo, e continua sendo o do `iniciar`.

O par separado existe porque os sistemas sem detecção de login (eProc, TRF6,
RUPE) eram tentados no instante em que o Chrome abria, falhavam porque ninguém
tinha logado ainda, e gastavam uma das 4 tentativas à toa. Em 15/08 o RUPE gastou
as 4 assim e ficou de fora da rodada inteira.

Uso:
  python iniciar.py           # abre, espera o login e extrai
  python iniciar.py --abrir   # só abre os sistemas
  python iniciar.py --extrair # só extrai, assumindo login feito
"""

import asyncio
import subprocess
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cnj_router import rotear
from runner import modo_supabase, ordenar_sistemas, MODO_AUTO, MODO_ASSUMIR_LOGADO
from sistema_auth import (
    _get_abas_chrome,
    abrir_aba_cdp,
    CHROME_PATH,
    CHROME_PROFILE,
    CDP_PORT,
    SISTEMA_HOST,
)
from supabase_writer import _get_client, _carregar_env

CDP_URL = f"http://localhost:{CDP_PORT}"


def _coletar_urls_pendentes() -> dict[str, str]:
    """Consulta os pendentes no Supabase e devolve {sistema: url} a abrir."""
    _carregar_env()
    client = _get_client()
    res = (
        client.table("processos")
        .select("numero_cnj, sistema")
        .in_("pje_status", ["pendente", "erro_browser", "captcha_bloqueado"])
        .eq("duplicata", False)
        .execute()
    )
    pendentes = res.data or []

    urls_por_sistema: dict[str, str] = {}
    for row in pendentes:
        info = rotear(row["numero_cnj"], row.get("sistema"))
        if info.url:
            urls_por_sistema[info.sistema] = info.url
    return urls_por_sistema


def _urls_que_faltam(urls_por_sistema: dict[str, str]) -> list[str]:
    """
    Só as URLs dos sistemas que ainda não têm aba aberta.

    Sem isto, cada clique em "Iniciar" jogava 3 abas novas na mesma janela do
    Chrome, porque o chrome.exe era chamado com as URLs sempre, sem olhar o que
    já estava aberto. Medido em 31/07/2026: com 3 abas o extrator conecta em
    0,5s; com 15 abas de sistema judicial ele estoura o limite de 180s do
    Playwright. E, uma vez estourado, aquele Chrome não volta a responder nem
    fechando as abas — só fechando o Chrome inteiro. Foi o que travou a máquina
    do Henrique por uma tarde.
    """
    abertas = [aba.get("url", "") for aba in _get_abas_chrome()]
    faltando: list[str] = []
    for sistema, url in urls_por_sistema.items():
        host = SISTEMA_HOST.get(sistema, "")
        if host and any(host in aberta for aberta in abertas):
            print(f"  {sistema}: aba já aberta — reaproveitando")
            continue
        print(f"  {sistema}: {url}")
        faltando.append(url)
    return faltando


async def _aguardar_cdp_pronto(tentativas: int = 30, intervalo_s: float = 0.5) -> bool:
    """Espera o Chrome subir e aceitar conexão CDP antes de prosseguir."""
    for _ in range(tentativas):
        try:
            urllib.request.urlopen(f"{CDP_URL}/json", timeout=1).close()
            return True
        except Exception:
            await asyncio.sleep(intervalo_s)
    return False


async def abrir_sistemas() -> dict:
    """
    Abre o Chrome e as abas dos sistemas com processo pendente, e para aí.

    Não extrai nada e não espera login: quem loga é o operador, no tempo dele. O
    eProc e o RUPE ainda pedem um código que chega por e-mail — qualquer relógio
    correndo aqui só serviria para queimar tentativa.
    """
    urls_por_sistema = _coletar_urls_pendentes()
    if not urls_por_sistema:
        print("Nenhum processo pendente. Nada a abrir.")
        return {"sistemas": [], "cdp_falhou": False}

    sistemas = ordenar_sistemas(list(urls_por_sistema.keys()))
    if not await _abrir_abas(urls_por_sistema):
        return {"sistemas": sistemas, "cdp_falhou": True}
    return {"sistemas": sistemas, "cdp_falhou": False}


async def extrair() -> dict:
    """
    Extrai assumindo que os logins já foram feitos (pela ação `abrir_sistemas`).

    Sem detecção de login e sem espera: cada sistema é tentado uma vez. Se algum
    ainda estiver deslogado, o runner devolve a fila dele para 'pendente' sem
    queimar processo — basta logar e mandar extrair de novo.
    """
    return await modo_supabase(MODO_ASSUMIR_LOGADO)


async def _abrir_abas(urls_por_sistema: dict[str, str]) -> bool:
    """Garante Chrome de pé com uma aba por sistema. Devolve se o CDP respondeu."""
    chrome_de_pe = bool(_get_abas_chrome())
    if chrome_de_pe:
        # Chrome de pé = as abas que faltam entram NELE, via CDP. Chamar o
        # chrome.exe aqui subia uma SEGUNDA instância, e as duas ficavam
        # escutando a 9222 em pilhas diferentes: a primeira em 127.0.0.1, a
        # segunda em ::1 (medido em 14/08). Com `localhost` resolvendo para as
        # duas, qual Chrome respondia virava sorteio — o agente conferia as abas
        # num e extraía do outro, e falhava com "Nenhuma aba encontrada".
        # Foi o que queimou 15 CNJs na rodada de 14/08.
        print("Chrome já aberto — conferindo quais abas faltam:")
        for url in _urls_que_faltam(urls_por_sistema):
            if not abrir_aba_cdp(url):
                print(f"  Aviso: não consegui abrir — abra manualmente: {url}")
    else:
        print(f"Abrindo Chrome com {len(urls_por_sistema)} aba(s):")
        for sistema, url in urls_por_sistema.items():
            print(f"  {sistema}: {url}")
        subprocess.Popen([
            CHROME_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={CHROME_PROFILE}",
            *urls_por_sistema.values(),
        ])

    if not await _aguardar_cdp_pronto():
        print("Não foi possível conectar ao Chrome (CDP). Verifique se ele abriu.")
        return False
    return True


async def main() -> dict:
    """Abre, observa o login e extrai — o comportamento do comando `iniciar`."""
    urls_por_sistema = _coletar_urls_pendentes()
    if not urls_por_sistema:
        print("Nenhum processo pendente. Nada a fazer.")
        return {"total": 0, "processados": 0, "erros": 0}

    if not await _abrir_abas(urls_por_sistema):
        return {"total": 0, "processados": 0, "erros": 0, "cdp_falhou": True}

    # MODO_AUTO: observa o login e dispara a extração sozinho.
    return await modo_supabase(MODO_AUTO)


if __name__ == "__main__":
    if "--abrir" in sys.argv:
        asyncio.run(abrir_sistemas())
    elif "--extrair" in sys.argv:
        asyncio.run(extrair())
    else:
        asyncio.run(main())
