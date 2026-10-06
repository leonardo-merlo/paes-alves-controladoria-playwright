"""
chrome_saude.py — o estado do Chrome do robô, medido em vez de deduzido.

Existe por causa de 02/10 e 05/10/2026, na máquina do Henrique. Nas duas rodadas
o Chrome trocou o id da aba de trabalho (`abas.poupada`) e o processo seguinte
travou em `connect_over_cdp` por 180s com o Chrome respondendo ao ping simples.
Duas falhas assim abortam a rodada e devolvem a fila inteira para 'pendente'.

A conexão do Playwright precisa falar com cada aba antes de começar, então basta
uma aba muda para travar tudo. Ninguém sabia qual. Este módulo pergunta a cada
aba, uma por uma e com prazo curto, se ela responde — e se o Chrome a descartou
para economizar memória (`document.wasDiscarded`), que é a hipótese principal
para a troca de id.

Só observa: não fecha, não recarrega e não muda nada no Chrome.
"""

import asyncio
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sistema_auth import CDP_URL, CHROME_PROFILE

PRAZO_SONDAGEM_S = 5.0

# Texto que cada aba roda para se descrever. Sem efeito colateral na página.
_EXPRESSAO_SONDAGEM = (
    "JSON.stringify({descartada: document.wasDiscarded === true, "
    "visibilidade: document.visibilityState})"
)


# ── configuração ─────────────────────────────────────────────────

def extrair_desempenho(local_state: dict, preferencias: dict) -> dict:
    """
    O bloco `performance_tuning` dos dois arquivos do perfil. Função pura — ver
    test_chrome_saude.py.

    Os dois arquivos, porque o nome e o lugar da chave da economia de memória
    já mudaram entre versões do Chrome. Gravar o bloco cru deixa a leitura para
    quem consulta, em vez de apostar num nome de chave.
    """
    return {
        "local_state": (local_state or {}).get("performance_tuning") or {},
        "preferencias": (preferencias or {}).get("performance_tuning") or {},
    }


def descrever_config(desempenho: dict, versao: str | None) -> str:
    """
    Uma linha para o log. Função pura — ver test_chrome_saude.py.

    Bloco vazio quer dizer que ninguém mexeu na configuração, e não que a
    economia de memória está desligada: o padrão depende da versão do Chrome.
    Por isso a frase não afirma o estado; quem afirma é a sondagem das abas.
    """
    prefixo = f"Chrome {versao}" if versao else "Chrome (versão desconhecida)"
    chaves = sorted(set(desempenho.get("local_state") or {})
                    | set(desempenho.get("preferencias") or {}))
    if not chaves:
        return f"{prefixo}; desempenho no padrão do Chrome (nada alterado no perfil)"
    return f"{prefixo}; desempenho alterado no perfil: {', '.join(chaves)}"


def _ler_json(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return {}


def versao_do_chrome() -> str | None:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2) as resp:
            return json.loads(resp.read()).get("Browser")
    except Exception:
        return None


def ler_config_chrome(perfil: str = CHROME_PROFILE) -> dict:
    """Lê a configuração de desempenho do perfil do robô. Nunca levanta exceção."""
    base = Path(perfil)
    return extrair_desempenho(
        _ler_json(base / "Local State"),
        _ler_json(base / "Default" / "Preferences"),
    )


# ── retrato das abas ─────────────────────────────────────────────

def _host(url: str | None) -> str:
    try:
        return urlparse(url or "").hostname or (url or "?")[:40]
    except Exception:
        return "?"


def retrato_abas(abas: list[dict]) -> list[dict]:
    """
    As abas em forma curta, para caber no `dados` de cada processo. Função pura
    — ver test_chrome_saude.py.

    Em 05/10 a aba da seguradora apareceu em algum ponto de uma hora sem
    registro nenhum, porque as abas só eram anotadas quando algo falhava. Com
    um retrato por processo, o minuto em que uma aba surge ou troca de id fica
    no histórico.
    """
    return [
        {"id": (a.get("id") or "")[:8], "tipo": a.get("type"), "host": _host(a.get("url"))}
        for a in abas
    ]


# ── sondagem ─────────────────────────────────────────────────────

async def _perguntar(ws_url: str, prazo: float) -> dict:
    import websockets

    opcoes: dict[str, Any] = {"max_size": None, "open_timeout": prazo}
    # a partir da 15 o websockets segue o proxy do Windows por conta própria;
    # 127.0.0.1 nunca deve passar por proxy. Antes da 15 o parâmetro não existe.
    if int(websockets.__version__.split(".")[0]) >= 15:
        opcoes["proxy"] = None

    async def _conversa() -> dict:
        async with websockets.connect(ws_url, **opcoes) as ws:
            await ws.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": _EXPRESSAO_SONDAGEM, "returnByValue": True},
            }))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 1:
                    valor = (msg.get("result") or {}).get("result", {}).get("value")
                    return json.loads(valor) if isinstance(valor, str) else {}

    return await asyncio.wait_for(_conversa(), timeout=prazo)


async def sondar_abas(abas: list[dict], prazo: float = PRAZO_SONDAGEM_S) -> list[dict]:
    """
    Pergunta a cada página se ela responde, uma por uma, com prazo curto.
    Nunca levanta exceção.

    Uma por uma de propósito: a pergunta é justamente qual delas não responde,
    e em paralelo uma aba muda atrasaria a resposta das outras.
    """
    try:
        import websockets  # noqa: F401 — vem com o supabase; sem ele, não dá para perguntar
        sem_biblioteca = False
    except ImportError:
        sem_biblioteca = True
    resultados: list[dict] = []
    for aba in abas:
        if aba.get("type") != "page":
            continue
        item: dict[str, Any] = {"id": (aba.get("id") or "")[:8], "host": _host(aba.get("url"))}
        ws_url = aba.get("webSocketDebuggerUrl")
        if sem_biblioteca:
            item["responde"] = None
            item["obs"] = "biblioteca websockets ausente — não perguntado"
            resultados.append(item)
            continue
        if not ws_url:
            # sem endereço quando outra ferramenta de depuração já está presa nela
            item["responde"] = None
            item["obs"] = "sem endereço de conexão"
            resultados.append(item)
            continue
        inicio = time.monotonic()
        try:
            estado = await _perguntar(ws_url, prazo)
            item["responde"] = True
            item["descartada"] = bool(estado.get("descartada"))
            item["visibilidade"] = estado.get("visibilidade")
        except asyncio.TimeoutError:
            item["responde"] = False
            item["obs"] = f"sem resposta em {prazo:.0f}s"
        except Exception as e:
            item["responde"] = False
            item["obs"] = f"{type(e).__name__}: {str(e)[:120]}"
        item["ms"] = int((time.monotonic() - inicio) * 1000)
        resultados.append(item)
    return resultados


def resumir_sondagem(resultados: list[dict]) -> tuple[bool, str]:
    """
    (todas responderam e nenhuma foi descartada, frase). Função pura — ver
    test_chrome_saude.py.

    As abas problemáticas vêm primeiro: numa linha só, é o que importa ler.
    """
    if not resultados:
        return True, "nenhuma página para sondar"
    mudas = [r for r in resultados if r.get("responde") is False]
    descartadas = [r for r in resultados if r.get("descartada")]
    partes = []
    if mudas:
        partes.append("NÃO RESPONDEM: " + ", ".join(
            f"{r['host']} ({r.get('obs', '?')})" for r in mudas))
    if descartadas:
        partes.append("DESCARTADAS pelo Chrome: " + ", ".join(r["host"] for r in descartadas))
    if not partes:
        return True, f"{len(resultados)} página(s), todas responderam, nenhuma descartada"
    return False, f"{len(resultados)} página(s); " + "; ".join(partes)
