"""
observabilidade.py — o rastro do que a extração fez, etapa por etapa.

Existe por causa de 08/09/2026. Naquele dia o eProc TJMG devolveu 35 processos
com "o sistema não estava aberto no Chrome", e responder *por quê* custou uma
investigação inteira — cruzando horários de `comandos` com `processos`,
deduzindo por diferença de timestamps, e terminando numa conclusão provável em
vez de certa. O sistema registrava o que sobrou no fim, nunca o que ele fez no
caminho.

Cada evento vira uma linha em dois lugares:

- `eventos_extracao` no Supabase — a que importa. O Leonardo investiga da
  máquina dele, e a extração roda na do Henrique; sem uma saída remota, o
  diagnóstico depende de alguém estar sentado na frente da máquina certa na
  hora certa.
- a janela do agente — de graça, porque `agente.py` já espelha tudo que é
  impresso para `logs/agente-AAAA-MM-DD.log` (ver `_Tee`). Serve de rede
  quando o Supabase está fora.

**Registrar nunca pode derrubar uma rodada.** Testemunha não vira juiz: toda
gravação é embrulhada, e falha vira aviso impresso, não exceção. Uma extração
de 40 minutos não pode morrer porque o disco encheu.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# O comando (rodada) ao qual os próximos eventos pertencem. É global de módulo
# porque a rodada é sequencial e de um agente só — passar isso por parâmetro
# atravessaria dez assinaturas de função para carregar um dado que nunca muda
# no meio do caminho. `agente.py` define no início e limpa no fim.
_comando_id: str | None = None

# Falhou a gravação remota? Para de tentar até o fim da rodada. Sem isto, uma
# rede caída faz cada um dos ~200 eventos esperar o timeout do Supabase, e o
# registro — que existe para ajudar — vira o motivo de a rodada demorar o dobro.
_remoto_desligado = False

# Quanto de um campo de texto vai para o banco. Lista de abas pode ser longa;
# o valor está no primeiro trecho, não na milésima URL.
LIMITE_DETALHE = 2000


def iniciar_rodada(comando_id: str | None) -> None:
    """Amarra os próximos eventos a um comando do painel."""
    global _comando_id, _remoto_desligado
    _comando_id = comando_id
    _remoto_desligado = False


def encerrar_rodada() -> None:
    global _comando_id
    _comando_id = None


def _linha_console(etapa: str, ok: bool, sistema: str | None,
                   numero_cnj: str | None, detalhe: str | None) -> str:
    """
    A linha que aparece na janela do agente. Função pura — ver test_observabilidade.py.

    Formato fixo e curto de propósito: quem lê é o Henrique, no meio da saída
    normal da extração.

    **Marca em ASCII puro, e isso não é detalhe.** A primeira versão usava
    simbolinhos bonitos; no console do Windows (cp1252) o de falha estourava no
    `print`, que está embrulhado em try/except — então a linha de FALHA, e só
    ela, sumia calada. Registro que perde justamente o evento que interessa é
    pior que registro nenhum: dá confiança falsa. Medido em 08/09, no primeiro
    teste de fumaça deste módulo.
    """
    marca = "[ok]" if ok else "[FALHA]"
    partes = [f"{marca} {etapa}"]
    if sistema:
        partes.append(f"[{sistema}]")
    if numero_cnj:
        partes.append(numero_cnj)
    if detalhe:
        partes.append(f"— {detalhe}")
    return " ".join(partes)


def registrar(
    etapa: str,
    *,
    ok: bool = True,
    sistema: str | None = None,
    numero_cnj: str | None = None,
    detalhe: str | None = None,
    dados: dict[str, Any] | None = None,
) -> None:
    """
    Grava um evento. Nunca levanta exceção.

    `etapa` é o nome curto e estável do passo (`abrir.aba_confirmada`,
    `cnj.ambiente`). Estável importa: é por ele que se filtra no SQL depois, e
    renomear etapa quebra consulta salva.

    `detalhe` é texto de gente — vai ser lido por quem está investigando.
    `dados` são os números soltos (quantas abas, quantos ms) que não cabem numa
    frase mas respondem perguntas depois.
    """
    texto = (detalhe or "")[:LIMITE_DETALHE] or None

    linha = _linha_console(etapa, ok, sistema, numero_cnj, texto)
    try:
        print(linha)
    except Exception:  # noqa: BLE001 — console quebrado não pode parar a rodada
        # Última tentativa antes de desistir da linha: trocar o que o console
        # não aceita por "?" ainda entrega o evento legível. Perder a linha
        # inteira por causa de um acento seria o defeito que este módulo existe
        # para acabar.
        try:
            print(linha.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass

    _gravar_remoto(etapa, ok, sistema, numero_cnj, texto, dados)


def _gravar_remoto(etapa: str, ok: bool, sistema: str | None,
                   numero_cnj: str | None, detalhe: str | None,
                   dados: dict[str, Any] | None) -> None:
    global _remoto_desligado
    if _remoto_desligado:
        return
    try:
        from supabase_writer import _get_client, _carregar_env

        _carregar_env()
        _get_client().table("eventos_extracao").insert({
            "momento": datetime.now(timezone.utc).isoformat(),
            "comando_id": _comando_id,
            "etapa": etapa,
            "sistema": sistema,
            "numero_cnj": numero_cnj,
            "ok": ok,
            "detalhe": detalhe,
            # json.loads(json.dumps(...)) troca o que não é serializável por
            # texto: um `dados` com objeto estranho dentro derrubaria a
            # gravação inteira, e o evento vale mais que o campo perfeito.
            "dados": json.loads(json.dumps(dados, default=str)) if dados else None,
        }).execute()
    except Exception as e:  # noqa: BLE001 — ver o comentário do topo do arquivo
        _remoto_desligado = True
        try:
            print(f"  (registro remoto desligado nesta rodada: {e})")
        except Exception:
            pass


def resumir_urls(abas: list[dict], limite: int = 12) -> str:
    """
    As URLs abertas, em uma linha. Função pura — ver test_observabilidade.py.

    É o dado que faltou em 08/09: quando um sistema falha com "Nenhuma aba", a
    pergunta seguinte é sempre "então o que ESTAVA aberto?". Sem esta lista, a
    resposta é dedução; com ela, é leitura.
    """
    if not abas:
        return "nenhuma aba aberta"
    urls = [str(a.get("url") or "?") for a in abas if a.get("type") == "page"]
    if not urls:
        return f"{len(abas)} aba(s), nenhuma do tipo página"
    mostradas = urls[:limite]
    sobra = len(urls) - len(mostradas)
    texto = " | ".join(mostradas)
    return f"{texto} (+{sobra})" if sobra > 0 else texto
