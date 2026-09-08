# Consultas para diagnosticar uma rodada

Cole no SQL Editor do Supabase. Escrito para responder, em segundos, as
perguntas que em 08/09/2026 custaram uma investigação inteira.

A tabela é `eventos_extracao`. Uma linha por etapa, gravada pelo agente
enquanto roda. O mesmo conteúdo também vai para `logs/agente-AAAA-MM-DD.log`
na máquina onde a extração rodou.

---

## 1. A rodada inteira, do clique ao resumo

A consulta principal. Mostra tudo em ordem.

```sql
select momento::time(0) as hora, etapa, sistema, numero_cnj,
       case when ok then '' else 'FALHA' end as falhou,
       detalhe
from eventos_extracao
where momento > now() - interval '3 hours'
order by momento;
```

Trocar `3 hours` pelo período que interessa. Para uma rodada específica, use o
`comando_id` (ver consulta 6).

## 2. Só o que deu errado

Quando a rodada foi longa e você quer ir direto ao ponto.

```sql
select momento::time(0) as hora, etapa, sistema, numero_cnj, detalhe
from eventos_extracao
where not ok and momento > now() - interval '1 day'
order by momento desc;
```

## 3. O estado de cada sistema ANTES de começar (pré-voo)

Responde "o eProc TJMG estava aberto ou não?" **no minuto zero**, em vez de
descobrir 26 minutos depois.

```sql
select momento::time(0) as hora, sistema,
       case when ok then 'tinha aba' else 'SEM ABA' end as aba,
       detalhe
from eventos_extracao
where etapa in ('previvo.inicio', 'previvo.sistema')
  and momento > now() - interval '1 day'
order by momento;
```

## 4. Quanto tempo cada sistema levou

Responde "por que o RUPE demora tanto" e "quando chegou a vez do PJe" com
número, não com palpite.

```sql
select sistema,
       min(momento)::time(0) as comecou,
       max(momento)::time(0) as terminou,
       round(extract(epoch from (max(momento) - min(momento)))/60, 1) as minutos,
       count(*) filter (where etapa = 'cnj.fim' and ok)     as processados,
       count(*) filter (where etapa = 'cnj.fim' and not ok) as com_erro
from eventos_extracao
where sistema is not null and momento > now() - interval '1 day'
group by sistema
order by comecou;
```

## 5. O que estava aberto no Chrome quando falhou

**A consulta que teria respondido a pergunta de 08/09 em dois segundos.**

```sql
select momento::time(0) as hora, sistema, numero_cnj, detalhe
from eventos_extracao
where etapa in ('cnj.ambiente', 'abrir.fim', 'abrir.aba_confirmada')
  and not ok
  and momento > now() - interval '1 day'
order by momento desc;
```

## 6. Ligar os eventos ao clique no painel

```sql
select c.acao, c.status, c.criado_em::time(0) as clicou,
       count(e.id) as eventos,
       count(e.id) filter (where not e.ok) as falhas
from comandos c
left join eventos_extracao e on e.comando_id = c.id
where c.criado_em > now() - interval '1 day'
group by c.id, c.acao, c.status, c.criado_em
order by c.criado_em desc;
```

## 7. Tempo por processo, do mais lento para o mais rápido

```sql
select sistema, numero_cnj,
       (dados->>'duracao_s')::int as segundos,
       case when ok then 'ok' else 'erro' end as desfecho, detalhe
from eventos_extracao
where etapa = 'cnj.fim' and dados->>'duracao_s' is not null
  and momento > now() - interval '1 day'
order by segundos desc nulls last
limit 20;
```

---

## Como ler as etapas

| Etapa | O que significa |
|---|---|
| `abrir.inicio` / `abrir.fila` | clicou em Abrir sistemas; que sistemas a fila exige |
| `abrir.chrome` | o Chrome já estava de pé ou foi aberto do zero |
| `abrir.aba_reaproveitada` | já havia aba desse sistema, não mexeu |
| `abrir.aba_pedida` | pediu ao Chrome para abrir; `FALHA` = o Chrome recusou o pedido |
| `abrir.aba_confirmada` | **conferiu se a aba existe mesmo**; `FALHA` = pediu, aceitou, e não está lá |
| `abrir.fim` | resultado do Abrir sistemas, com quem ficou faltando |
| `previvo.inicio` / `previvo.sistema` | estado de cada sistema antes de processar qualquer coisa |
| `sistema.inicio` / `sistema.fim` | começo e fim da fila de um sistema, com o minuto da rodada |
| `cnj.fim` | desfecho de um processo, com duração |
| `cnj.ambiente` | **só em falha**: as abas abertas no instante exato do erro |
| `cnj.falha_cdp` | não conseguiu falar com o Chrome; diz se o Chrome respondeu ao ping simples |
| `sistema.sem_sessao` | falhou no primeiro processo do sistema e devolveu a fila inteira |
| `rodada.abortada` | o Chrome morreu e a rodada inteira parou |
| `extrair.fim` | resumo final |
| `comando.excecao` | o comando estourou com erro não previsto |
