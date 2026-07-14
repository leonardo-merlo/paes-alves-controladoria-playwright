"""
analyzer.py — Analisa processos extraídos usando Claude API e gera rascunhos jurídicos.

Chamado pelo runner.py após a extração. Não rodar diretamente.
"""

import json
import os
import time
from datetime import date
from pathlib import Path

import httpx
import anthropic
from dotenv import load_dotenv
from supabase_writer import get_responsaveis

# carregar .env manualmente — evita problemas de encoding com python-dotenv
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip()

CPC_DIR = Path("cpc")
MODEL = "claude-haiku-4-5-20251001"
MAX_DOCS_PARA_ANALISE = 7  # documentos mais recentes enviados ao modelo (texto completo)

def _carregar_arquivo_cpc(nome: str) -> str:
    path = CPC_DIR / nome
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[{nome} não encontrado]"

def _build_system_msg() -> str:
    referencia = _carregar_arquivo_cpc("cpc_referencia_final.md")
    indice = _carregar_arquivo_cpc("00_indice.md")
    print(f"[CPC] referencia_final: {len(referencia)} chars | indice: {len(indice)} chars")
    return f"""Você é um assistente jurídico especializado em CPC 2015. Sua única função é analisar processos e retornar JSON estruturado. NUNCA escreva texto fora do JSON. NUNCA explique seu raciocínio antes do JSON. Sua resposta deve começar com {{ e terminar com }}.

REGRAS DO ESCRITÓRIO (PRIORIDADE MÁXIMA — prevalecem sobre interpretação genérica da lei):
{referencia}
FIM DAS REGRAS DO ESCRITÓRIO.

ÍNDICE DO CPC — USE PARA IDENTIFICAR O ARQUIVO DE ORIGEM AO CITAR ARTIGOS:
{indice}
FIM DO ÍNDICE.

PROTOCOLO DE ANÁLISE:
0. IDENTIFIQUE PRIMEIRO QUAL POLO O ESCRITÓRIO REPRESENTA. Procure nos autos os advogados
   do escritório (os nomes constam na lista de RESPONSÁVEIS DISPONÍVEIS e suas variações —
   ex.: "Paes Alves Pequeno") e determine se eles atuam no POLO ATIVO (autor) ou PASSIVO
   (réu). Na quase totalidade dos casos somos o AUTOR, mas confirme sempre.
1. Leia o despacho/intimação/documento mais recente e identifique o ato processual.
2. DETERMINE A QUEM O COMANDO/PRAZO É DIRIGIDO. Um prazo dirigido à PARTE CONTRÁRIA
   (ex.: "RÉU - Banco X - Prazo: 15 dias" para contestar) NÃO é obrigação nossa — nesse
   caso a nossa próxima ação costuma ser AGUARDAR (ou manifestar, quando cabível). Só
   classifique como CONTESTACAO se a contestação for OBRIGAÇÃO DO NOSSO POLO.
3. LEIA AS DESCRIÇÕES DOS EVENTOS, não só os documentos. Datas de audiência, prazos e a
   parte destinatária frequentemente estão só na descrição do evento (ex.: "Audiência de
   conciliação designada - art. 334 CPC - ... - 22/09/2026 16:00"). Siga as referências
   entre eventos (ex.: "Refer. ao Evento 7") para encontrar a informação que falta.
4. Verifique o prazo nas REGRAS DO ESCRITÓRIO acima.
5. Ao citar artigos na justificativa, sempre indique o arquivo de origem conforme o índice.
   Exemplo: "prazo de 15 dias úteis (Art. 335 — 02_PROCESSO_CONHECIMENTO)"
6. Se o prazo não estiver explícito nas regras do escritório, use o índice para identificar a fase e citar o arquivo correto."""

PROMPT_USER = """Processo: {numero_cnj} | Sistema: {sistema} | Hoje: {data_hoje}

RESPONSÁVEIS DISPONÍVEIS (advogados/equipe do NOSSO escritório):
{responsaveis_lista}

LINHA DO TEMPO DE EVENTOS (mais recente primeiro — descrições podem conter datas de audiência, prazos e a parte destinatária):
{eventos_formatados}

DOCUMENTOS (mais recente primeiro):
{documentos_formatados}

Retorne APENAS este JSON (sem texto antes ou depois):
{{
  "nosso_polo": "ATIVO|PASSIVO",
  "status_sugerido": "CONTESTACAO|SENTENCA_ACORDO|EXECUCAO|AGUARDAR|MANIFESTAR",
  "responsavel_sugerido": "{responsaveis_opcoes}",
  "proxima_acao": "PROTOCOLAR X até DD/MM/AAAA (prazo interno: DD/MM/AAAA) OU AGUARDAR — motivo",
  "cenario_prazo": "EXPLICITO|VIA_ARTIGO|INFERIDO",
  "prazo_fatal_dias_uteis": 15,
  "prazo_interno_dias_uteis": 12,
  "justificativa": "5-7 frases descrevendo: (1) que polo representamos e como identificou, (2) o que aconteceu no processo até agora, (3) qual foi o evento mais recente e o que ele significa, (4) a quem o último comando/prazo é dirigido e se é obrigação NOSSA, (5) qual é a próxima obrigação processual e por quê, (6) qual artigo do CPC fundamenta o prazo e em qual arquivo (ex: Art. 335 — 02_PROCESSO_CONHECIMENTO)",
  "alerta": null,
  "classificacao_risco": "BAIXO|MEDIO|ALTO|CRITICO"
}}

Regras de status_sugerido:
- CONTESTACAO / SENTENCA_ACORDO / EXECUCAO: quando há ato processual a protocolar pelo NOSSO polo.
- AGUARDAR: quando NÃO há ato a protocolar agora (o prazo corrente é da parte contrária, ou aguarda-se audiência/decisão). Nesse caso proxima_acao começa com "AGUARDAR — " e cita o próximo marco/data. NÃO invente prazo nosso que não existe; deixe prazo_fatal_dias_uteis null.
- MANIFESTAR: quando cabe uma manifestação nossa sem ser contestação/réplica (ex.: manifestar sobre conciliação, sobre documento juntado, ciência com prazo).

Regras de responsável: use exatamente o primeiro nome como listado acima. Regra geral: gestor → CONTESTACAO, advogados → SENTENCA_ACORDO ou EXECUCAO conforme o caso. prazo_interno = fatal - 3. alerta obrigatório quando cenario_prazo = INFERIDO."""


def _formatar_eventos(metadados_timeline: list[dict]) -> str:
    """
    Formata a linha do tempo de eventos para o prompt. Tolerante aos dois formatos:
    eProc (campo 'descricao') e PJE (lista 'movimentos').
    """
    if not metadados_timeline:
        return "[sem eventos capturados]"
    linhas = []
    for ev in metadados_timeline:
        num = ev.get("num") or ""
        data = ev.get("data") or ""
        descricao = ev.get("descricao")
        if not descricao:
            movs = ev.get("movimentos") or []
            descricao = " | ".join(m for m in movs if m)
        descricao = (descricao or "").strip()
        if not descricao:
            continue
        ref = ev.get("referencia") or []
        ref_txt = f" [refer. eventos: {', '.join(ref)}]" if ref else ""
        prefixo = f"Evento {num}".strip() if num else "Evento"
        linhas.append(f"{prefixo} | {data} | {descricao}{ref_txt}")
    return "\n".join(linhas) if linhas else "[sem eventos capturados]"


def _formatar_documentos(documentos: list[dict]) -> str:
    recentes = documentos[:MAX_DOCS_PARA_ANALISE]
    linhas = []
    for doc in recentes:
        texto = (doc.get("texto") or "").strip()
        if not texto:
            texto = "[INACESSÍVEL: sem texto extraído]"
        linhas.append(
            f"{doc['indice']} | {doc['numero_documento']} | {texto}"
        )
    return "\n\n".join(linhas)


def analisar_processo(numero_cnj: str, resultado_extracao: dict) -> dict:
    """Recebe o resultado da extração e retorna o JSON de análise do Claude."""

    documentos = resultado_extracao.get("documentos", [])
    if not documentos:
        return {"erro": "sem_documentos", "numero_cnj": numero_cnj}

    docs_formatados = _formatar_documentos(documentos)
    eventos_formatados = _formatar_eventos(resultado_extracao.get("metadados_timeline", []))
    sistema = resultado_extracao.get("sistema", "pje_tjmg")

    try:
        usuarios = get_responsaveis()
    except Exception:
        usuarios = []

    if usuarios:
        responsaveis_lista = "\n".join(
            f"- {u['primeiro_nome']} ({u['nome']}) — {u['papel']}" for u in usuarios
        )
        responsaveis_opcoes = "|".join(u["primeiro_nome"] for u in usuarios)
    else:
        responsaveis_lista = "- (não foi possível carregar usuários)"
        responsaveis_opcoes = "responsavel"

    prompt = PROMPT_USER.format(
        numero_cnj=numero_cnj,
        sistema=sistema,
        data_hoje=str(date.today()),
        eventos_formatados=eventos_formatados,
        documentos_formatados=docs_formatados,
        responsaveis_lista=responsaveis_lista,
        responsaveis_opcoes=responsaveis_opcoes,
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"erro": "ANTHROPIC_API_KEY não encontrada no .env", "numero_cnj": numero_cnj}

    # verify=False necessário: antivírus/proxy local injeta certificado SSL não reconhecido pelo Python
    client = anthropic.Anthropic(api_key=api_key, http_client=httpx.Client(verify=False))

    MAX_TENTATIVAS = 3
    resposta_texto = ""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=_build_system_msg(),
                messages=[{"role": "user", "content": prompt}],
            )
            resposta_texto = message.content[0].text.strip() if message.content else ""

            # extrair JSON de bloco ```json...``` se presente (mesmo após texto)
            import re as _re
            bloco = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", resposta_texto, _re.DOTALL)
            if bloco:
                resposta_texto = bloco.group(1).strip()
            elif not resposta_texto.startswith("{"):
                # tentar a partir do primeiro {
                inicio = resposta_texto.find("{")
                if inicio != -1:
                    resposta_texto = resposta_texto[inicio:]

            analise = json.loads(resposta_texto)
            analise["numero_cnj"] = numero_cnj
            analise["total_documentos_analisados"] = len(documentos)
            analise["documentos_enviados_ao_modelo"] = min(len(documentos), MAX_DOCS_PARA_ANALISE)
            analise["modelo"] = MODEL

            u = message.usage
            custo_usd = (u.input_tokens / 1_000_000 * 1) + (u.output_tokens / 1_000_000 * 5)
            print(f"[TOKENS] input: {u.input_tokens:,} | output: {u.output_tokens:,} | total: {u.input_tokens + u.output_tokens:,} | custo: USD {custo_usd:.4f} (~R$ {custo_usd*5.7:.2f})")
            return analise

        except Exception as e:
            # JSONDecodeError (resposta truncada/ruído) e erros de rede transitórios
            # (ex.: WinError 10054 — reset de conexão pelo antivírus/proxy) são retentáveis.
            if tentativa < MAX_TENTATIVAS:
                print(f"  [análise] falha (tentativa {tentativa}/{MAX_TENTATIVAS}): {e} — retentando em 5s...")
                time.sleep(5)
                continue
            import traceback
            return {"erro": str(e), "traceback": traceback.format_exc(),
                    "resposta_bruta": resposta_texto[:500], "numero_cnj": numero_cnj}
