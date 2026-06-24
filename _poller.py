"""Poller temporário: acompanha o progresso da extração via Supabase.
Emite uma linha sempre que o estado muda; encerra quando o comando termina."""
import sys
import time

from supabase_writer import _get_client, _carregar_env

_carregar_env()
client = _get_client()

TERMINAIS = {"concluido", "erro"}
ultimo = None
estavel_terminal = 0

while True:
    procs = client.table("processos").select("pje_status").execute().data or []
    cont = {}
    for p in procs:
        s = p.get("pje_status", "?")
        cont[s] = cont.get(s, 0) + 1

    cmd = (
        client.table("comandos")
        .select("status, mensagem")
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
        .data
    )
    cmd_status = cmd[0]["status"] if cmd else "?"
    cmd_msg = (cmd[0].get("mensagem") or "")[:80] if cmd else ""

    assinatura = (tuple(sorted(cont.items())), cmd_status, cmd_msg)
    if assinatura != ultimo:
        ultimo = assinatura
        resumo = " | ".join(f"{k}={v}" for k, v in sorted(cont.items()))
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] comando={cmd_status} :: {resumo} :: {cmd_msg}", flush=True)

    if cmd_status in TERMINAIS:
        # confirma 2x para garantir que o estado assentou antes de sair
        estavel_terminal += 1
        if estavel_terminal >= 2:
            print(f"[{time.strftime('%H:%M:%S')}] FIM (comando={cmd_status})", flush=True)
            break
    else:
        estavel_terminal = 0

    time.sleep(10)
