# Aprendizados

Registro do que a gente descobre investigando incidentes reais — não é plano,
não é dívida técnica (isso fica em `divida-tecnica.md`), é "isto aconteceu,
isto foi o motivo real, é bom lembrar disso da próxima vez". Entradas por data,
mais recente primeiro. Nunca reescreve entrada antiga — só acrescenta.

---

## 09/09/2026 — duas janelas do agente, e a hipótese que fecha o 08/09

O Henrique tinha **duas janelas pretas** do agente abertas. O certo é uma.

**Correção do mesmo dia:** minha primeira explicação foi o `atualizar.bat`
abrindo uma janela extra numa corrida de tempo. **Estava errada.** O Henrique
depois esclareceu que as duas janelas abrem **ao ligar o computador**, sem
ninguém rodar nada — ou seja, são dois registros de inicialização automática,
não um efeito do script de atualização.

A causa real: existem **dois scripts que fazem a mesma coisa** — `agente.bat`
(laço de 5s) e `agente-watchdog.bat` (laço de 10s, e ainda sobe o Chrome). Os
dois chamam `agente.py`, os dois se reiniciam sozinhos. Registrar os dois na
inicialização dá exatamente duas janelas. Na máquina do Leonardo há **um**
registro só (Tarefa Agendada apontando para o watchdog), que é o esperado.

O defeito que eu tinha achado no `atualizar.bat` é real e foi corrigido (ele
conferia python e abria vigia — coisas diferentes), mas **não era a causa
disto**. Vale como conserto próprio, não como explicação.

**Por que importa mais do que parece — e aqui está o achado sério:** a trava
que impede dois agentes de rodarem ao mesmo tempo (`ha_rodada_em_andamento`)
ignora comando parado há mais de 90 minutos, tratando como rodada abandonada. E
`atualizado_em` **só é escrito duas vezes**: quando o comando é reivindicado e
quando termina. Nada durante a rodada.

Ou seja: **rodada que passe de 90 minutos vira invisível para o segundo
agente**, que então inicia uma segunda extração — no mesmo Chrome, com as duas
mexendo nas mesmas abas e cada uma fechando as abas "vazadas" que a outra
acabou de abrir. Com um agente só isso nunca podia acontecer. Com dois, é
questão de a rodada ser longa o bastante — e já houve dia com mais de 6 horas
de extração.

Não está provado que causou o eProc TJMG sem aba, mas é o primeiro mecanismo
encontrado que explicaria uma aba sumir no meio da rodada. O conserto de fundo é
o batimento: o agente escrever `atualizado_em` periodicamente enquanto trabalha,
para "está vivo" e "está parado" deixarem de ser indistinguíveis.

Ferramenta criada no mesmo dia: `conferir-janelas.bat` (duplo-clique) relata
todos os pontos de inicialização automática da máquina para o Supabase, sem
alterar nada.

**A hipótese que isso abre para o travamento de 08/09:** aquele `Stop-Process
-Force` mata o agente sem cerimônia, no meio do que ele estiver fazendo. Se
rodar enquanto uma rodada está em andamento, o processo morre entre reivindicar
o comando e escrever o desfecho — e o comando fica `em_andamento` para sempre,
**sem nenhuma exceção gravada, porque não houve exceção: houve morte**.

Bate exatamente com a assinatura de 08/09 às 15:46: comando reivindicado em
0,8s, nunca mais atualizado, nada no bloco de erro. E bate com as duas janelas
terem aparecido no mesmo dia. Não está provado — exigiria a máquina dele no
momento — mas explica os dois sintomas com um mecanismo só.

**O que ficou pendente:** o `atualizar.bat` continua matando rodada em
andamento. A correção de hoje resolve a janela duplicada, não o kill. Enquanto
isso, atualizar durante uma extração continua podendo orfanar o comando.

**O que isso NÃO explica:** o eProc TJMG sem aba. Dois agentes não brigam pelo
mesmo comando (a trava é atômica), então essa conta continua aberta.

---

## 08/09/2026 — o dia dos três avisos otimistas

Numa rodada só, três etapas diferentes falharam e, nas três, a mensagem que
chegou até o Leonardo/Henrique disse que tinha dado certo. Padrão que vale
vigiar em qualquer coisa nova: **uma etapa que só avisa quando falha, e fica
muda quando o "avisar" em si falha, sempre mente por omissão.**

1. **"Abrir sistemas" travou sem escrever nada.** A primeira chamada que essa
   ação faz — perguntar ao banco quais processos estão pendentes — não tinha
   limite de tempo. Uma rede engasgada ali prendia a função inteira, sem
   exceção pra cair no bloco de erro. Corrigido: teto de 3 minutos
   (`TIMEOUT_ABRIR_SISTEMAS_S`, `agente.py`).

2. **Chrome caiu no meio da extração — e o resumo culpou o login.** O circuito
   de segurança que aborta a rodada quando o Chrome para de responder
   funcionou certinho, gravou o motivo certo em cada processo devolvido. O
   problema era só a frase-resumo do topo: ela só reconhece uma lista fixa de
   causas conhecidas, e "Chrome parou de responder" não estava nessa lista —
   então caiu no texto genérico "Login não concluído? Verifique", que é a
   causa errada e manda a pessoa checar justamente o que estava certo.

3. **eProc TJMG "não estava aberto" — mas a aba nunca foi confirmada.**
   "Abrir sistemas" listou "Abri eProc TJMG" no resumo, mas essa lista é
   montada a partir de QUEM PRECISAVA ser aberto, não de quem de fato abriu.
   O pedido HTTP que abre a aba tem 5s de prazo e pode falhar silenciosamente
   — só um aviso no terminal que ninguém vê. 24 minutos depois, quando a
   extração tentou usar aquela aba, não achou nenhuma — e a falha inteira do
   sistema (35 processos) aconteceu em menos de 1 segundo, sinal forte de que
   a aba nunca chegou a existir, não de que sumiu no meio do caminho.

**Fio comum:** nas três, o código sabia a verdade internamente (o motivo certo
estava gravado por processo, no caso 2) ou tinha como saber e não checou (casos
1 e 3). O consertos pontuais (timeout, mensagem melhor) resolvem o sintoma de
cada um. A causa de fundo — falta de confirmação depois de cada ação, e
mensagens-resumo otimistas por padrão — é maior que os três juntos. Ver
`docs/fluxo-extracao-passo-a-passo.md` para o mapa completo de onde isso ainda
acontece.

**Achado à parte, não-bug:** o RUPE levou 26 minutos para 6 processos nessa
mesma rodada. Não é regressão — já é comportamento conhecido e documentado
(`divida-tecnica.md`, item do CNJ que sozinho levou 14 min). O sistema
simplesmente é lento.

**Achado à parte, explica um "estranho":** a regra que decide "sessão
envelheceu esperando a vez" mede o tempo desde que a RODADA DE EXTRAÇÃO
começou — não desde que a pessoa efetivamente logou. Numa noite com mais de
uma tentativa (uma rodada fracassada, depois outra), o login pode ter
acontecido bem antes da rodada que finalmente rodou, fazendo a sessão parecer
mais "nova" do que realmente estava. Isso pode (ainda não confirmado) explicar
por que o PJe expirou aos 22 minutos quando historicamente aguentava 40+.
