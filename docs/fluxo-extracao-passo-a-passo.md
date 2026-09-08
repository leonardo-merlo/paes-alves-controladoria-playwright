# O que acontece, do clique ao resultado — passo a passo completo

Escrito em 08/09/2026, depois de um dia com três incidentes na mesma rodada
(botão travado, Chrome caiu no meio, eProc TJMG não abriu). Existe pra responder
uma pergunta: **quando algo dá errado, em que ponto exato do processo isso
aconteceu, e o que fica registrado sobre isso?**

Cobre o fluxo atual (os dois botões: "Abrir sistemas" e "Iniciar extração").
Não cobre o modo antigo de um clique só (`iniciar`), que ainda existe no código
por compatibilidade mas não é o que o painel usa.

Cada passo diz: o que acontece → o que pode dar errado ali → o que fica
registrado quando dá errado (ou a falta disso).

---

## Parte 1 — "Abrir sistemas" (primeiro botão)

**1.1 — Pergunta ao banco quais processos estão esperando.**
Lê a tabela de processos e separa os que estão com status "pendente", "erro do
navegador" ou "captcha bloqueado". É a fila do dia.

**1.2 — Descobre que sistemas essa fila precisa** (PJe, eProc TJMG, eProc TRF6,
RUPE...) e a URL de entrada de cada um.
*Se a fila estiver vazia*: para aqui, mensagem "Nenhum processo pendente".

**1.3 — Confere se o Chrome já está de pé** (um ping simples na porta de
depuração, 2 segundos de prazo).

**1.4a — Se o Chrome JÁ estava aberto:** para cada sistema que a fila precisa,
olha as abas já abertas e procura se o endereço de alguma delas contém o
endereço daquele sistema. Achou → reaproveita a aba, não mexe nela. Não achou →
manda o Chrome abrir uma aba nova para aquele sistema, por um pedido HTTP com
**5 segundos de prazo**.

> ⚠️ **Aqui mora um buraco.** Se esse pedido falhar (Chrome ocupado no
> instante, rede engasgada), a única coisa que acontece é um aviso na janela
> preta do agente — que ninguém fica olhando. **Não existe checagem de "a aba
> realmente abriu e carregou".** O sistema segue como se tivesse dado certo.

**1.4b — Se o Chrome NÃO estava aberto:** abre o Chrome do zero, já passando
todas as URLs necessárias de uma vez, e espera até **15 segundos** ele responder
à porta de depuração.
*Se não responder nesse tempo*: para aqui, mensagem "Não foi possível abrir o
navegador".

**1.5 — Escreve no painel: "Abri [lista de sistemas]. Faça login e clique em
Iniciar extração."**

> ⚠️ **Mesmo buraco do 1.4a, na mensagem final.** Essa frase é montada a partir
> da lista de sistemas que a fila PRECISAVA — não da lista de sistemas cuja aba
> de fato abriu. Um sistema pode aparecer nessa frase mesmo se a abertura dele
> tiver falhado silenciosamente no passo 1.4a.

**O que este botão NÃO faz:** não espera login, não confere se alguém está
logado em nada. É só "deixar a porta aberta". Quem loga é a pessoa, no tempo
dela.

**Timeout novo (08/09/2026):** desde hoje, se o botão "Abrir sistemas" como um
todo não terminar em **3 minutos** (180s), ele para sozinho e escreve um erro
de verdade em vez de ficar mudo pra sempre. Isso resolve o travamento em
silêncio, mas não resolve o buraco do 1.4a — uma aba pode falhar individualmente
sem que o passo inteiro estoure esse teto.

---

## Parte 2 — "Iniciar extração" (segundo botão)

Aqui a extração assume que o login já foi feito. Não vai checar de novo se o
Chrome está de pé nem vai reabrir abas — trabalha com o que já está lá.

### 2.1 — A ordem dos sistemas

A fila é dividida por sistema e processada **um sistema de cada vez, na
sequência**, nunca em paralelo. A ordem é fixa e pensada pela duração da
sessão de cada um:

1. RUPE (a sessão dele cai primeiro)
2. eProc TJMG
3. eProc TRF6 (1ª e 2ª instância)
4. tudo o mais na ordem em que chegou
5. **PJe por último** — é o que, historicamente, aguenta esperar mais

**Consequência direta:** o sistema no fim da fila só começa depois que TODOS os
anteriores terminaram, sejam eles rápidos ou não. Se o RUPE demorar 26 minutos
(ele é lento, isso já é conhecido — ver dívida técnica), o eProc TJMG só começa
depois desses 26 minutos, e o PJe só depois disso.

### 2.2 — Para cada sistema: tira uma "foto" das abas que já existem

Antes de mexer em qualquer processo daquele sistema, o código anota quais abas
o Chrome tem NAQUELE momento. Serve só para no final saber quais abas o
PRÓPRIO sistema abriu durante o trabalho dele (documentos, por exemplo), para
poder fechá-las depois — não serve para verificar se a aba principal do
sistema existe.

### 2.3 — Para cada processo (CNJ) da fila daquele sistema, em ordem:

**2.3.1 — Chama o extrator daquele sistema, passando o número do processo.**
O relógio começa a contar aqui — TUDO que acontece a seguir é cronometrado, dá
certo ou dá errado.

**2.3.2 — O extrator conecta ao Chrome** (Playwright, não o pedido HTTP simples
do passo 1). Prazo: **180 segundos (3 minutos)** por tentativa — é o padrão da
ferramenta, não foi escolhido a dedo.
*Se não conseguir conectar*: erro "não foi possível conectar ao Chrome via
CDP". Isso conta como sinal de "o Chrome pode estar morto" (ver 2.4).

**2.3.3 — Procura, entre as abas abertas, uma cujo endereço contenha o domínio
daquele sistema** (por exemplo, `eproc1g.tjmg.jus.br`). Se achar mais de uma
aba do mesmo sistema, prefere a que tem o campo de busca visível na tela — sinal
de que é o painel principal, não uma aba de documento.
*Se não achar NENHUMA aba com esse domínio*: erro **"Nenhuma aba encontrada"**.
Este é exatamente o erro de hoje com o eProc TJMG.

> Este passo não sabe dizer a diferença entre duas histórias bem diferentes:
> **"essa aba nunca chegou a abrir"** (falha no passo 1.4a) e **"a aba abriu,
> mas sumiu ou navegou para outro lugar no meio do caminho"**. As duas terminam
> na mesma frase de erro.

**2.3.4 — Confere se a sessão está logada.** Cada sistema tem seu próprio jeito
de checar isso, porque cada site de tribunal é diferente:
- **eProc**: olha o texto e o endereço da página atual, procurando frases como
  "Entrar no Sistema" ou "sessão foi encerrada". Não navega — lê o que já está
  na tela.
- **PJe**: **navega** de propósito para a página de consulta antes de checar,
  espera 2 segundos, e olha se caiu numa tela de login ou se aparece um campo
  de senha visível.
- **RUPE**: também navega, mas de um jeito tolerante — se a navegação demorar
  ou não completar (o RUPE é lento), isso **não** é tratado como sessão caída;
  quem decide é o que está desenhado na tela no final, não se o carregamento
  "terminou" a tempo.
*Se detectar deslogado*: erro "sessão expirada".

**2.3.5 — Se está logado: pesquisa o número do processo** no campo de busca do
sistema.

**2.3.6 — Lê a lista de eventos/documentos** daquele processo na tela.

**2.3.7 — Baixa o conteúdo de cada documento.** No eProc, isso é feito sem
trocar de página (por um pedido direto de dentro da própria aba) — porque
navegar para o documento derruba a sessão do eProc. PJe e RUPE têm sua própria
forma.

**2.3.8 — Manda o conteúdo para o Claude analisar** e sugerir prazo, status e
próxima ação.

**2.3.9 — Grava o resultado no banco:**
- Deu tudo certo → status "processado" + o rascunho da análise.
- Algum passo acima falhou → status "erro do navegador" + o texto do erro.
- **Em qualquer um dos dois casos, o tempo total gasto nesse processo é
  gravado** (isso já existe — é o único dado de tempo por evento que o sistema
  guarda hoje).

**2.3.10 — Limpa as abas extras** que esse processo específico deixou para
trás (abas de documento, por exemplo), usando três regras: só o que apareceu
depois da "foto" do passo 2.2, só do tipo página (não conta aba invisível de
sistema), só endereço de tribunal (`.jus.br`) — pra nunca fechar algo que a
pessoa tinha aberto por conta própria.

### 2.4 — Depois de cada processo, duas perguntas de segurança

**"Foi erro de não conseguir falar com o Chrome?"** (o erro do passo 2.3.2)
- Faz um ping simples e barato na porta do Chrome.
  - Chrome nem responde a isso → **para a rodada inteira agora**, todo processo
    que ainda não foi tentado (desse sistema e de todos os seguintes) volta pra
    fila com o motivo "Chrome parou de responder".
  - Chrome responde ao ping, só essa conexão específica falhou → tolera, soma
    uma falha. Na **2ª falha desse tipo**, mesmo com o Chrome respondendo ao
    ping, desiste da mesma forma.

**"Foi erro de sessão caída ou nenhuma aba?"** (os erros dos passos 2.3.3 e
2.3.4)
- Se foi o **primeiro** processo desse sistema na fila: decide o texto do
  motivo por uma regra baseada em **quantos minutos a rodada já está rodando**
  (não quantos minutos fazem desde o login):
  - Erro foi "nenhuma aba" → motivo é sempre "o sistema não estava aberto".
  - Rodada com 10 minutos ou mais → motivo é "a sessão envelheceu esperando a
    vez".
  - Rodada com menos de 10 minutos → motivo é "login ainda não estava feito".
  - **Devolve TODOS os processos desse sistema para a fila sem tentar mais
    nenhum**, e pula pro próximo sistema.
- Se não foi o primeiro (algum já tinha dado certo antes): considera que a
  sessão caiu no meio, devolve o resto para a fila com "sessão caiu durante a
  rodada", e pula pro próximo sistema.

### 2.5 — Quando a rodada inteira termina

Soma tudo: quantos processados, quantos com erro, quantos devolvidos sem
tentar. Monta uma frase única pro painel:

- Se **nenhum** processo deu certo: tenta explicar a causa mais comum entre os
  erros — mas só reconhece um conjunto FIXO de frases já catalogadas
  (certificado digital, processo não encontrado, sistema sem extrator, etc.).
  **Se o erro não bater com nenhuma dessas frases conhecidas, a mensagem cai de
  volta em "Login não concluído? Verifique."** — mesmo que a causa real seja
  outra coisa completamente (foi o que aconteceu quando o eProc TJMG deu
  "Nenhuma aba" combinado com uma falha nova do RUPE que a lista não conhecia).
- Se algum deu certo: "X processado(s), Y com erro. Z de volta na fila."

---

## Todos os prazos que existem hoje, e o que cada um mede

| Prazo | Quanto | Mede a partir de quando | Onde |
|---|---|---|---|
| Conectar ao Chrome (por processo) | 180s | do início daquela tentativa | dentro de cada extrator |
| Abrir uma aba nova | 5s | do pedido HTTP | "Abrir sistemas", passo 1.4a |
| Chrome responder à porta, ao abrir do zero | 15s (30 tentativas de 0,5s) | do Chrome ter sido lançado | "Abrir sistemas", passo 1.4b |
| Botão "Abrir sistemas" travar | 180s | do clique | novo, 08/09/2026 |
| Tolerância a falha de conexão | 2 falhas | acumulado na rodada | passo 2.4 |
| "Sessão envelheceu" vs "login não feito" | 10 min | **do início da rodada de extração** (não do login!) | passo 2.4 |
| Comando considerado abandonado | 90 min | da última atualização do comando | painel + agente |

**O ponto mais importante desta tabela:** o único prazo que decide "a sessão
envelheceu" mede o tempo **desde que a extração começou a rodar** — não desde
que a pessoa efetivamente digitou a senha. Se o login foi feito bem antes (por
exemplo, numa tentativa anterior que falhou rápido), o sistema não tem como
saber disso, e o número que ele usa pode estar bem abaixo do tempo real de vida
da sessão.

---

## O que NÃO fica registrado hoje (as lacunas de verdade)

1. **O momento do login.** Só existe "quando a rodada começou". Nunca "quando a
   pessoa autenticou".
2. **Se uma aba realmente abriu e carregou.** O sistema sabe que PEDIU pra
   abrir. Não sabe se deu certo, até 24 minutos depois (quando a extração
   finalmente tenta usar aquela aba).
3. **A diferença entre "aba nunca existiu" e "aba existiu e sumiu".** Os dois
   casos geram o mesmo erro ("Nenhuma aba").
4. **Uma linha de log por tentativa.** Hoje só existe o resultado FINAL de cada
   processo (deu certo / deu erro / motivo). Não existe: "às 20:25:07 tentei
   achar aba do eProc TJMG, não achei, desisti do sistema inteiro". Essa
   sequência, hoje, só dá pra reconstruir de forma indireta, cruzando horários
   de outras tabelas — foi assim que reconstruímos o que aconteceu com o eProc
   TJMG hoje, e levou uma investigação inteira para chegar lá.
5. **Login detectado ≠ login confirmado por sistema, num só lugar.** Cada
   sistema tem seu próprio jeito de checar sessão (ler a página parada, navegar
   e olhar o resultado, navegar de forma tolerante a demora) — três lógicas
   diferentes, cada uma podendo ter seu próprio ponto cego, e hoje nenhuma
   delas é testada contra uma aba de verdade, só contra conteúdo de página
   simulado.

## Por que não existe teste automatizado pra essas lacunas

Os testes que já existem (`test_runner.py`, `test_sistema_auth.py`) cobrem bem
duas coisas: contas e decisões puras (que motivo escrever, que ordem seguir,
quanto tempo durou) e a leitura de uma página **já dada como certa** (um texto
de exemplo, fingindo ser o HTML da tela). Nenhum teste hoje aciona de verdade o
pedido HTTP que abre uma aba no Chrome, nem a busca por "qual aba tem esse
domínio" — porque isso depende de um Chrome de verdade (ou de fingir um
inteiro, o que ninguém construiu ainda). É por isso que esse ponto específico —
abrir a aba e confirmar que abriu — ficou sem teste até hoje: não é que ele
seja menos importante, é que testá-lo exige montar uma peça que não existe no
projeto ainda.
