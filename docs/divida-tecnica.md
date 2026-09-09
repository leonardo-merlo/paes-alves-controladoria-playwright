## Dívida técnica

Pendências adiadas de propósito. Ficam aqui, versionadas, e não só numa conversa:
o que só foi dito some, e daqui a três meses ninguém sabe se a duplicação era
descuido ou decisão.

Cada item diz o que foi adiado, por quê, e o que faz voltar a valer a pena mexer.

---

### `atualizar.bat` mata rodada em andamento e orfana o comando

**Onde:** `atualizar.bat`, o `Stop-Process -Force` que derruba o `agente.py`
antes de aplicar a atualização.

**O quê:** o script mata o agente sem cerimônia, sem checar se há rodada
acontecendo. Se rodar durante uma extração, o processo morre entre reivindicar
o comando e escrever o desfecho — e o comando fica `em_andamento` para sempre,
**sem nenhuma exceção gravada, porque não houve exceção: houve morte**. O painel
então trava os dois botões até os 90 minutos de abandono passarem, e destravar
antes disso exige SQL na mão.

É a hipótese mais forte para o travamento de 08/09/2026 às 15:46 (comando pego
em 0,8s, nunca mais atualizado, bloco de erro vazio) — ver `aprendizados.md`.
Não está provado: exigiria a máquina do Henrique no instante exato.

**Por que assim:** em 09/09 foi corrigido o defeito vizinho (o script abria uma
segunda janela do agente), que era barato e não mexia em comportamento. Este
aqui mexe: qualquer conserto tem de decidir o que fazer quando alguém pede
atualização no meio de uma extração de 40 minutos — esperar (e frustrar quem
clicou), recusar (e exigir que ele saiba voltar depois), ou matar e encerrar o
comando direito antes de morrer. São três produtos diferentes, e a escolha é do
Leonardo, não do código. Adiado de propósito em 09/09, com o teste na máquina do
Leonardo em andamento e sem tempo para essa decisão.

**O que faz mudar de ideia:** já vale. O caminho mais barato e menos invasivo é
o terceiro: antes de matar, o script encerra o comando ativo no banco com um
motivo honesto ("atualização interrompeu esta rodada — pode rodar de novo").
Isso não decide nada pelo usuário e elimina o comando órfão, que é o dano real.
Os outros dois desenhos podem esperar.

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

---

### Parede de traceback do asyncio ao fim da rodada

**Onde:** `conectar_cdp()` nos três extratores — o `async_playwright().start()` /
`playwright.stop()` que cada CNJ faz.

**O quê:** depois de a rodada já ter impresso "Concluído", saem vários blocos de
`ValueError: I/O operation on closed pipe`, vindos de
`BaseSubprocessTransport.__del__` e `_ProactorBasePipeTransport.__del__`. É o
coletor de lixo do Python tentando avisar sobre o processo `node.exe` do
Playwright depois que o event loop já foi fechado — no Windows o `__repr__` desse
aviso consulta um pipe que não existe mais e estoura.

**Por que não é defeito:** nada falhou. A extração já terminou, o resumo já foi
gravado e o desfecho de cada processo já está no banco quando esses blocos
aparecem. Medido em 18/08/2026 numa rodada que devolveu os 18 CNJs à fila
corretamente, com os tracebacks logo depois.

**Por que incomoda mesmo assim:** quem lê a janela do agente é o Henrique. Uma
parede de traceback vermelho parece quebra — foi por esse mesmo motivo que o erro
de rede repetido virou uma linha só em `d6dfc75`. E agora isso também entra no
`logs/agente-AAAA-MM-DD.log`, empurrando para longe o que interessa.

**O que fazer quando for a hora:** a saída de verdade não é silenciar o aviso, é
parar de subir e derrubar um driver do Playwright **por CNJ**. Uma instância viva
durante o sistema inteiro tira o ruído e ainda economiza o custo de start/stop a
cada processo. Mexe nos três extratores e no ciclo de vida da conexão, então é
tarefa própria, não um reparo de passagem.

**O que faz voltar a valer a pena:** o Henrique reportar que "deu erro" numa
rodada que na verdade deu certo. Aí o ruído passou a custar diagnóstico.

---

### RESOLVIDO em 19/08 — o Chrome travava por acúmulo de abas

Fica registrado porque a causa custou três dias de investigação e a hipótese
errada apareceu duas vezes.

**O que era:** cada processo extraído deixava abas abertas, cerca de uma a cada
dez documentos lidos. Medido nos logs da máquina do Henrique: 5 abas no início da
rodada, **46** ao fim do bloco do PJe (400 documentos). A partir daí o
`connect_over_cdp` estourava os 180s, porque ele precisa falar com cada aba antes
de começar.

**A prova que fechou o caso** foi o identificador da sessão do Chrome no log
(`ws://.../devtools/browser/<id>`): em 5 rodadas que usaram um Chrome já
castigado por uma extração grande, 5 morreram; nas 2 que rodaram em Chrome recém
aberto, 2 completaram. Determinístico, não intermitente.

**O conserto:** `abas_vazadas` + `fechar_aba_cdp`, limpando ao fim de cada
processo. Por HTTP e não por Playwright — é a conexão do Playwright que trava, e
usá-la para limpar seria pedir socorro a quem está afogando.

**O que o teste de fumaça pegou e o unitário não:** a regra original só fechava
abas dos hosts em `SISTEMA_HOST`, e abrir `pje.tjmg.jus.br` termina em
`sso.cloud.pje.jus.br`. A aba vazada escapava justamente por ter ido para o
login. A regra virou o sufixo `.jus.br`.

---

### A limpeza de abas não recolhe os *workers* que o PJe deixa

**Onde:** `abas_vazadas` (`runner.py`), a trava `aba.get("type") == "page"`.

**O quê:** a limpeza só fecha alvos do tipo `page`. O PJe cria um *worker*
`blob:` por documento lido e não os recolhe. Medido em 09/09/2026 no meio da
rodada: 26 alvos no Chrome, sendo **22 workers**; ao fim do bloco do PJe ainda
havia 15 pendurados, com o Chrome em **5,6 GB / 40 processos**. As abas ficam
limpas e o consumo sobe assim mesmo.

**Por que assim:** a trava do `page` existe por um motivo bom — iframe e service
worker não se fecham por CDP do mesmo jeito, e a regra foi escrita para nunca
fechar o que não é aba de verdade. Recolher worker é outro problema: precisa
saber quais são descartáveis, e fechar o worker errado quebra a página viva que
depende dele. Não foi tentado.

**O que faz mudar de ideia:** se voltar a aparecer rodada que morre de exaustão
no Chrome (o sintoma de 18–19/08, "Chrome já usado nunca roda inteiro") mesmo
com as abas limpas. Hoje o dado de memória existe mas ninguém mediu o efeito
sobre a duração da rodada.

---

### Um blip de rede cega o registro remoto pela rodada inteira

**Onde:** `_remoto_desligado` em `observabilidade.py`.

**O quê:** a primeira falha de gravação desliga `eventos_extracao` até o fim da
rodada. Em 09/09/2026, às 12:07, um `WinError 10054` (conexão resetada) apagou o
registro remoto por **31 minutos** — o resto do bloco do PJe inteiro. O
diagnóstico do dia teve de sair do log local, que é justamente o que a tabela
existe para evitar (o Leonardo investiga de outra máquina).

**Por que assim:** o desligamento existe por uma razão real e medida — sem ele,
uma rede caída faz cada um dos ~200 eventos esperar o timeout do Supabase, e o
registro vira o motivo de a rodada demorar o dobro. Trocar isso por "tenta
sempre" só inverte o defeito.

**O que faz mudar de ideia:** já vale. O desenho mais barato é desligar por
tempo, não pela rodada: parar por 2 minutos e voltar a tentar (com um evento
dizendo que ficou cego e por quanto tempo). Um blip custa 2 minutos de buraco em
vez de uma rodada inteira, e uma rede realmente caída continua não travando
nada. O que não pode continuar é a cegueira ser silenciosa e permanente.

---

### Por que a aba do eProc sumiu em 09/09 continua sem resposta

**Onde:** desconhecido — é esse o problema.

**O quê:** na rodada de 09/09 a aba do eProc estava viva às 12:31:56 (ID
inalterado desde 11:04, comprovado por vigia externo) e não existia mais às
12:43:52. Nenhum código conhecido pode tê-la fechado: a limpeza protege por
`ids_no_inicio` e o ID dela estava lá; o fallback do PJe não disparou (o PJe
achou a aba dele); não foi descarte do Chrome (a aba não estava na barra); e
havia **um** agente só na máquina, conferido pelo processo pai. Ver
`aprendizados.md`, entrada de 09/09.

**Por que assim:** a janela de 12 minutos em que aconteceu é exatamente onde o
vigia de abas morreu. Não sobrou evidência, e inventar uma quinta hipótese sem
ela seria repetir o que já falhou quatro vezes no mesmo dia.

**O que faz mudar de ideia:** a instrumentação que faltava entrou em 3aa2ee6
(`abas.limpeza` diz qual aba foi fechada, no log e no banco). Na próxima
ocorrência a pergunta se responde por consulta. Até lá, isto fica registrado
como aberto — não como resolvido pelos consertos do mesmo dia, que são outros.
