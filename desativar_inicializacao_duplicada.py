"""
desativar_inicializacao_duplicada.py — deixa UM registro de inicialização.

Existe porque em 09/09/2026 o `diagnostico_inicializacao.py` achou **dois**
registros na máquina do Henrique: uma Tarefa Agendada (`agente-startup` →
`agente-watchdog.bat`) e um atalho na pasta de inicialização
(`AgenteControladoria.lnk`). Dois registros = duas janelas do agente = dois
agentes disputando a mesma tabela `comandos`.

Tira o **atalho**, mantém a **tarefa**: a tarefa a gente sabe exatamente para
onde aponta; o atalho é uma incógnita, e manter a incógnita seria escolher o
pior dos dois para sobreviver.

**Move, não apaga.** O atalho vai para `inicializacao-desativada/` ao lado do
código. Desfazer é arrastar o arquivo de volta. Apagar configuração da máquina
de outra pessoa sem caminho de volta não é um risco que valha economizar três
linhas.

Três recusas de propósito, porque um script que "conserta" a inicialização e
erra deixa o Henrique sem agente nenhum na manhã seguinte:

1. Se houver 1 registro ou menos, não faz nada — já está certo.
2. Se não houver Tarefa Agendada, não faz nada — tirar o atalho deixaria zero.
3. Se não achar nenhum atalho para tirar, não faz nada — e diz o que viu.

Ao final reconfere e manda o estado novo para o Supabase, para o Leonardo ver o
resultado sem precisar pedir print.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import observabilidade as obs
from diagnostico_inicializacao import _rodar, _interessa, coletar

PASTA_DESATIVADOS = "inicializacao-desativada"


def pasta_de_inicializacao() -> Path | None:
    """Onde o Windows guarda os atalhos que sobem com a sessão."""
    caminho = _rodar("[Environment]::GetFolderPath('Startup')").strip()
    if caminho and Path(caminho).is_dir():
        return Path(caminho)
    # Reserva: o PowerShell pode falhar (política, perfil quebrado). O caminho
    # padrão vale para toda instalação do Windows em português ou inglês.
    appdata = os.environ.get("APPDATA")
    if appdata:
        padrao = Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup"
        if padrao.is_dir():
            return padrao
    return None


def atalhos_do_agente(pasta: Path) -> list[Path]:
    """Só os atalhos que são deste projeto — ver _interessa."""
    try:
        return [a for a in pasta.iterdir() if a.is_file() and _interessa(a.name)]
    except Exception:  # noqa: BLE001 — pasta ilegível não é motivo para estourar
        return []


def main() -> None:
    print("Conferindo como o agente esta configurado para subir...\n")
    antes = coletar()
    total = sum(len(v) for k, v in antes.items() if k != "rodando agora")
    tem_tarefa = bool(antes.get("tarefa agendada"))

    def relatar(resultado: str, ok: bool, dados: dict | None = None) -> None:
        obs.iniciar_rodada(None)
        obs.registrar(
            "diagnostico.desativar_inicializacao", ok=ok,
            detalhe=f"maquina={os.environ.get('COMPUTERNAME', '?')} "
                    f"registros_antes={total} — {resultado}",
            dados=dados or {"antes": antes},
        )
        obs.encerrar_rodada()

    if total <= 1:
        print(f"Ja esta certo: {total} registro de inicializacao.")
        print("Nao mexi em nada.")
        relatar("nada a fazer, ja havia 1 registro ou menos", ok=True)
        return

    if not tem_tarefa:
        print("Achei mais de um registro, mas NENHUM e Tarefa Agendada.")
        print("Nao vou mexer: tirar o atalho poderia deixar o agente sem subir.")
        print("Avise o Leonardo.")
        relatar("recusado: mais de um registro, porem sem tarefa agendada", ok=False)
        return

    pasta = pasta_de_inicializacao()
    if pasta is None:
        print("Nao consegui achar a pasta de inicializacao do Windows.")
        print("Avise o Leonardo.")
        relatar("recusado: pasta de inicializacao nao encontrada", ok=False)
        return

    alvos = atalhos_do_agente(pasta)
    if not alvos:
        print(f"Nenhum atalho do agente na pasta de inicializacao ({pasta}).")
        print("O segundo registro esta em outro lugar. Avise o Leonardo.")
        relatar(f"recusado: nenhum atalho em {pasta}", ok=False)
        return

    destino = Path(__file__).parent / PASTA_DESATIVADOS
    destino.mkdir(exist_ok=True)

    movidos: list[str] = []
    falhas: list[str] = []
    for atalho in alvos:
        try:
            shutil.move(str(atalho), str(destino / atalho.name))
            movidos.append(atalho.name)
            print(f"  Desativado: {atalho.name}")
        except Exception as e:  # noqa: BLE001 — um atalho travado não para os outros
            falhas.append(f"{atalho.name}: {e}")
            print(f"  NAO consegui mover {atalho.name}: {e}")

    depois = coletar()
    total_depois = sum(len(v) for k, v in depois.items() if k != "rodando agora")

    relatar(
        f"movidos={movidos or 'nenhum'} falhas={falhas or 'nenhuma'} "
        f"registros_depois={total_depois}",
        ok=bool(movidos) and not falhas and total_depois <= 1,
        dados={"antes": antes, "depois": depois, "movidos": movidos,
               "falhas": falhas, "guardados_em": str(destino)},
    )

    print()
    print("=" * 55)
    if movidos and total_depois <= 1:
        print("  Pronto. Agora o agente sobe UMA vez so.")
        print("  Na proxima vez que ligar o PC, deve abrir 1 janela preta.")
    elif movidos:
        print(f"  Movi {len(movidos)}, mas ainda vejo {total_depois} registros.")
        print("  O Leonardo vai conferir.")
    else:
        print("  Nao consegui desativar nada. O Leonardo vai conferir.")
    print(f"  O atalho foi GUARDADO em: {destino}")
    print("  (nao foi apagado — da para voltar atras)")
    print("  Relatorio enviado para o Leonardo. Pode fechar esta janela.")
    print("=" * 55)


if __name__ == "__main__":
    main()
