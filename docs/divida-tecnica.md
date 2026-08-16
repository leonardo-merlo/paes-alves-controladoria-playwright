## Dívida técnica

Pendências adiadas de propósito. Ficam aqui, versionadas, e não só numa conversa:
o que só foi dito some, e daqui a três meses ninguém sabe se a duplicação era
descuido ou decisão.

Cada item diz o que foi adiado, por quê, e o que faz voltar a valer a pena mexer.

---

### Regra de roteamento CNJ existe em duas linguagens

**Onde:** `cnj_router.py` (agente) e `lib/cnj.ts` (painel, repo
`ia-controladoria-advocacia`).

**O quê:** a tabela que traduz o número do processo em sistema judicial — o
dígito 1/5 do TJMG, a origem `0000` da 2ª instância, o `4.06` que é sempre
federal — está escrita duas vezes. Mexer numa e esquecer a outra faz o painel
dizer uma coisa e o agente fazer outra.

**Por que assim:** o painel precisa responder "pelo número, parece X" sobre
processos que já estão no banco há semanas. A alternativa era o agente gravar a
resposta numa coluna nova, o que exigiria migração em produção e um backfill, e
ainda deixaria o painel incapaz de responder sobre processo que o agente nunca
tocou. Duplicar 40 linhas puras custou menos, em 16/08/2026.

**O que faz mudar de ideia:** a regra passar a mudar com frequência, ou um
terceiro consumidor aparecer. Aí a saída é a coluna no banco, gravada pelo
agente, com backfill.

---

### A ação `iniciar` sobrevive só por compatibilidade

**Onde:** `ACOES` em `agente.py` e a lista equivalente em
`app/api/comandos/route.ts` do painel.

**O quê:** o comando `iniciar` (abre, espera o login e extrai, tudo num clique)
continua existindo ao lado do par `abrir_sistemas` + `extrair`, que o substitui.

**Por que assim:** as duas pontas vivem em máquinas diferentes e são atualizadas
em dias diferentes — a do Henrique roda o `atualizar.bat` quando ele lembra.
Enquanto o `iniciar` existir, um agente velho entende o painel novo e vice-versa,
e nenhuma janela de atualização deixa o Henrique sem sistema.

**O que faz mudar de ideia:** confirmar que a máquina do Henrique está atualizada
e que o painel novo está no ar há algumas semanas. Aí `iniciar` sai dos dois
lados, junto com o `modo_auto` e a máquina de retentativa de login em
`sistema_auth.py`, que só ele usa.
