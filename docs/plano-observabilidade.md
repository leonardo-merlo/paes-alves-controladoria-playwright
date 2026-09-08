# Plano — observabilidade da extração

Escrito em 08/09/2026. Objetivo único e concreto: **amanhã, rodando o sistema,
o Leonardo consegue dizer exatamente em que etapa o problema aconteceu e por
quê — com uma consulta, sem reconstruir por inferência.**

Hoje isso não é possível. A investigação do "eProc TJMG não estava aberto"
levou uma sessão inteira e terminou numa conclusão provável, não certa, porque
o sistema não registra o que fez — só o que sobrou no fim.

---

## A ideia central

Toda etapa que hoje só existe na cabeça do código passa a deixar **uma linha
registrada**, com hora, sistema, processo, se deu certo, e o que aconteceu.

Duas saídas, sempre as duas:
- **Tabela `eventos_extracao` no Supabase** — para o Leonardo consultar de
  qualquer lugar, inclusive da máquina do Henrique sem estar nela. É a saída
  que importa: foi assim que ele passou o dia inteiro investigando.
- **Arquivo de log local** — de graça, porque o agente já manda tudo que
  imprime para `logs/agente-AAAA-MM-DD.log`. Serve quando o Supabase está fora
  do ar.

Falha ao registrar **nunca** derruba a rodada. Registro é testemunha, não juiz.

---

## As três mudanças

### 1. Registro por evento (o grosso)

Uma linha por etapa, nos dois fluxos. As etapas, na ordem em que acontecem:

**Abrir sistemas**
- `abrir.inicio` — clicou; quantos processos na fila
- `abrir.fila` — quais sistemas a fila exige
- `abrir.chrome` — Chrome já estava de pé? quantas abas tinha?
- `abrir.aba_reaproveitada` — por sistema: já havia aba, não mexeu
- `abrir.aba_pedida` — por sistema: pediu para abrir; o pedido foi aceito?
- `abrir.aba_confirmada` — **novo**: depois de pedir, conferiu se a aba existe
  de verdade. Esta checagem não existe hoje — é o buraco que escondeu o eProc
  TJMG por 24 minutos.
- `abrir.fim` — quais sistemas ficaram confirmados, quais falharam

**Extração**
- `extrair.inicio` — fila total, ordem em que os sistemas vão rodar
- `previvo.sistema` — **novo**: antes de processar qualquer coisa, passa por
  todos os sistemas da fila e registra: tem aba? a sessão está viva? Custa
  segundos e responde, no minuto zero, a pergunta que hoje só aparece 26
  minutos depois.
- `sistema.inicio` — sistema, quantos CNJs, em que minuto da rodada começou
- `cnj.fim` — por processo: desfecho, duração, e o erro quando houver
- `cnj.ambiente` — **novo, só quando dá erro**: a lista de abas abertas no
  instante exato da falha. É a linha que teria respondido "o eProc TJMG não
  abriu" em dois segundos.
- `sistema.fim` — desfecho do sistema, quantos ok/erro/devolvidos
- `extrair.fim` — resumo da rodada

### 2. Pré-voo antes de extrair

Antes do primeiro processo, varre todos os sistemas da fila e registra o estado
de cada um: aba presente, sessão viva. Não aborta nada, não muda decisão
nenhuma — só registra. Três ganhos:

- Descobre o sistema sem aba **no minuto zero**, não no minuto 26.
- Cria um marco temporal do login: "às 20:03, PJe estava logado". Hoje a regra
  de "sessão envelheceu" mede o tempo desde o início da rodada, que não é a
  mesma coisa que o tempo desde o login. Com o pré-voo, passa a existir um
  instante real de referência.
- O resumo final pode dizer "eProc TJMG não estava aberto desde o começo" em
  vez de culpar o login.

### 3. ~~Domínio do sistema num lugar só~~ — cancelado, a premissa era falsa

Eu tinha anotado que o endereço do sistema era comparado de dois jeitos
diferentes (URL completa de um lado, domínio puro do outro), e que isso poderia
fazer um lado achar a aba e o outro não. **Fui conferir e está errado**:
`SISTEMA_HOST` já guarda domínio puro (`eproc1g.tjmg.jus.br`), e é esse mesmo
valor que os dois lados usam. Não há inconsistência para corrigir. Fica
registrado para ninguém "consertar" isso depois achando que é bug.

---

## Critérios de sucesso

Cada um verificável, sem depender de opinião:

1. **Uma consulta responde "o que aconteceu na rodada de hoje"** — um `SELECT`
   em `eventos_extracao` ordenado por hora mostra a rodada inteira, do clique
   ao resumo, sem cruzar com outra tabela.
2. **Quando um sistema não tem aba, existe uma linha mostrando quais abas
   estavam abertas naquele instante** — a pergunta de hoje ("mas por que não
   estava aberto?") passa a ter resposta em texto, não em dedução.
3. **Existe uma linha de pré-voo por sistema, antes de qualquer processamento**,
   dizendo se tinha aba e se a sessão estava viva.
4. **Dá para dizer em que minuto cada sistema começou e terminou** por consulta,
   sem cruzar horários de tabelas diferentes.
5. **Falha ao registrar não derruba a rodada** — Supabase fora do ar, disco
   cheio, o que for: a extração continua e o log local ainda recebe.
6. **Nenhum comportamento de extração muda** — mesmos status, mesmos motivos,
   mesma ordem, mesmas decisões. Só passa a existir registro.
7. **Os testes existentes continuam passando**, e as funções novas puras têm
   teste.

### Conferindo os critérios contra as perguntas reais

As perguntas que ficaram sem resposta hoje, e qual critério cobre cada uma:

| Pergunta de hoje | Coberta por |
|---|---|
| Por que o eProc TJMG não abriu? | 2 e 3 |
| A aba nunca existiu ou existiu e sumiu? | 2 e 3 (pré-voo distingue os dois) |
| Em que momento a extração parou de funcionar? | 1 e 4 |
| O login tinha sido feito mesmo? | 3 |
| Por que o PJe caiu em 22 min se aguentava 40? | 3 (marco real de login) + 4 |
| Por que o RUPE demora tanto? | 4 (tempo por sistema e por processo) |
| Deu erro — mas erro de quê, exatamente? | 1 e 2 |

Uma pergunta que **não** fica coberta, e é honesto dizer: *"por que o pedido de
abrir a aba falhou?"* — o Chrome responde só sim ou não a esse pedido. O que
passa a existir é saber **que** falhou, na hora, em vez de descobrir 24 minutos
depois. A causa dentro do Chrome continua fora do alcance.

---

## O que este plano NÃO faz

- Não muda a ordem dos sistemas, nem tempos, nem regra de decisão nenhuma.
- Não resolve o paralelismo (rodada longa demais) — é outro assunto, e agora
  vai ter dado de tempo real por sistema para decidir com número, não com
  palpite.
- Não conserta o eProc TJMG. Faz o problema ser visível no minuto zero, o que
  é o passo que faltava para poder consertar.
