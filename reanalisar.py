"""
reanalisar.py — Reroda a análise de processos que ficaram 'processado' sem rascunho.

Usa os documentos que JÁ estão no Supabase: não abre navegador, não precisa de
login e não reextrai nada. Existe porque devolver esses processos para 'pendente'
não resolve — a reextração seria incremental, não acharia documento novo e o
processo voltaria a 'processado' sem análise, no mesmo lugar de antes.

Uso:
  python reanalisar.py --listar            # quem está processado e sem rascunho
  python reanalisar.py --todos             # reanalisa todos eles
  python reanalisar.py <cnj> [<cnj> ...]   # reanalisa CNJs específicos
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from analyzer import analisar_processo, STATUS_SUGERIDOS
from supabase_writer import _get_client, _carregar_env, _upsert_rascunho

# processos.status_atual aceita os mesmos atos que o modelo pode sugerir, mais os
# três estados de ciclo de vida, que não vêm da IA. Escrever um valor de fora da
# lista derruba o update.
STATUS_ATUAL_ACEITOS = {"PENDENTE", "EM_ANDAMENTO", "ARQUIVADO", *STATUS_SUGERIDOS}


def listar_sem_rascunho(client) -> list[dict]:
    """Processos marcados 'processado' que não têm nenhum rascunho."""
    processos = (
        client.table("processos")
        .select("id, numero_cnj, sistema, total_documentos, lote_id")
        .eq("pje_status", "processado")
        .execute()
    ).data or []
    com_rascunho = {
        r["processo_id"]
        for r in ((client.table("rascunhos").select("processo_id").execute()).data or [])
    }
    return [p for p in processos if p["id"] not in com_rascunho]


def buscar_por_cnj(client, cnjs: list[str]) -> list[dict]:
    res = (
        client.table("processos")
        .select("id, numero_cnj, sistema, total_documentos, lote_id")
        .in_("numero_cnj", cnjs)
        .execute()
    )
    return res.data or []


def _documentos(client, processo_id: str) -> list[dict]:
    """Documentos na mesma ordem em que o extrator os entregou (mais recente primeiro)."""
    res = (
        client.table("documentos")
        .select("indice, numero_documento, titulo, data_documento, juntado_por, cargo, texto, erro")
        .eq("processo_id", processo_id)
        .order("indice", desc=True)
        .execute()
    )
    return res.data or []


def reanalisar_um(client, processo: dict) -> str:
    cnj = processo["numero_cnj"]
    documentos = _documentos(client, processo["id"])
    if not documentos:
        return "sem documentos no banco — precisa extrair de novo, não dá para reanalisar"

    # a timeline não é guardada no banco; o analyzer trabalha só com os documentos
    resultado = {
        "sistema":            processo.get("sistema") or "pje_tjmg",
        "numero_cnj":         cnj,
        "total_documentos":   len(documentos),
        "documentos":         documentos,
        "metadados_timeline": [],
    }

    analise = analisar_processo(cnj, resultado)
    if analise.get("erro"):
        return f"análise falhou: {analise['erro']}"

    _upsert_rascunho(client, processo["id"], analise)

    update: dict = {"motivo_ignorado": None}
    status = analise.get("status_sugerido")
    if status in STATUS_ATUAL_ACEITOS:
        update["status_atual"] = status
    if analise.get("proxima_acao"):
        update["proxima_acao"] = analise["proxima_acao"]
    client.table("processos").update(update).eq("id", processo["id"]).execute()

    prazo = analise.get("prazo_fatal_dias_uteis")
    prazo_str = f"{prazo} d.u." if prazo else "sem prazo"
    return f"OK — {status} | {analise.get('responsavel_sugerido')} | {prazo_str}"


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    _carregar_env()
    client = _get_client()

    if "--listar" in args:
        alvos = listar_sem_rascunho(client)
        if not alvos:
            print("Nenhum processo 'processado' sem rascunho.")
            return
        print(f"{len(alvos)} processo(s) 'processado' sem rascunho:")
        for p in alvos:
            print(f"  {p['numero_cnj']}  [pauta {p.get('lote_id')}]  "
                  f"{p.get('total_documentos')} doc(s)  sistema={p.get('sistema')}")
        return

    if "--todos" in args:
        alvos = listar_sem_rascunho(client)
    else:
        alvos = buscar_por_cnj(client, args)
        faltando = {c for c in args} - {p["numero_cnj"] for p in alvos}
        for cnj in sorted(faltando):
            print(f"  {cnj} — não encontrado em processos")

    if not alvos:
        print("Nada a reanalisar.")
        return

    print(f"Reanalisando {len(alvos)} processo(s) a partir dos documentos já salvos...\n")
    for i, processo in enumerate(alvos, 1):
        print(f"  [{i}/{len(alvos)}] {processo['numero_cnj']} — analisando...")
        try:
            print(f"  [{i}/{len(alvos)}] {reanalisar_um(client, processo)}")
        except Exception as e:  # noqa: BLE001 — um processo ruim não pode parar a lista
            print(f"  [{i}/{len(alvos)}] ERRO: {e}")


if __name__ == "__main__":
    main()
