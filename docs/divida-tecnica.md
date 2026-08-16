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

### Certificado digital: 3 processos do PJe sem acesso

**Onde:** nada em código. É configuração da máquina do Henrique.

**O quê:** o PJe recusa a íntegra dos autos a advogado não vinculado, exigindo
login com certificado. Três processos falham por isso a cada rodada, com a
mensagem correta gravada em `motivo_ignorado`.

**Por que assim:** decisão do Leonardo em 16/08 — o erro já diz o motivo exato,
que é o suficiente para o Henrique agir. Além disso, o sistema **nunca faz
login**: ele reusa a sessão aberta na mão. Logo, isto não é engenharia, é
configuração e rotina.

**O que precisa acontecer, quando for a hora:**
1. Instalar a extensão do assinador no perfil `C:\ChromeControladoria` — o
   provável tropeço, porque esse perfil é separado do Chrome do dia a dia e
   extensão não passa de um para outro.
2. O token (pendrive A3) precisa estar plugado durante a rodada.
3. O PIN é digitado pelo Henrique. Não automatizar: é credencial, e o desenho
   atual (ele loga, o robô reusa a sessão) já é o certo.
4. Sessão com certificado costuma cair mais rápido — vira um passo a mais na
   rotina dele, não uma feature.

**O que NÃO fazer:** apontar a extração para o perfil normal do Chrome dele.
Resolveria a extensão de graça, mas o robô passaria a abrir e fechar abas no
navegador de trabalho, e o histórico de 14/08 mostra que mexer em perfil nesta
porta custa caro.

---

### `skill-cowork-cnj.md` não descreve o que a skill realmente faz

**Onde:** `skill-cowork-cnj.md`, na raiz deste repo.

**O quê:** o arquivo não menciona a coluna `sistema` em lugar nenhum — só CNJ,
vara, comarca, polos e classe. Mas a skill que roda na máquina do Henrique grava
`sistema` em todo processo: medido em 16/08, os 67 do banco tinham `pje` (43),
`eproc_tjmg` (9), `pje_tjmg_2inst` (7), `eproc_trf6` (6) e `pje_2g` (2).

São **cinco valores para o mesmo conjunto pequeno**, misturando dois
vocabulários: rótulos genéricos (`pje`, `eproc`), um apelido só dela (`pje_2g`) e
nomes internos do roteador (`eproc_trf6`, `pje_tjmg_2inst`). `pje_2g` e
`pje_tjmg_2inst` são o mesmo sistema escrito de dois jeitos.

**Por que importa:** esse rótulo é palpite tirado do texto da Vara, e o roteador
existe justamente para poder recusá-lo (ver `rotear`). Enquanto o documento não
descrever a regra, ninguém consegue dizer se um palpite errado veio de defeito da
skill ou de e-mail sem informação suficiente.

**O que fazer quando for a hora:** abrir a skill no Cowork, ler a regra que
realmente está lá, trazer para este arquivo e reduzir a um vocabulário só —
de preferência o do `cnj_router`.

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
