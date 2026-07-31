"""
agente.py — Agente local da controladoria.

Fica rodando na máquina do operador, consultando a tabela `comandos` no Supabase
a cada poucos segundos. Quando encontra um comando 'iniciar' pendente, executa o
fluxo de extração (iniciar.py) e grava o resultado de volta no Supabase.

Não abre portas nem recebe conexões: só consulta o Supabase de tempos em tempos.

Uso:
  python agente.py
"""

import asyncio
import time
import traceback
from datetime import datetime, timedelta, timezone

from iniciar import main as executar_extracao
from supabase_writer import _get_client, _carregar_env

INTERVALO_S = 3

# Uma rodada de extração leva 20-45min. Um comando 'em_andamento' mais antigo
# que isto é tratado como rodada abandonada (agente caiu no meio) e deixa de
# bloquear novas rodadas — senão a fila travaria pra sempre após um crash.
LIMITE_RODADA_ABANDONADA_MIN = 90


def proximo_pendente(comandos: list[dict]) -> dict | None:
    """Dentre os comandos recebidos, escolhe o mais antigo com status 'pendente'."""
    pendentes = [c for c in comandos if c.get("status") == "pendente"]
    if not pendentes:
        return None
    return sorted(pendentes, key=lambda c: c.get("criado_em", ""))[0]


def buscar_pendentes(client) -> list[dict]:
    res = (
        client.table("comandos")
        .select("id, acao, status, criado_em")
        .eq("status", "pendente")
        .order("criado_em")
        .execute()
    )
    return res.data or []


def marcar(client, comando_id: str, status: str, mensagem: str | None = None) -> None:
    update: dict = {
        "status": status,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }
    if mensagem is not None:
        update["mensagem"] = mensagem
    client.table("comandos").update(update).eq("id", comando_id).execute()


def ha_rodada_em_andamento(client) -> bool:
    """Camada (b) — exclusão mútua global: True se já existe uma extração em
    curso (outro agente rodando). Ignora rodadas abandonadas (ver constante)."""
    limite = (
        datetime.now(timezone.utc) - timedelta(minutes=LIMITE_RODADA_ABANDONADA_MIN)
    ).isoformat()
    res = (
        client.table("comandos")
        .select("id")
        .eq("status", "em_andamento")
        .gte("atualizado_em", limite)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def reivindicar(client, comando_id: str, mensagem: str) -> bool:
    """Camada (a) — claim atômico: marca 'em_andamento' SOMENTE se o comando
    ainda estiver 'pendente', numa única operação. Retorna True apenas se ESTE
    agente foi quem o pegou (se outro pegou antes, o update afeta 0 linhas)."""
    res = (
        client.table("comandos")
        .update({
            "status": "em_andamento",
            "mensagem": mensagem,
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", comando_id)
        .eq("status", "pendente")
        .execute()
    )
    return len(res.data or []) == 1


def processar_um(client) -> bool:
    """Pega e executa um comando pendente. Retorna True se executou algo."""
    # Camada (b): não inicia uma rodada se outra já estiver em andamento.
    if ha_rodada_em_andamento(client):
        return False

    comando = proximo_pendente(buscar_pendentes(client))
    if not comando:
        return False

    cid = comando["id"]
    # Camada (a): só segue se conseguir reivindicar o comando atomicamente.
    if not reivindicar(client, cid, "Abrindo navegador. Faça login nos sistemas."):
        return False

    print(f"Comando recebido: {comando.get('acao')} ({cid[:8]})")
    try:
        resumo = asyncio.run(executar_extracao()) or {}
        status, mensagem = _resumo_para_status(resumo)
        marcar(client, cid, status, mensagem)
        print(f"Comando {status}: {mensagem}")
    except Exception as e:  # noqa: BLE001 — agente não pode morrer por um comando
        marcar(client, cid, "erro", f"Erro: {e}")
        print(f"Erro ao executar comando: {e}")
        traceback.print_exc()
    return True


def _resumo_para_status(resumo: dict) -> tuple[str, str]:
    """Traduz o resumo da extração em (status, mensagem) honestos para o app."""
    total = resumo.get("total", 0)
    n_ok = resumo.get("processados", 0)
    n_err = resumo.get("erros", 0)
    n_rev = resumo.get("revisao_manual", 0)
    n_novo = resumo.get("nada_novo", 0)

    # processo salvo sem análise não conta como erro, mas não pode passar em
    # silêncio: ele aparece no painel como pronto e sem prazo nenhum.
    aviso = f" {n_rev} sem análise — revisar." if n_rev else ""
    # já estavam extraídos e não tinham documento novo: sucesso, mas não é
    # extração desta rodada — somar no total faria o painel inflar o número.
    novidade = f", {n_novo} sem novidade" if n_novo else ""

    if resumo.get("cdp_falhou"):
        return "erro", "Não foi possível abrir o navegador (CDP)."
    if total == 0:
        return "concluido", "Nenhum processo pendente."
    if n_ok == 0 and n_novo == 0:
        return "erro", f"Nada extraído ({n_err} com erro). Login não concluído? Verifique."
    if n_err > 0:
        return "concluido", f"{n_ok} processado(s){novidade}, {n_err} com erro.{aviso}"
    return "concluido", f"{n_ok} processado(s){novidade}.{aviso}"


def main_loop() -> None:
    _carregar_env()
    client = _get_client()
    print("Agente da controladoria iniciado. Aguardando comandos (Ctrl+C para sair)...")
    while True:
        try:
            processar_um(client)
        except Exception as e:  # noqa: BLE001 — loop nunca para por erro de rede
            print(f"Erro no loop do agente: {e}")
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main_loop()
