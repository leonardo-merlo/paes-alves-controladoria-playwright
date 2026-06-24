"""
runner.py — Orquestra extrações agrupadas por sistema judicial.

Uso:
  python runner.py              # lê do Supabase (padrão)
  python runner.py --local      # usa inputs/<hoje>/cnj_list.txt
  python runner.py --local 2026-06-09
  python runner.py --todas      # todas as datas locais pendentes
"""

import asyncio
import sys
from collections import defaultdict
from datetime import date, timezone, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from analyzer import analisar_processo
from cnj_router import rotear_lista, CNJInfo
from extrator_dispatch import obter_extrator, esta_implementado, descricao_pendente
from sistema_auth import preparar_autenticacao, monitorar_logins_e_processar
from supabase_writer import salvar_no_supabase, _get_client, _carregar_env

INPUTS_DIR = Path("inputs")


# ── helpers locais ────────────────────────────────────────────────

def ler_cnjs_local(data_str: str) -> list[str]:
    arquivo = INPUTS_DIR / data_str / "cnj_list.txt"
    if not arquivo.exists():
        return []
    return [l.strip() for l in arquivo.read_text(encoding="utf-8-sig").splitlines()
            if l.strip() and not l.startswith("#")]


def datas_pendentes_local() -> list[str]:
    if not INPUTS_DIR.exists():
        return []
    return sorted(p.name for p in INPUTS_DIR.iterdir() if p.is_dir())


# ── Supabase inputs ───────────────────────────────────────────────

def ler_cnjs_supabase() -> list[dict]:
    _carregar_env()
    client = _get_client()
    res = (
        client.table("processos")
        .select("id, numero_cnj, fonte, lote_id, sistema, data_ultima_consulta")
        .in_("pje_status", ["pendente", "erro_browser", "captcha_bloqueado"])
        .eq("duplicata", False)
        .order("data_entrada")
        .execute()
    )
    return res.data or []


def marcar_supabase(ids: list[str], status: str, motivo: str | None = None) -> None:
    if not ids:
        return
    _carregar_env()
    client = _get_client()
    update: dict = {"pje_status": status}
    if motivo:
        update["motivo_ignorado"] = motivo
    client.table("processos").update(update).in_("id", ids).execute()


def inserir_processos_pendentes(
    entradas: list[dict],
    fonte: str = "manual",
    lote_id: str | None = None,
) -> None:
    """
    Insere CNJs pendentes diretamente em `processos`.
    Cada entrada pode ter: numero_cnj, vara, comarca, polo_ativo, polo_passivo, classe_processual.
    """
    _carregar_env()
    client = _get_client()

    res_existentes = client.table("processos").select("numero_cnj, pje_status").execute()
    existentes: dict[str, str] = {
        r["numero_cnj"]: r.get("pje_status", "") for r in (res_existentes.data or [])
    }

    vistos: set[str] = set()
    inseridos = 0
    ignorados = 0

    for entrada in entradas:
        cnj = entrada.get("numero_cnj", "").strip()
        if not cnj:
            continue

        status_atual = existentes.get(cnj)

        if status_atual == "pendente":
            print(f"  CNJ {cnj} já está pendente — ignorando reinserção")
            continue

        duplicata = cnj in vistos
        if not duplicata and status_atual in ("processado", "ignorado", "erro_browser", "captcha_bloqueado"):
            duplicata = True

        motivo = ("CNJ duplicado no mesmo lote" if cnj in vistos
                  else "CNJ já existe em processos" if duplicata else None)
        vistos.add(cnj)

        row: dict = {
            "numero_cnj": cnj,
            "fonte": fonte,
            "lote_id": lote_id,
            "duplicata": duplicata,
            "pje_status": "ignorado" if duplicata else "pendente",
            "data_entrada": datetime.now(timezone.utc).isoformat(),
        }
        if motivo:
            row["motivo_ignorado"] = motivo

        # campos de cabeçalho extraídos do e-mail — só preenche se presentes
        for campo in ("vara", "comarca", "polo_ativo", "polo_passivo", "classe_processual"):
            if entrada.get(campo):
                row[campo] = entrada[campo]

        if duplicata or status_atual is None:
            client.table("processos").upsert(row, on_conflict="numero_cnj").execute()
        else:
            # processo já existe mas não está pendente — apenas atualiza campos de entrada
            update = {k: v for k, v in row.items() if k != "numero_cnj"}
            client.table("processos").update(update).eq("numero_cnj", cnj).execute()

        if duplicata:
            ignorados += 1
        else:
            inseridos += 1

    print(f"  {inseridos} CNJ(s) pendentes, {ignorados} duplicata(s) ignorada(s)")


# ── processamento de um único CNJ ────────────────────────────────

async def processar_cnj(
    info: CNJInfo,
    data_str: str,
    prefixo: str,
    data_corte: str | None = None,
) -> dict | None:
    extrator = obter_extrator(info.sistema)
    if not extrator:
        return None  # não deve chegar aqui — filtrado antes

    MAX_TENTATIVAS = 3
    resultado = None

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        sufixo = f" (tentativa {tentativa}/{MAX_TENTATIVAS})" if tentativa > 1 else ""
        if data_corte:
            print(f"{prefixo} — extraindo (a partir de {data_corte[:10]}){sufixo}...")
        else:
            print(f"{prefixo} — extraindo (todos os documentos){sufixo}...")

        resultado = await extrator(info.numero_cnj, data_corte=data_corte)

        if resultado.get("erro"):
            erro_msg = resultado["erro"]
            _permanente = ("sessao_expirada", "Nenhuma aba", "Não foi possível conectar")
            eh_permanente = any(p in erro_msg for p in _permanente)
            if eh_permanente or tentativa == MAX_TENTATIVAS:
                print(f"{prefixo} — ERRO extração: {erro_msg}")
                return resultado
            print(f"{prefixo} — ERRO temporário ({erro_msg}) — retentando em 10s...")
            await asyncio.sleep(10)
            continue

        total = resultado.get("total_documentos", 0)
        print(f"{prefixo} — {total} doc(s)")

        if total > 0:
            break

        if tentativa < MAX_TENTATIVAS:
            print(f"{prefixo} — 0 documentos, retentando em 5s...")
            await asyncio.sleep(5)

    if resultado.get("total_documentos", 0) == 0:
        print(f"{prefixo} — ERRO: nenhum documento após {MAX_TENTATIVAS} tentativa(s)")
        return {"erro": "sem_documentos", "numero_cnj": info.numero_cnj}

    print(f"{prefixo} — analisando com Claude...")
    analise = analisar_processo(info.numero_cnj, resultado)

    if analise.get("erro"):
        # análise falhou mesmo após retries — não grava rascunho vazio nem marca
        # 'processado'; retorna erro para o CNJ cair em erro_browser e reprocessar.
        print(f"{prefixo} — ERRO análise: {analise['erro']} — marcando p/ reprocessar")
        return {"erro": "analise_falhou", "numero_cnj": info.numero_cnj}

    status    = analise.get("status_sugerido", "?")
    resp      = analise.get("responsavel_sugerido", "?")
    prazo     = analise.get("prazo_fatal_dias_uteis")
    risco     = analise.get("classificacao_risco", "?")
    prazo_str = f"{prazo} d.u." if prazo else "sem prazo"
    print(f"{prefixo} — {status} | {resp} | {prazo_str} | {risco}")

    n_docs = len(resultado.get("documentos") or [])
    print(f"{prefixo} — salvando {n_docs} doc(s) no Supabase...")
    sb = salvar_no_supabase(info.numero_cnj, resultado, analise)
    if sb.get("ok"):
        print(f"{prefixo} — salvo OK (id: {sb['processo_id'][:8]}...)")
    else:
        print(f"{prefixo} — ERRO Supabase: {sb.get('erro')}")
        print(sb.get("tb", "(sem traceback)"))
        return {"erro": "supabase_falhou", "numero_cnj": info.numero_cnj}

    return resultado


# ── orquestração por sistema ──────────────────────────────────────

async def processar_por_sistema(
    cnjs_roteados: list[CNJInfo],
    data_str: str,
    ids_map: dict[str, str] | None = None,
    corte_map: dict[str, str | None] | None = None,
    modo_auto: bool = False,
    progresso_cb=None,
) -> tuple[list[str], list[str]]:
    """
    Agrupa os CNJs por sistema, autentica uma vez, processa um sistema por vez.
    Retorna (ids_ok, ids_erro) para atualizar o Supabase.
    """

    # separar por sistema
    por_sistema: dict[str, list[CNJInfo]] = defaultdict(list)
    nao_impl: list[CNJInfo] = []
    com_erro: list[CNJInfo] = []

    for info in cnjs_roteados:
        if info.erro:
            com_erro.append(info)
        elif not esta_implementado(info.sistema):
            nao_impl.append(info)
        else:
            por_sistema[info.sistema].append(info)

    # avisar sistemas não implementados
    if nao_impl:
        print("Sistemas ainda não implementados (serão pulados):")
        by_sis: dict[str, int] = defaultdict(int)
        for info in nao_impl:
            by_sis[info.sistema] += 1
        for sis, qtd in by_sis.items():
            print(f"  {sis} ({descricao_pendente(sis)}) — {qtd} CNJ(s)")
        print()

    if com_erro:
        print(f"CNJs com formato inválido: {len(com_erro)}")
        for info in com_erro:
            print(f"  {info.numero_cnj} — {info.erro}")
        print()

    if not por_sistema:
        print("Nenhum CNJ para processar.")
        return [], []

    sistemas_necessarios = list(por_sistema.keys())
    ids_ok: list[str] = []
    ids_erro: list[str] = []
    total_global = sum(len(v) for v in por_sistema.values())
    processados_global = 0

    async def _processar_sistema(sistema: str) -> None:
        nonlocal processados_global
        infos = por_sistema[sistema]
        total = len(infos)
        print(f"{'='*50}")
        print(f"[{sistema}] {total} CNJ(s)\n")
        for i, info in enumerate(infos, 1):
            prefixo = f"  [{i}/{total}] {info.numero_cnj}"
            data_corte = corte_map.get(info.numero_cnj) if corte_map else None
            resultado = await processar_cnj(info, data_str, prefixo, data_corte=data_corte)
            cnj_id = ids_map.get(info.numero_cnj) if ids_map else None
            if resultado and not resultado.get("erro") and cnj_id:
                ids_ok.append(cnj_id)
            elif cnj_id:
                ids_erro.append(cnj_id)
            processados_global += 1
            if progresso_cb:
                progresso_cb(processados_global, total_global)
        print()

    if modo_auto:
        processados = await monitorar_logins_e_processar(sistemas_necessarios, _processar_sistema)
        nao_processados = [s for s in sistemas_necessarios if s not in processados]
        if ids_map and nao_processados:
            ids_timeout = [
                ids_map[info.numero_cnj]
                for s in nao_processados
                for info in por_sistema.get(s, [])
                if info.numero_cnj in ids_map
            ]
            marcar_supabase(ids_timeout, "erro_browser", "Sistema indisponível ou timeout de login")
    else:
        ok = await preparar_autenticacao(sistemas_necessarios, modo_auto=False)
        if not ok:
            return [], []
        for sistema in sistemas_necessarios:
            await _processar_sistema(sistema)

    # ids de CNJs não implementados → ignorado
    if ids_map:
        ids_nao_impl = [ids_map[i.numero_cnj] for i in nao_impl if i.numero_cnj in ids_map]
        marcar_supabase(ids_nao_impl, "ignorado", "Sistema não implementado")

    return ids_ok, ids_erro


# ── modos de execução ─────────────────────────────────────────────

async def modo_supabase(modo_auto: bool = False, progresso_cb=None) -> dict:
    """Processa os pendentes do Supabase. Retorna resumo {total, processados, erros}."""
    pendentes = ler_cnjs_supabase()
    if not pendentes:
        print("Nenhum CNJ pendente no Supabase.")
        return {"total": 0, "processados": 0, "erros": 0}

    numeros = [p["numero_cnj"] for p in pendentes]
    ids_map = {p["numero_cnj"]: p["id"] for p in pendentes}
    corte_map = {p["numero_cnj"]: p.get("data_ultima_consulta") for p in pendentes}
    hints = {p["numero_cnj"]: p.get("sistema") for p in pendentes}
    cnjs = rotear_lista(numeros, hints)
    data_str = str(date.today())

    print(f"Supabase: {len(cnjs)} CNJ(s) únicos pendentes")
    ids_ok, ids_erro = await processar_por_sistema(cnjs, data_str, ids_map, corte_map, modo_auto=modo_auto, progresso_cb=progresso_cb)
    print(f"ids_ok={ids_ok}")
    print(f"ids_erro={ids_erro}")
    marcar_supabase(ids_ok, "processado")
    marcar_supabase(ids_erro, "erro_browser", "Erro durante processamento")
    print(f"Concluído: {len(ids_ok)} processados, {len(ids_erro)} com erro")
    return {"total": len(cnjs), "processados": len(ids_ok), "erros": len(ids_erro)}


async def modo_local(data_str: str) -> None:
    linhas = ler_cnjs_local(data_str)
    if not linhas:
        print(f"Nenhum CNJ em inputs/{data_str}/cnj_list.txt")
        return
    cnjs = rotear_lista(linhas)
    print(f"Local [{data_str}]: {len(cnjs)} CNJ(s) únicos")
    await processar_por_sistema(cnjs, data_str)


async def main() -> None:
    args = sys.argv[1:]

    if "--todas" in args:
        for d in datas_pendentes_local():
            await modo_local(d)
    elif "--local" in args:
        args.remove("--local")
        await modo_local(args[0] if args else str(date.today()))
    else:
        await modo_supabase()


if __name__ == "__main__":
    asyncio.run(main())
