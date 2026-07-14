"""
supabase_writer.py — Persiste os resultados de extração e análise no Supabase.

Chamado pelo runner.py após extração + análise.
"""

import os
import ssl
from datetime import datetime, timezone
from pathlib import Path

# antivírus/proxy injeta certificado SSL não reconhecido pelo Python
# patch no httpx para sempre usar verify=False neste processo
import httpx
from postgrest import SyncPostgrestClient

# patch no SyncPostgrestClient para sempre usar verify=False
# necessário: antivírus/proxy injeta certificado SSL não reconhecido
_orig_postgrest_init = SyncPostgrestClient.__init__
def _patched_postgrest_init(self, *args, **kwargs):
    kwargs["verify"] = False  # forçar sempre — antivírus injeta cert inválido
    kwargs.pop("http_client", None)  # remover http_client se presente, verify toma prioridade
    _orig_postgrest_init(self, *args, **kwargs)
SyncPostgrestClient.__init__ = _patched_postgrest_init

from supabase import create_client, Client


def _build_responsavel_map(client: Client) -> dict[str, str]:
    """Busca usuários ativos e retorna {primeiro_nome_lower: uuid}."""
    res = client.table("usuarios").select("id, nome").eq("ativo", True).execute()
    mapa: dict[str, str] = {}
    for u in (res.data or []):
        primeiro_nome = u["nome"].split()[0].lower()
        # remove acentos simples para matching mais robusto (julia / júlia)
        normalizado = primeiro_nome.replace("ú", "u").replace("á", "a").replace("ã", "a").replace("é", "e").replace("ê", "e").replace("ó", "o").replace("ç", "c")
        mapa[normalizado] = u["id"]
        mapa[primeiro_nome] = u["id"]  # também com acento, por segurança
    return mapa


def _carregar_env() -> None:
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()


def _get_client() -> Client:
    _carregar_env()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")  # service_role bypassa RLS — correto para scripts server-side
    if not url or not key:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_KEY não encontrados no .env")
    return create_client(url, key)


def get_supabase() -> Client:
    return _get_client()


def get_responsaveis() -> list[dict]:
    """Retorna lista de usuários ativos: [{id, nome, primeiro_nome}]."""
    client = _get_client()
    res = client.table("usuarios").select("id, nome, papel").eq("ativo", True).execute()
    resultado = []
    for u in (res.data or []):
        primeiro = u["nome"].split()[0]
        resultado.append({"id": u["id"], "nome": u["nome"], "primeiro_nome": primeiro, "papel": u["papel"]})
    return resultado


def _upsert_processo(client: Client, numero_cnj: str, resultado: dict, analise: dict) -> str:
    """
    Insere ou atualiza o processo no Supabase.
    Retorna o UUID do processo.
    """
    responsavel_nome = analise.get("responsavel_sugerido", "")
    responsavel_map = _build_responsavel_map(client)
    responsavel_id = responsavel_map.get(responsavel_nome.lower())

    data = {
        "numero_cnj":          numero_cnj,
        "sistema":             resultado.get("sistema", "pje_tjmg"),
        "status_atual":        analise.get("status_sugerido"),
        "total_documentos":    resultado.get("total_documentos"),
        "proxima_acao":        analise.get("proxima_acao"),
        "data_ultima_consulta": datetime.now(timezone.utc).isoformat(),
        "responsavel_id":      responsavel_id,
        "pje_status":          "processado",
    }
    # remover nulos para não sobrescrever dados existentes com null
    data = {k: v for k, v in data.items() if v is not None}

    res = client.table("processos").upsert(data, on_conflict="numero_cnj").execute()
    return res.data[0]["id"]


def _clean_text(val: str | None) -> str | None:
    """Remove null bytes que o PostgreSQL não aceita em colunas text."""
    if val is None:
        return None
    return val.replace("\x00", "")


def _upsert_documentos(client: Client, processo_id: str, documentos: list[dict], incremental: bool = False) -> None:
    """
    Insere ou atualiza os documentos extraídos no Supabase.
    """
    if not documentos:
        return

    offset = 0
    if incremental:
        res = (
            client.table("documentos")
            .select("indice")
            .eq("processo_id", processo_id)
            .order("indice", desc=True)
            .limit(1)
            .execute()
        )
        offset = res.data[0]["indice"] if res.data else 0

    rows = []
    for doc in documentos:
        rows.append({
            "processo_id":      processo_id,
            "indice":           doc.get("indice") + offset,
            "numero_documento": _clean_text(doc.get("numero_documento")),
            "url_iframe":       _clean_text(doc.get("url_iframe")),
            "texto":            _clean_text((doc.get("texto") or ""))[:50000],
            "erro":             _clean_text(doc.get("erro")),
            "titulo":           _clean_text(doc.get("titulo")),
            "juntado_por":      _clean_text(doc.get("juntado_por")),
            "cargo":            _clean_text(doc.get("cargo")),
            "data_documento":   _clean_text(doc.get("data_documento")),
            "data_extracao":    datetime.now(timezone.utc).isoformat(),
        })

    # upsert em lotes de 50 para evitar payload muito grande
    for i in range(0, len(rows), 50):
        client.table("documentos").upsert(
            rows[i:i+50],
            on_conflict="processo_id,indice",
        ).execute()


def _upsert_rascunho(client: Client, processo_id: str, analise: dict) -> None:
    """
    Insere ou atualiza o rascunho de análise no Supabase.
    """
    responsavel_nome = analise.get("responsavel_sugerido", "")
    responsavel_map = _build_responsavel_map(client)
    responsavel_id = responsavel_map.get(responsavel_nome.lower())

    data = {
        "processo_id":                processo_id,
        "status_sugerido":            analise.get("status_sugerido"),
        "responsavel_sugerido":       responsavel_nome,        # texto — usado pelo app para exibição
        "responsavel_sugerido_id":    responsavel_id,           # UUID — usado na aprovação
        "proxima_acao":               analise.get("proxima_acao"),
        "cenario_prazo":              analise.get("cenario_prazo"),
        "prazo_fatal_dias_uteis":     analise.get("prazo_fatal_dias_uteis"),
        "prazo_interno_dias_uteis":   analise.get("prazo_interno_dias_uteis"),
        "justificativa":              analise.get("justificativa"),
        "alerta":                     analise.get("alerta"),
        "classificacao_risco":        analise.get("classificacao_risco"),
        "modelo_ia":                  analise.get("modelo"),
        "documentos_analisados":      analise.get("total_documentos_analisados"),
        "documentos_enviados_modelo": analise.get("documentos_enviados_ao_modelo"),
        "data_extracao":              datetime.now(timezone.utc).isoformat(),
        "status":                     "pendente",
    }
    data = {k: v for k, v in data.items() if v is not None}

    # verificar se já existe rascunho pendente para esse processo
    existente = (
        client.table("rascunhos")
        .select("id")
        .eq("processo_id", processo_id)
        .eq("status", "pendente")
        .execute()
    )

    if existente.data:
        # atualizar o rascunho pendente existente
        client.table("rascunhos").update(data).eq("id", existente.data[0]["id"]).execute()
    else:
        # criar novo rascunho
        client.table("rascunhos").insert(data).execute()


def salvar_no_supabase(
    numero_cnj: str,
    resultado_extracao: dict,
    analise: dict,
) -> dict:
    """
    Ponto de entrada principal. Persiste tudo no Supabase.
    Retorna dict com status e processo_id.
    """
    try:
        client = _get_client()

        processo_id = _upsert_processo(client, numero_cnj, resultado_extracao, analise)
        _upsert_documentos(client, processo_id, resultado_extracao.get("documentos", []), incremental=resultado_extracao.get("incremental", False))
        if analise:
            _upsert_rascunho(client, processo_id, analise)

        return {"ok": True, "processo_id": processo_id}

    except Exception as e:
        import traceback
        return {"ok": False, "erro": str(e), "tb": traceback.format_exc()}
