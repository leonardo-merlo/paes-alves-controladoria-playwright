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
from pathlib import Path

from iniciar import main as executar_extracao
from reanalisar import listar_sem_rascunho, reanalisar_um
from supabase_writer import _get_client, _carregar_env

INTERVALO_S = 3

# Enquanto este arquivo existir na pasta, o agente ignora comandos novos. Serve
# para tirar uma máquina do ar — por exemplo, rodar as extrações noutro
# computador — sem mexer na inicialização do Windows e sem depender de alguém
# lembrar de fechar a janela: o agente pode subir sozinho que fica quieto.
# Está no .gitignore de propósito, para o atualizar.bat não apagá-lo.
# Não interrompe rodada em andamento: só impede que a próxima comece.
NOME_ARQUIVO_PAUSA = "AGENTE-PAUSADO.txt"

# Uma rodada de extração leva 20-45min. Um comando 'em_andamento' mais antigo
# que isto é tratado como rodada abandonada (agente caiu no meio) e deixa de
# bloquear novas rodadas — senão a fila travaria pra sempre após um crash.
LIMITE_RODADA_ABANDONADA_MIN = 90


# Trechos que aparecem quando a máquina está sem rede. O agente sobe junto com o
# Windows, antes de o Wi-Fi conectar, e passa alguns minutos sem conseguir falar
# com o Supabase — situação normal, não defeito.
ERROS_DE_REDE = (
    "getaddrinfo failed",
    "11001",
    "Name or service not known",
    "Temporary failure in name resolution",
    "Max retries exceeded",
    "Connection aborted",
    "Connection reset",
    "10054",
)


def esta_pausado(pasta: Path | None = None) -> bool:
    """Esta máquina foi colocada em pausa? Ver NOME_ARQUIVO_PAUSA."""
    base = pasta or Path(__file__).parent
    return (base / NOME_ARQUIVO_PAUSA).exists()


def resumir_erro_do_loop(erro: str) -> str:
    """
    Vira a linha que aparece na janela do agente. Função pura — ver test_agente.py.

    Falha de rede recebe texto de gente: quem olha essa janela é o Henrique, e
    "getaddrinfo failed" não diz nada para ele.
    """
    if any(marca in erro for marca in ERROS_DE_REDE):
        return "Sem conexão com a internet — aguardando a rede voltar..."
    return f"Erro no loop do agente: {erro}"


def deve_imprimir(mensagem: str, ultima_mensagem: str | None) -> bool:
    """
    Só imprime quando a mensagem muda. Função pura — ver test_agente.py.

    Sem isto, uma falha que se repete a cada 3s vira parede de texto: em 15/08 a
    janela do Henrique encheu de erro de rede repetido e pareceu que o agente
    tinha quebrado, quando ele estava só esperando o Wi-Fi subir.
    """
    return mensagem != ultima_mensagem


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
        resumo["reanalisados"] = varrer_sem_rascunho(client)
        status, mensagem = _resumo_para_status(resumo)
        marcar(client, cid, status, mensagem)
        print(f"Comando {status}: {mensagem}")
    except Exception as e:  # noqa: BLE001 — agente não pode morrer por um comando
        marcar(client, cid, "erro", f"Erro: {e}")
        print(f"Erro ao executar comando: {e}")
        traceback.print_exc()
    return True


def varrer_sem_rascunho(client) -> int:
    """
    Reanalisa quem ficou 'processado' sem rascunho. Retorna quantos foram salvos.

    Existe porque a extração é incremental: se a análise falha depois de os
    documentos serem salvos (agente morre no meio, API fora do ar, resposta
    truncada), o processo fica 'processado' e a rodada seguinte não acha documento
    novo, conclui "nada novo" e segue. Ninguém repara — no painel ele aparece
    pronto, sem prazo nenhum, que é o pior desfecho num controle de prazo.
    Não abre navegador nem precisa de login: trabalha sobre o que já está no banco.
    """
    try:
        alvos = listar_sem_rascunho(client)
    except Exception as e:  # noqa: BLE001 — varredura não pode derrubar a rodada
        print(f"Varredura de rascunhos: falhou ao listar ({e}) — seguindo.")
        return 0

    if not alvos:
        return 0

    print(f"\nVarredura: {len(alvos)} processo(s) sem rascunho — reanalisando...")
    salvos = 0
    for processo in alvos:
        cnj = processo["numero_cnj"]
        try:
            resultado = reanalisar_um(client, processo)
            print(f"  {cnj} — {resultado}")
            # reanalisar_um devolve texto; só "OK" significa rascunho gravado
            if resultado.startswith("OK"):
                salvos += 1
        except Exception as e:  # noqa: BLE001 — um processo ruim não para a lista
            print(f"  {cnj} — ERRO na reanálise: {e}")
    return salvos


def _resumo_para_status(resumo: dict) -> tuple[str, str]:
    """Traduz o resumo da extração em (status, mensagem) honestos para o app."""
    total = resumo.get("total", 0)
    n_ok = resumo.get("processados", 0)
    n_err = resumo.get("erros", 0)
    n_rev = resumo.get("revisao_manual", 0)
    n_novo = resumo.get("nada_novo", 0)
    n_rean = resumo.get("reanalisados", 0)

    # processo salvo sem análise não conta como erro, mas não pode passar em
    # silêncio: ele aparece no painel como pronto e sem prazo nenhum.
    aviso = f" {n_rev} sem análise — revisar." if n_rev else ""
    # já estavam extraídos e não tinham documento novo: sucesso, mas não é
    # extração desta rodada — somar no total faria o painel inflar o número.
    novidade = f", {n_novo} sem novidade" if n_novo else ""
    # análise recuperada de rodada anterior — não é extração desta, mas o Henrique
    # precisa saber que apareceu rascunho novo em processo que ele já dava por visto.
    recuperados = f" {n_rean} análise(s) recuperada(s)." if n_rean else ""

    if resumo.get("cdp_falhou"):
        return "erro", "Não foi possível abrir o navegador (CDP)."
    if total == 0:
        return "concluido", f"Nenhum processo pendente.{recuperados}"
    if n_ok == 0 and n_novo == 0:
        return "erro", f"Nada extraído ({n_err} com erro). Login não concluído? Verifique."
    if n_err > 0:
        return "concluido", f"{n_ok} processado(s){novidade}, {n_err} com erro.{aviso}{recuperados}"
    return "concluido", f"{n_ok} processado(s){novidade}.{aviso}{recuperados}"


def main_loop() -> None:
    _carregar_env()
    client = _get_client()
    print("Agente da controladoria iniciado. Aguardando comandos (Ctrl+C para sair)...")
    avisou_pausa = False
    ultimo_aviso: str | None = None
    while True:
        try:
            if esta_pausado():
                if not avisou_pausa:
                    print(f"\nAGENTE PAUSADO nesta máquina ({NOME_ARQUIVO_PAUSA} existe).")
                    print("Nenhuma extração será executada aqui. Para religar, use voltar-agente.bat\n")
                    avisou_pausa = True
            else:
                if avisou_pausa:
                    print("\nAgente religado. Aguardando comandos...\n")
                    avisou_pausa = False
                processar_um(client)
            if ultimo_aviso is not None:
                print("Conexão restabelecida. Aguardando comandos...")
                ultimo_aviso = None
        except Exception as e:  # noqa: BLE001 — loop nunca para por erro de rede
            aviso = resumir_erro_do_loop(str(e))
            if deve_imprimir(aviso, ultimo_aviso):
                print(aviso)
                ultimo_aviso = aviso
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main_loop()
