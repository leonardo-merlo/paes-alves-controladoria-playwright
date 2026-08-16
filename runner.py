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
import time
from collections import defaultdict
from datetime import date, timezone, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from analyzer import analisar_processo
from cnj_router import rotear_lista, motivo_sem_extrator, CNJInfo
from extrator_dispatch import obter_extrator, esta_implementado, descricao_pendente
from sistema_auth import preparar_autenticacao, monitorar_logins_e_processar
from supabase_writer import salvar_no_supabase, _get_client, _carregar_env

INPUTS_DIR = Path("inputs")

MOTIVO_CHROME = ("Chrome parou de responder — feche o Chrome por completo, "
                 "abra de novo, faça login e rode outra vez")
MOTIVO_SESSAO = "Sessão caiu durante a rodada — refazer login e rodar de novo"
MOTIVO_LOGIN_PENDENTE = "Login ainda não estava feito quando a extração tentou"

# Como a rodada trata o login. Eram dois valores num booleano (`modo_auto`) e
# passaram a ser três quando "abrir os sistemas" virou um comando separado de
# "extrair" — ver docs/handoff-2026-08-16-separar-login-e-painel.md.
MODO_INTERATIVO = "interativo"       # abre as abas e espera Enter no terminal
MODO_AUTO = "auto"                   # observa o Chrome e dispara sozinho
MODO_ASSUMIR_LOGADO = "assumir_logado"  # o login já foi feito, vai direto
MODOS = (MODO_INTERATIVO, MODO_AUTO, MODO_ASSUMIR_LOGADO)

# Quem é logado primeiro é quem mais tempo passa parado esperando a vez. A sessão
# do RUPE cai antes das outras, então ela vai na frente: com os logins todos
# feitos ANTES da extração (ver a ação `abrir_sistemas`), a diferença entre ser o
# primeiro e ser o último da fila pode ser meia hora de sessão envelhecendo.
# Os que não estão listados mantêm a ordem em que chegaram.
PRIORIDADE_SISTEMAS = ["pje_tjmg_2inst"]


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


def ids_com_documentos(ids: list[str]) -> set[str]:
    """
    Quais desses processos já têm documento salvo.
    Serve de trava para a extração incremental: se a gravação anterior falhou no
    meio (data_ultima_consulta gravada, documentos não), extrair a partir da data
    de corte devolveria 0 documentos e o processo passaria por "nada novo" —
    ficando 'processado' sem nenhum documento no banco.
    """
    if not ids:
        return set()
    _carregar_env()
    client = _get_client()
    encontrados: set[str] = set()
    # in_() com lista grande estoura o tamanho da URL — vai em lotes.
    for i in range(0, len(ids), 50):
        res = (
            client.table("documentos")
            .select("processo_id")
            .in_("processo_id", ids[i:i + 50])
            .execute()
        )
        encontrados.update(r["processo_id"] for r in (res.data or []))
    return encontrados


def marcar_supabase(ids: list[str], status: str, motivo: str | None = None) -> None:
    if not ids:
        return
    _carregar_env()
    client = _get_client()
    update: dict = {"pje_status": status}
    if motivo:
        update["motivo_ignorado"] = motivo
    elif status == "processado":
        # sem limpar, um processo que volta a dar certo carrega para sempre o
        # motivo da falha anterior — o painel passa a mentir sobre o estado atual.
        update["motivo_ignorado"] = None
    client.table("processos").update(update).in_("id", ids).execute()


def gravar_duracao(cnj_id: str, segundos: int) -> None:
    """Quanto tempo este processo levou. Uma linha por CNJ, não em lote."""
    _carregar_env()
    client = _get_client()
    client.table("processos").update(
        {"duracao_extracao_s": segundos}
    ).eq("id", cnj_id).execute()


def duracao_segundos(inicio: float, fim: float) -> int:
    """
    Segundos inteiros entre dois instantes de time.monotonic().
    Função pura — ver test_runner.py. Nunca negativo: número negativo gravado
    envenena a média do painel de forma silenciosa.
    """
    return max(0, round(fim - inicio))


def ordenar_sistemas(sistemas: list[str]) -> list[str]:
    """
    Em que ordem os sistemas são extraídos. Função pura — ver test_runner.py.

    Antes a ordem saía de `list(por_sistema.keys())`, que segue a `data_entrada`
    dos CNJs — acidental, portanto. Ver PRIORIDADE_SISTEMAS para o porquê do RUPE
    na frente. Estável no resto: reordenar o que não precisa só tornaria a rodada
    difícil de comparar com a de ontem.
    """
    prioritarios = [s for s in PRIORIDADE_SISTEMAS if s in sistemas]
    restantes = [s for s in sistemas if s not in prioritarios]
    return prioritarios + restantes


def eh_nada_novo(total_documentos: int, data_corte: str | None) -> bool:
    """
    0 documentos numa extração incremental = nada mudou desde a última consulta.
    É o desfecho normal de um processo já extraído que voltou à fila numa pauta
    nova. Tratar isso como erro apagava do painel um processo que já estava
    pronto, com documentos e rascunho salvos.
    Na primeira extração (sem corte) 0 documentos continua sendo falha de verdade.
    """
    return total_documentos == 0 and bool(data_corte)


def eh_queda_de_sessao(resultado: dict | None) -> bool:
    """
    O sistema não está pronto — todo CNJ seguinte da fila vai falhar igual.

    Duas formas do mesmo desfecho. `sessao_expirada` é a aba aberta e deslogada.
    "Nenhuma aba" é não haver aba nenhuma daquele sistema no Chrome do agente —
    que é o estado normal antes de o operador logar, não um erro do processo.
    Sem a segunda, cada CNJ virava `erro_browser` individualmente e o sistema
    era dado como resolvido, matando as 3 retentativas de 5/10/15 min: em 14/08
    a fila do eProc, TRF6 e RUPE (15 CNJs) foi queimada em 15 segundos, antes de
    o Henrique ter chance de digitar a senha.
    """
    if not resultado:
        return False
    erro = str(resultado.get("erro") or "")
    return "sessao_expirada" in erro or "Nenhuma aba" in erro


def eh_chrome_inacessivel(resultado: dict | None) -> bool:
    """
    Não dá para falar com o Chrome. Insistir é pior que parar: cada CNJ gasta os
    180s de timeout do Playwright antes de falhar, e uma fila de 20 vira uma hora
    de nada. Além disso o Chrome nesse estado não se recupera sozinho — precisa
    ser fechado e aberto de novo.
    """
    if not resultado:
        return False
    erro = str(resultado.get("erro") or "")
    return "connect_over_cdp" in erro or "conectar ao Chrome" in erro


def motivo_do_erro(resultado: dict | None) -> str:
    """
    Mensagem real do extrator, para gravar em `motivo_ignorado`.
    Sem isto o banco só guarda "Erro durante processamento" e o diagnóstico
    depende de alguém estar olhando o terminal na hora em que falhou.
    """
    if not resultado:
        return "Erro durante processamento (extrator não retornou resultado)"
    erro = str(resultado.get("erro") or "desconhecido").strip()
    detalhe = str(resultado.get("mensagem") or "").strip()
    texto = f"{erro} — {detalhe}" if detalhe else erro
    return texto[:400]


# Do texto cru do erro para uma frase curta. A ordem importa: a primeira que
# casar vence, então o específico vem antes do genérico.
# Espelha as categorias do painel (app/dashboard/erros.ts) de propósito — as duas
# pontas descrevem a mesma rodada e não podem discordar na frente do Henrique.
CATEGORIAS_MOTIVO: list[tuple[str, str]] = [
    ("certificado digital", "os processos exigem certificado digital"),
    ("recusou o acesso", "o sistema recusou o acesso"),
    ("não localizado", "os processos não foram encontrados"),
    ("Tabela de eventos não encontrada", "os processos não foram encontrados"),
    ("sem_documentos", "os processos não têm documento"),
    ("não tem extrator", "não há extrator para esse tribunal"),
    ("Sistema não implementado", "não há extrator para esse tribunal"),
    ("sessao_expirada", "a sessão caiu"),
    ("Nenhuma aba", "o sistema não estava aberto"),
    ("Chrome parou", "o Chrome não respondeu"),
    ("supabase_falhou", "falha ao gravar no banco"),
]


def resumir_motivos(motivos: list[str]) -> str | None:
    """
    A categoria mais frequente entre os erros, em texto de gente. Função pura —
    ver test_runner.py. `None` quando não há motivo reconhecível.

    Serve para o agente parar de chutar "Login não concluído?" quando nenhum
    processo é extraído: em 16/08 essa frase apareceu duas vezes com os erros
    todos em certificado digital, ou seja, com o login perfeitamente feito.
    """
    contagem: dict[str, int] = defaultdict(int)
    for motivo in motivos:
        for marca, frase in CATEGORIAS_MOTIVO:
            if marca in motivo:
                contagem[frase] += 1
                break
    if not contagem:
        return None
    return max(contagem.items(), key=lambda par: par[1])[0]


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
    """
    Extrai e analisa um CNJ, cronometrado.

    Mede todas as tentativas, inclusive as que falham: tempo gasto num processo que
    deu erro é tempo real. Quais entram na média é decisão da interface, não daqui.
    """
    inicio = time.monotonic()
    resultado = await _extrair_e_analisar(info, data_str, prefixo, data_corte=data_corte)
    if isinstance(resultado, dict):
        resultado["duracao_extracao_s"] = duracao_segundos(inicio, time.monotonic())
    return resultado


async def _extrair_e_analisar(
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

        try:
            resultado = await extrator(info.numero_cnj, data_corte=data_corte, sistema_hint=info.sistema)
        except Exception as e:
            resultado = {"erro": str(e), "numero_cnj": info.numero_cnj}

        if resultado.get("erro"):
            erro_msg = resultado["erro"]
            # recusa de acesso não muda por insistência — retentar só repete o alerta
            _permanente = ("sessao_expirada", "Nenhuma aba", "Não foi possível conectar",
                           "recusou o acesso")
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

        if eh_nada_novo(total, data_corte):
            break  # retentar não traz documento que não existe

        if tentativa < MAX_TENTATIVAS:
            print(f"{prefixo} — 0 documentos, retentando em 5s...")
            await asyncio.sleep(5)

    if resultado.get("total_documentos", 0) == 0:
        if eh_nada_novo(0, data_corte):
            print(f"{prefixo} — nada novo desde {data_corte[:10]} — segue processado")
            return {"nada_novo": True, "numero_cnj": info.numero_cnj}
        print(f"{prefixo} — ERRO: nenhum documento após {MAX_TENTATIVAS} tentativa(s)")
        return {"erro": "sem_documentos", "numero_cnj": info.numero_cnj}

    print(f"{prefixo} — analisando com Claude...")
    analise = analisar_processo(info.numero_cnj, resultado)

    motivo_revisao: str | None = None
    if analise.get("erro"):
        # análise falhou (ex: sem créditos API) — salva os documentos mesmo assim
        print(f"{prefixo} — AVISO análise: {analise['erro']} — salvando documentos sem análise")
        motivo_revisao = f"ANÁLISE NÃO GERADA ({analise['erro']}) — revisar manualmente"[:400]
        analise = {}  # rascunho vazio; pje_status ficará 'processado' sem análise

    if not analise.get("erro"):
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

    if motivo_revisao:
        # sem este aviso o processo fica 'processado' e some do painel sem prazo
        # nenhum — o pior desfecho num sistema de controle de prazo, porque
        # ninguém vai olhar de novo um processo que aparece como pronto.
        resultado["revisao_manual"] = motivo_revisao

    return resultado


# ── orquestração por sistema ──────────────────────────────────────

async def processar_por_sistema(
    cnjs_roteados: list[CNJInfo],
    data_str: str,
    ids_map: dict[str, str] | None = None,
    corte_map: dict[str, str | None] | None = None,
    modo: str = MODO_INTERATIVO,
) -> tuple[list[str], list[str], list[tuple[str, str]], list[str]]:
    """
    Agrupa os CNJs por sistema, autentica uma vez, processa um sistema por vez.
    Retorna (ids_ok, ids_erro, ids_revisao, ids_nada_novo, motivos_erro).
    `motivos_erro`  é o texto cru de cada falha, para o agente dizer a causa real.
    `ids_revisao`   são processos salvos porém sem análise — precisam de aviso.
    `ids_nada_novo` já estavam extraídos e não tinham documento novo — continuam
    processados, mas não devem ser contados como extração desta rodada.
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
        return [], [], [], [], []

    sistemas_necessarios = ordenar_sistemas(list(por_sistema.keys()))
    ids_ok: list[str] = []
    ids_erro: list[str] = []
    ids_revisao: list[tuple[str, str]] = []
    ids_nada_novo: list[str] = []
    # texto cru de cada falha, para o agente poder dizer o motivo real em vez de
    # chutar "login não concluído" — ver resumir_motivos
    motivos_erro: list[str] = []

    # o Chrome travado não se recupera sozinho: uma vez detectado, nenhum sistema
    # seguinte tem chance. A flag para a rodada inteira, não só o sistema atual.
    chrome_morreu = False

    def _devolver_a_fila(restantes: list[CNJInfo], motivo: str) -> None:
        ids = [ids_map[o.numero_cnj] for o in restantes
               if ids_map and o.numero_cnj in ids_map]
        if ids:
            print(f"  {len(ids)} CNJ(s) devolvidos à fila")
        marcar_supabase(ids, "pendente", motivo)

    async def _processar_sistema(sistema: str) -> bool:
        """
        Processa a fila de um sistema. Devolve False quando não havia sessão logo
        no PRIMEIRO processo — sinal de que ninguém logou ainda e vale tentar de
        novo mais tarde. Todo o resto devolve True: o sistema está resolvido para
        esta rodada, mesmo que tenha dado erro.
        """
        nonlocal chrome_morreu
        infos = por_sistema[sistema]
        total = len(infos)

        if chrome_morreu:
            print(f"[{sistema}] pulado — o Chrome não está respondendo")
            _devolver_a_fila(infos, MOTIVO_CHROME)
            return True

        print(f"{'='*50}")
        print(f"[{sistema}] {total} CNJ(s)\n")
        for i, info in enumerate(infos, 1):
            prefixo = f"  [{i}/{total}] {info.numero_cnj}"
            data_corte = corte_map.get(info.numero_cnj) if corte_map else None
            resultado = await processar_cnj(info, data_str, prefixo, data_corte=data_corte)
            cnj_id = ids_map.get(info.numero_cnj) if ids_map else None

            # antes das checagens abaixo de propósito: tentativa que morreu no meio
            # também consumiu tempo. A próxima tentativa sobrescreve o valor.
            if cnj_id and isinstance(resultado, dict) and "duracao_extracao_s" in resultado:
                gravar_duracao(cnj_id, resultado["duracao_extracao_s"])

            if eh_chrome_inacessivel(resultado):
                chrome_morreu = True
                print(f"  [{sistema}] o Chrome parou de responder — abortando a rodada")
                print(f"  >>> {MOTIVO_CHROME}")
                _devolver_a_fila(infos[i - 1:], MOTIVO_CHROME)
                break

            if eh_queda_de_sessao(resultado):
                # seguir a fila só queima os CNJs restantes contra um sistema
                # deslogado — em 29/07 foram 37 assim, em 1h40. O que não chegou
                # a ser tentado volta para 'pendente': não é erro, é fila.
                if i == 1:
                    # falhar já no primeiro é a assinatura de "ninguém logou
                    # ainda", não de sessão que caiu. Nada foi extraído, então
                    # tentar de novo mais tarde não repete trabalho nenhum.
                    print(f"  [{sistema}] sem sessão ainda — fila devolvida, tentará de novo")
                    _devolver_a_fila(infos, MOTIVO_LOGIN_PENDENTE)
                    return False
                print(f"  [{sistema}] sessão caiu — devolvendo o resto da fila")
                _devolver_a_fila(infos[i - 1:], MOTIVO_SESSAO)
                break

            if resultado and not resultado.get("erro") and cnj_id:
                ids_ok.append(cnj_id)
                if resultado.get("nada_novo"):
                    ids_nada_novo.append(cnj_id)
                if resultado.get("revisao_manual"):
                    ids_revisao.append((cnj_id, resultado["revisao_manual"]))
            elif cnj_id:
                ids_erro.append(cnj_id)
                motivo = motivo_do_erro(resultado)
                motivos_erro.append(motivo)
                marcar_supabase([cnj_id], "erro_browser", motivo)
        print()
        return True

    if modo == MODO_AUTO:
        processados = await monitorar_logins_e_processar(sistemas_necessarios, _processar_sistema)
        nao_processados = [s for s in sistemas_necessarios if s not in processados]
        if ids_map and nao_processados:
            ids_timeout = [
                ids_map[info.numero_cnj]
                for s in nao_processados
                for info in por_sistema.get(s, [])
                if info.numero_cnj in ids_map
            ]
            # login não concluído = não houve extração. Marcar erro aqui fazia
            # o painel acusar falha em processo que nunca chegou a ser lido.
            marcar_supabase(
                ids_timeout, "pendente",
                "Login não concluído dentro do tempo — nenhuma sessão ativa nas tentativas",
            )
    elif modo == MODO_ASSUMIR_LOGADO:
        # O login foi feito antes, por outro comando, com o tempo que precisasse.
        # Não existe máquina de retentativa aqui de propósito: se ainda faltar
        # sessão, o primeiro CNJ de cada sistema falha e _processar_sistema
        # devolve a fila inteira para 'pendente' sem queimar processo nenhum.
        print(f"Extraindo direto (logins já feitos): {', '.join(sistemas_necessarios)}\n")
        for sistema in sistemas_necessarios:
            await _processar_sistema(sistema)
    elif modo == MODO_INTERATIVO:
        ok = await preparar_autenticacao(sistemas_necessarios, modo_auto=False)
        if not ok:
            return [], [], [], [], []
        for sistema in sistemas_necessarios:
            await _processar_sistema(sistema)
    else:
        # Cair no interativo por engano seria pior do que estourar: ele chama
        # input(), e o agente não tem terminal — ficaria pendurado até alguém
        # notar que a rodada nunca termina.
        raise ValueError(f"Modo desconhecido: {modo!r} (esperado um de {MODOS})")

    # ids de CNJs não implementados → ignorado, com a mensagem daquele tribunal
    # (uma chamada por processo, e não em bloco: o texto do TRF1 carrega a origem
    # dele — ver cnj_router.motivo_sem_extrator)
    if ids_map:
        for info in nao_impl:
            cnj_id = ids_map.get(info.numero_cnj)
            if cnj_id:
                motivo = motivo_sem_extrator(info.numero_cnj)
                motivos_erro.append(motivo)
                marcar_supabase([cnj_id], "ignorado", motivo)

    return ids_ok, ids_erro, ids_revisao, ids_nada_novo, motivos_erro


# ── modos de execução ─────────────────────────────────────────────

async def modo_supabase(modo: str = MODO_INTERATIVO) -> dict:
    """Processa os pendentes do Supabase. Retorna resumo {total, processados, erros}."""
    pendentes = ler_cnjs_supabase()
    if not pendentes:
        print("Nenhum CNJ pendente no Supabase.")
        return {"total": 0, "processados": 0, "erros": 0}

    numeros = [p["numero_cnj"] for p in pendentes]
    ids_map = {p["numero_cnj"]: p["id"] for p in pendentes}
    # só extrai incremental quem realmente tem os documentos anteriores salvos
    com_docs = ids_com_documentos([p["id"] for p in pendentes])
    corte_map = {
        p["numero_cnj"]: (p.get("data_ultima_consulta") if p["id"] in com_docs else None)
        for p in pendentes
    }
    hints = {p["numero_cnj"]: p.get("sistema") for p in pendentes}
    cnjs = rotear_lista(numeros, hints)
    data_str = str(date.today())

    print(f"Supabase: {len(cnjs)} CNJ(s) únicos pendentes")
    ids_ok, ids_erro, ids_revisao, ids_nada_novo, motivos_erro = await processar_por_sistema(
        cnjs, data_str, ids_map, corte_map, modo=modo
    )
    print(f"ids_ok={ids_ok}")
    print(f"ids_erro={ids_erro}")
    marcar_supabase(ids_ok, "processado")
    # depois de marcar 'processado' (que limpa motivo_ignorado), reescreve o aviso
    # nos que ficaram sem análise — senão eles aparecem no painel como prontos.
    for cnj_id, motivo in ids_revisao:
        marcar_supabase([cnj_id], "processado", motivo)
    # os ids com erro já foram marcados um a um, com o motivo real, dentro de
    # _processar_sistema — remarcar em bloco aqui sobrescreveria esse detalhe.
    # "extraído" e "nada novo" contam como sucesso, mas dizer que 12 foram
    # processados quando 9 só foram reconferidos confunde quem lê o painel.
    extraidos = len(ids_ok) - len(ids_nada_novo)
    aviso = f", {len(ids_revisao)} sem análise (revisão manual)" if ids_revisao else ""
    sem_novidade = f", {len(ids_nada_novo)} sem novidade" if ids_nada_novo else ""
    print(f"Concluído: {extraidos} processados{sem_novidade}, {len(ids_erro)} com erro{aviso}")
    return {"total": len(cnjs), "processados": extraidos, "erros": len(ids_erro),
            "revisao_manual": len(ids_revisao), "nada_novo": len(ids_nada_novo),
            "motivo_principal": resumir_motivos(motivos_erro)}


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
