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
from datetime import datetime, timezone

from iniciar import main as executar_extracao
from supabase_writer import _get_client, _carregar_env

INTERVALO_S = 3


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


def processar_um(client) -> bool:
    """Pega e executa um comando pendente. Retorna True se executou algo."""
    comando = proximo_pendente(buscar_pendentes(client))
    if not comando:
        return False

    cid = comando["id"]
    print(f"Comando recebido: {comando.get('acao')} ({cid[:8]})")
    marcar(client, cid, "em_andamento", "Abrindo navegador. Faça login nos sistemas.")
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

    if resumo.get("cdp_falhou"):
        return "erro", "Não foi possível abrir o navegador (CDP)."
    if total == 0:
        return "concluido", "Nenhum processo pendente."
    if n_ok == 0:
        return "erro", f"Nada extraído ({n_err} com erro). Login não concluído? Verifique."
    if n_err > 0:
        return "concluido", f"{n_ok} processado(s), {n_err} com erro."
    return "concluido", f"{n_ok} processado(s)."


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
