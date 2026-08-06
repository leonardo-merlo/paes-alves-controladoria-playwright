# Spec — Métricas de eficiência no painel da controladoria

Data: 2026-08-06 · Autor: Leonardo + Claude · Status: aprovado no desenho, sem implementação

## Objetivo

Mostrar, no topo do dashboard, números que respondam "essa automação está
funcionando e quanto ela custa": taxa de extração, fila de aprovação, custo e
tempo por processo. Hoje o painel mostra o detalhe (linha a linha, dia a dia) e
não mostra o agregado.

Dois dos quatro números **não existem no banco** e precisam passar a ser gravados.

## Repositórios envolvidos

- **Agente** — `controladoria-playwright` (`master`). Grava custo e tempo.
- **Painel** — pasta `paes-alves-controladoria`, repo GitHub `ia-controladoria-advocacia`
  (`main`). Mostra os números. **Push para `main` = deploy automático na Vercel.**
- **Banco** — Supabase produção `hjesbvnxeivphplfymml`. Uma migração.

## Decisões tomadas

| Decisão | Escolha | Por quê |
|---|---|---|
| O que é "sucesso" | extraiu sem erro | "Aguardando aprovação" cai a zero conforme o Henrique aprova — anunciaria 0% justamente quando o fluxo funcionou |
| Aguardando aprovação | contagem, não % | é fila de trabalho, não indicador de qualidade |
| Recorte | segue o filtro de mês | dois números na mesma tela contando períodos diferentes se contradizem |
| Moeda | dólar | o câmbio está cravado no código e envelhece; dólar é o valor exato |
| `ignorado` | fora da taxa, em rodapé | não é o robô falhando — é CNJ que ninguém sabe rotear |
| Custo/tempo | gravar agora | só mede daqui pra frente; quanto antes começar, antes há histórico |

## Parte 1 — Passar a gravar custo e tempo

### Migração

```sql
alter table rascunhos
  add column tokens_entrada integer,
  add column tokens_saida   integer,
  add column custo_usd      numeric(10,6);

alter table processos
  add column duracao_extracao_s integer;
```

Todas anuláveis. Os 158 processos existentes ficam com `null` **para sempre** — não
há como reconstruir o custo de uma chamada já feita. Isso não é limitação temporária,
é permanente, e a interface precisa refletir.

### Agente

**`analyzer.py`** — hoje o custo nasce e morre dentro de um `print` (linha ~262):

```python
custo_usd = (u.input_tokens / 1_000_000 * 1) + (u.output_tokens / 1_000_000 * 5)
print(f"... custo: USD {custo_usd:.4f} (~R$ {custo_usd*5.7:.2f})")
```

Os preços por milhão de token viram constantes nomeadas no topo do módulo (hoje são
números mágicos dentro de uma f-string) e `analisar_processo` passa a devolver
`tokens_entrada`, `tokens_saida` e `custo_usd` no dicionário de resultado. O `print`
continua — é o que o operador lê no terminal.

**`supabase_writer._upsert_rascunho`** — grava os três campos quando presentes.

**`runner.processar_cnj`** — cronometra do início da extração até o fim da gravação e
devolve `duracao_extracao_s`; `marcar_supabase` grava no processo. Medir **todas** as
tentativas, inclusive as que falham: o tempo gasto num processo que deu erro é tempo
real. O recorte de quais entram na média é decisão da interface, não da coleta.

### Testes (agente)

O agente tem suíte própria, sem pytest, no estilo `test_*.py` com `assert` e `print`.
Entram testes para: cálculo de custo a partir de contagens de token conhecidas, e o
resultado do analyzer carregando os campos novos. Rodar os três arquivos antes e
depois — hoje são 40 testes.

## Parte 2 — Mostrar no painel

### Onde

Componente novo `app/dashboard/MetricasResumo.tsx`, renderizado por
`EntradasPorDia.tsx` **acima** do "Filtrar por mês", recebendo a lista **já filtrada**
— assim acompanha o filtro sem lógica de sincronização.

### Os quatro números

| Número | Definição |
|---|---|
| **Taxa de extração** | `processado ÷ (processado + erros)`. `erros` = `pje_status` começando com `erro_` ou `captcha_bloqueado`, mesma regra que `agruparPorDia` já usa. `pendente` e `ignorado` ficam fora do numerador e do denominador |
| **Aguardando aprovação** | contagem de processos `processado` com rascunho `status='pendente'` |
| **Custo** | soma do período em destaque, e média por processo ao lado. Só processos que extraíram com sucesso e têm `custo_usd` preenchido |
| **Tempo** | média de `duracao_extracao_s`, mesmo recorte |

Rodapé: `N sem sistema identificado` quando houver `ignorado`.

Ao lado das médias, sempre `média de N processos`. Sem isso o número não é
interpretável: um processo de 84 documentos custa dezenas de vezes mais que um de 1,
e a média de um mês com um processo gordo não se parece com a de um mês sem.

**Quando não houver dado, mostrar `—`, nunca `US$ 0,00`.** Zero é uma afirmação falsa
sobre um período que simplesmente não foi medido. Meses anteriores a esta mudança vão
cair nesse caso.

### Definições compartilhadas

`agruparPorDia` já classifica extraído / aguardando aprovação / erro / pendente. As
definições saem para funções puras exportadas (ex.: `classificarStatus`,
`resolverDataAgrupamento` já existe) e passam a ser usadas nos dois lugares. Escrever
contas novas em paralelo faria os números de cima discordarem da tabela de baixo na
mesma tela.

### Consultas

`app/dashboard/page.tsx` hoje faz duas consultas. As duas mudam:

- `fetchEntradas` — inclui `duracao_extracao_s` no select.
- `fetchPendingProcessoIds` — passa a trazer `processo_id, status, custo_usd` e a
  devolver duas coisas: o conjunto de pendentes (como hoje) e o custo por processo.
  Continua sendo **uma** consulta.

## Correções que entram junto

Três defeitos existentes que a mudança encosta. Corrigir agora é mais barato que
explicar depois por que os números não fecham.

**1. Teto de 200 (`app/dashboard/page.tsx`).** `fetchEntradas` tem `.limit(200)`. Com
164 processos vem tudo; passando de 200 o banco devolve os mais recentes e cala sobre
o resto — a taxa passaria a descrever uma amostra se apresentando como total.

Só tirar o `.limit` **não resolve**: o PostgREST tem teto próprio de 1000 linhas por
resposta. A solução é buscar por páginas com `.range()` até a página vir incompleta.
Com centenas de processos é uma requisição só; o laço existe para o dia em que não for.

**2. Selo "Duplicata" errado (`app/entradas/[data]/ProcessosList.tsx:16`).** O status
`ignorado` recebe o rótulo "Duplicata". Os 3 processos nesse status hoje têm
`duplicata = false` e motivo "Sistema não implementado" — o selo mente. O rótulo
nasceu quando `ignorado` só servia para duplicata; o uso cresceu e o rótulo não.
Passa a ser derivado: `duplicata = true` → "Duplicata"; senão → "Sem sistema".

**3. `ignorado` some das colunas (`agruparPorDia`).** Ele entra em `total` e em nenhuma
das parcelas, então total ≠ soma das colunas. Passa a ter contagem própria.

## Fora de escopo

- Gráfico ou série temporal das métricas — número no topo primeiro; se virar pergunta
  recorrente, aí se justifica.
- Reconstruir custo histórico — impossível, não é decisão.
- Custo do modelo por processo em real — decidido em dólar.
- Runner de testes no painel: o projeto tem só `lint` e `build`, e adicionar
  dependência exige aprovação do Leonardo. As contas ficam em funções puras
  exportadas, prontas para teste no dia em que houver runner.

## Riscos

**A média engana em volume baixo.** Um mês com 3 processos, um deles gigante, produz
uma média que não descreve nada. Mitigado pelo "média de N", não resolvido.

**O agente é o que acabou de ser validado.** As mudanças no `analyzer` e no `runner`
mexem no caminho crítico da extração. Rodar os 40 testes antes e depois, e validar
numa extração real antes de mandar para a máquina do Henrique.

**Deploy do painel é automático.** Chegou no `main`, está no ar. Confirmação explícita
do Leonardo antes do push, sempre.

## Como validar

1. Suíte do agente: 40 testes antes, 40+ depois, todos passando.
2. Migração aplicada e conferida com `select` das colunas novas.
3. Uma extração real: conferir que `custo_usd` e `duracao_extracao_s` chegaram
   preenchidos nos processos daquela rodada, e vazios nos antigos.
4. Painel local (`npm run dev`): taxa e contagem batendo com a tabela de baixo;
   trocar o filtro de mês e ver os números acompanharem; um mês antigo mostrando `—`
   e não zero.
5. `npm run build` e `npm run lint` limpos antes de qualquer push.
