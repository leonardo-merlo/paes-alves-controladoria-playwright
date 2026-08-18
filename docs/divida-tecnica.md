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

---

### Por que o Chrome para de responder ao CDP: ainda não medido

**Onde:** máquina do Henrique. Nenhum arquivo específico.

**O quê:** em 17/08/2026 as duas rodadas dele morreram com
`connect_over_cdp` estourando os 180s (assinatura no banco:
`duracao_extracao_s = 181`). O que foi corrigido nessa data foi o **estrago** —
uma falha dessas não condena mais a rodada inteira, e o motivo anterior deixou de
ser apagado. A **causa** do travamento continua desconhecida.

Candidatos, em ordem de suspeita: acúmulo de abas no perfil
`C:\ChromeControladoria` (já travou a máquina em 31/07 — ver
`iniciar._urls_que_faltam`), memória depois dos ~14min de PDF.js do RUPE, e o
antivírus interceptando a 9222.

**Por que assim:** não reproduz na máquina do Leonardo, e por dois motivos
independentes — a rede é outra, e o processo pesado do RUPE
(`2817393-23.2026.8.13.0000`) **só aparece com o login do Henrique**. Sem
reproduzir, qualquer correção da causa seria chute.

**O que faz voltar a valer a pena:** a próxima falha na máquina dele. Agora
existem duas coisas que não existiam: `logs/agente-AAAA-MM-DD.log`, com o texto
real do erro, e a contagem de abas impressa no início de cada sistema. Se o log
mostrar dezenas de abas, é acúmulo e a correção é fechar aba usada; se mostrar
três, é memória ou antivírus.

---

### Timeout de 180s do `connect_over_cdp` continua o padrão

**Onde:** `conectar_cdp()` em `pje_extractor.py`, `eproc_extractor.py` e
`rupe_extractor.py`.

**O quê:** os três chamam `connect_over_cdp` sem `timeout`, então vale o padrão
do Playwright (`DEFAULT_PLAYWRIGHT_LAUNCH_TIMEOUT_IN_MILLISECONDS`, 180s). Numa
conexão com `127.0.0.1` isso é absurdo: com 3 abas a conexão fecha em 0,5s
(medido em 31/07). Cada falha custa 3 minutos parado, e como a rodada agora
tolera `LIMITE_FALHAS_CDP` falhas, o pior caso é ~6 minutos de espera.

**Por que assim:** o modo de falha que se quer detectar é justamente "muitas abas
deixam a conexão lenta". Baixar o teto sem saber quanto tempo uma conexão
*saudável* leva na máquina do Henrique, com o número de abas que ela realmente
tem, transformaria rodada lenta em rodada quebrada.

**O que faz mudar de ideia:** ter essa medida. O log já registra a contagem de
abas; com dois ou três dias de rodada dá para ver o tempo típico e fixar um teto
com margem — 30s é o palpite atual, mas é palpite.

---

### `2817393-23.2026.8.13.0000` abre toda rodada e nunca termina

**Onde:** dado no Supabase, mais `PRIORIDADE_SISTEMAS` em `runner.py`.

**O quê:** o RUPE vai na frente da fila de propósito (a sessão dele cai antes das
outras), e esse processo é o único do RUPE. Resultado: ele é o **primeiro de toda
rodada**, gasta ~865s (14min) e, até agora, nunca terminou — em 17/08 chegou até
a gravação e falhou por rede. Toda rodada paga 14 minutos antes de tocar no
primeiro processo que tem chance de dar certo.

**Por que assim:** não é bug, são duas decisões corretas se encontrando. E mexer
nisso é decisão do Leonardo, não do código: as saídas são diferentes entre si
(marcar como `ignorado`, dar um teto de tempo por processo, ou tirar o RUPE da
frente quando tiver um CNJ só).

**O que faz mudar de ideia:** a próxima rodada. Se ele passar, o item morre
sozinho; se falhar de novo pelo mesmo motivo, vira decisão consciente.
