"""
diagnostico_inicializacao.py — onde o agente está registrado para subir sozinho.

Existe porque em 09/09/2026 o Henrique relatou **duas janelas pretas do agente
abrindo sozinhas ao ligar o computador**. Duas janelas = dois agentes, e existem
dois scripts que fazem a mesma coisa (`agente.bat` e `agente-watchdog.bat`) —
os dois com laço próprio, os dois chamando `agente.py`. Registrar os dois na
inicialização dá exatamente esse resultado.

Só LÊ e RELATA. Não mexe em registro, nem em pasta de inicialização, nem em
tarefa agendada: mudar configuração da máquina de outra pessoa é decisão do
Leonardo, e este script existe para dar a ele a informação, não para agir por
conta.

O relatório vai para `eventos_extracao` no Supabase, então o Leonardo lê da
máquina dele — o Henrique só precisa dar um duplo-clique e pode fechar a janela.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import observabilidade as obs

PS = ["powershell", "-NoProfile", "-Command"]
ALVOS = ("agente.py", "agente.bat", "agente-watchdog", "controladoria")


def _rodar(comando: str) -> str:
    try:
        r = subprocess.run(PS + [comando], capture_output=True, text=True, timeout=45)
        return (r.stdout or "").strip()
    except Exception as e:  # noqa: BLE001 — um lugar ilegível não pode parar os outros
        return f"(falhou ao consultar: {e})"


def _interessa(texto: str) -> bool:
    baixo = texto.lower()
    return any(alvo in baixo for alvo in ALVOS)


def coletar() -> dict[str, list[str]]:
    """Os quatro lugares onde algo pode ser registrado para subir com o Windows."""
    achados: dict[str, list[str]] = {}

    pasta_startup = _rodar(
        "Get-ChildItem ([Environment]::GetFolderPath('Startup')) -ErrorAction "
        "SilentlyContinue | ForEach-Object { $_.Name }"
    )
    achados["pasta de inicializacao"] = [
        l for l in pasta_startup.splitlines() if _interessa(l)
    ]

    for chave, rotulo in (
        ("HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "registro do usuario"),
        ("HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run", "registro da maquina"),
    ):
        saida = _rodar(
            f"$p = Get-ItemProperty '{chave}' -ErrorAction SilentlyContinue; "
            "if ($p) { $p.PSObject.Properties | Where-Object { $_.Name -notlike 'PS*' } "
            "| ForEach-Object { $_.Name + ' = ' + $_.Value } }"
        )
        achados[rotulo] = [l for l in saida.splitlines() if _interessa(l)]

    tarefas = _rodar(
        "Get-ScheduledTask -ErrorAction SilentlyContinue | ForEach-Object { "
        "$a = ($_.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join '; '; "
        "$_.TaskName + ' -> ' + $a }"
    )
    achados["tarefa agendada"] = [l for l in tarefas.splitlines() if _interessa(l)]

    # Só python e cmd, e não "qualquer coisa que mencione agente": sem esse
    # filtro entram os próprios terminais que estiverem rodando este
    # diagnóstico, e o relatório vira parede de texto onde o que importa some.
    rodando = _rodar(
        "Get-CimInstance Win32_Process | Where-Object { "
        "($_.Name -eq 'python.exe' -or $_.Name -eq 'cmd.exe') -and "
        "($_.CommandLine -like '*agente.py*' -or $_.CommandLine -like '*agente.bat*' "
        "-or $_.CommandLine -like '*agente-watchdog*') } "
        "| ForEach-Object { $_.Name + ' (PID ' + $_.ProcessId + ') ' + $_.CommandLine }"
    )
    achados["rodando agora"] = [l.strip() for l in rodando.splitlines() if l.strip()]

    return achados


def main() -> None:
    print("Conferindo onde o agente esta registrado para subir sozinho...\n")
    achados = coletar()

    total = sum(len(v) for k, v in achados.items() if k != "rodando agora")
    for lugar, itens in achados.items():
        print(f"[{lugar}]")
        for item in itens or ["  (nada)"]:
            print(f"  {item}")
        print()

    obs.iniciar_rodada(None)
    obs.registrar(
        "diagnostico.inicializacao",
        # Dois ou mais registros de subida automática é o defeito que este
        # script foi escrito para achar. Um só é o esperado.
        ok=total <= 1,
        detalhe=f"maquina={os.environ.get('COMPUTERNAME', '?')} "
                f"pasta={Path(__file__).parent} "
                f"registros_de_inicializacao={total}",
        dados=achados,
    )
    obs.encerrar_rodada()

    print("=" * 55)
    if total > 1:
        print(f"  ACHEI {total} REGISTROS DE INICIALIZACAO — o certo e 1.")
        print("  E por isso que abre mais de uma janela ao ligar o PC.")
    elif total == 1:
        print("  1 registro de inicializacao. E o esperado.")
    else:
        print("  Nenhum registro encontrado nos lugares comuns.")
    print("  Relatorio enviado para o Leonardo. Pode fechar esta janela.")
    print("=" * 55)


if __name__ == "__main__":
    main()
