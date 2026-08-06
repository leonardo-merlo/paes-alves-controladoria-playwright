# Métricas de eficiência — Parte 1: coleta (agente + banco)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o agente gravar no banco o custo em dólar e a duração de cada processo — números que hoje ele calcula e joga fora.

**Architecture:** Três mudanças pequenas em cadeia. O `analyzer.py` passa a devolver tokens e custo em vez de só imprimir; o `supabase_writer.py` grava esses campos no rascunho; o `runner.py` cronometra cada CNJ e grava a duração no processo. As contas saem para funções puras, testáveis sem rede e sem banco. Uma migração adiciona quatro colunas anuláveis.

**Tech Stack:** Python 3 · Playwright · supabase-py · Anthropic SDK · suíte de testes caseira (`test_*.py` com `assert` e `print`, sem pytest)

**Spec:** `docs/superpowers/specs/2026-08-06-metricas-eficiencia-painel-design.md`

---

## Antes de começar — ambiente

O interpretador é o do venv da pasta principal. **`python` puro no PATH cai no stub da
Microsoft Store e falha com exit 49.**

```bash
C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/venv/Scripts/python.exe
```

O código a editar está no worktree:

```
C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b
```

O `.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`) existe **só na
pasta principal** — é gitignored e não está no worktree. Testes de função pura rodam
de qualquer lugar; qualquer coisa que fale com o banco precisa rodar com a pasta
principal como diretório de trabalho.

Linha de base antes de tocar em nada — **40 testes, todos passando**:

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && for t in test_runner.py test_sistema_auth.py test_agente.py; do ../../../venv/Scripts/python.exe $t; done
```

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `analyzer.py` | calcular custo e devolvê-lo junto da análise | modificar |
| `test_analyzer.py` | provar o cálculo de custo sem chamar a API | **criar** |
| `supabase_writer.py` | montar e gravar a linha de rascunho | modificar |
| `test_supabase_writer.py` | provar a montagem da linha sem banco | **criar** |
| `runner.py` | cronometrar cada CNJ e gravar a duração | modificar |
| `test_runner.py` | ganha o teste da conta de duração | modificar |

Duas funções puras novas carregam toda a lógica testável: `calcular_custo_usd` e
`duracao_segundos`. O resto é fiação.

---

### Task 1: Preço vira constante nomeada e custo vira função pura

Hoje o custo nasce e morre dentro de um `print` (`analyzer.py`, ~linha 262), com os
preços por milhão de token como números soltos no meio da conta:

```python
custo_usd = (u.input_tokens / 1_000_000 * 1) + (u.output_tokens / 1_000_000 * 5)
```

**Files:**
- Create: `test_analyzer.py`
- Modify: `analyzer.py` (constantes junto de `MODEL`, ~linha 28; função nova antes de `analisar_processo`)

- [ ] **Step 1: Escrever o teste que falha**

Criar `test_analyzer.py`:

```python
"""test_analyzer.py — testes do cálculo de custo. Rodar: python test_analyzer.py"""

from analyzer import calcular_custo_usd


def test_custo_de_um_milhao_de_tokens_de_cada_lado():
    # 1 milhão de entrada = USD 1,00 · 1 milhão de saída = USD 5,00
    assert calcular_custo_usd(1_000_000, 1_000_000) == 6.0
    print("OK custo_um_milhao")


def test_custo_de_chamada_real_medida_em_05_08_2026():
    # rodada real: 53.891 entrada + 733 saída imprimiu USD 0.0576
    custo = calcular_custo_usd(53_891, 733)
    assert round(custo, 4) == 0.0576
    print("OK custo_chamada_real")


def test_chamada_sem_tokens_custa_zero():
    assert calcular_custo_usd(0, 0) == 0.0
    print("OK custo_zero")


if __name__ == "__main__":
    test_custo_de_um_milhao_de_tokens_de_cada_lado()
    test_custo_de_chamada_real_medida_em_05_08_2026()
    test_chamada_sem_tokens_custa_zero()
    print("Todos os testes passaram.")
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_analyzer.py
```

Esperado: `ImportError: cannot import name 'calcular_custo_usd' from 'analyzer'`

- [ ] **Step 3: Implementar**

Em `analyzer.py`, logo abaixo de `MODEL = "claude-haiku-4-5-20251001"`:

```python
# Preço do Haiku 4.5 por milhão de tokens, em dólar. Trocar de modelo sem mexer
# aqui faz o custo gravado mentir — os dois andam juntos.
PRECO_ENTRADA_POR_MILHAO_USD = 1.0
PRECO_SAIDA_POR_MILHAO_USD = 5.0
```

E, antes de `def analisar_processo`:

```python
def calcular_custo_usd(tokens_entrada: int, tokens_saida: int) -> float:
    """Custo em dólar de uma chamada. Função pura — ver test_analyzer.py."""
    return (tokens_entrada / 1_000_000 * PRECO_ENTRADA_POR_MILHAO_USD) + (
        tokens_saida / 1_000_000 * PRECO_SAIDA_POR_MILHAO_USD
    )
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_analyzer.py
```

Esperado: 3 linhas `OK` e `Todos os testes passaram.`

- [ ] **Step 5: Commit**

```bash
git add analyzer.py test_analyzer.py && git commit -m "refactor: preco por token vira constante nomeada e custo vira funcao pura"
```

---

### Task 2: A análise passa a carregar tokens e custo

**Files:**
- Modify: `analyzer.py` (função nova + uso dela na ~linha 261)
- Modify: `test_analyzer.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `test_analyzer.py` (e no bloco `__main__`, na ordem em que aparecem):

```python
from analyzer import anexar_uso


def test_anexar_uso_poe_os_tres_campos_na_analise():
    analise = anexar_uso({"status_sugerido": "AGUARDAR"}, 53_891, 733)
    assert analise["tokens_entrada"] == 53_891
    assert analise["tokens_saida"] == 733
    assert round(analise["custo_usd"], 4) == 0.0576
    print("OK anexar_uso")


def test_anexar_uso_preserva_o_que_ja_estava_na_analise():
    analise = anexar_uso({"status_sugerido": "MANIFESTAR"}, 10, 20)
    assert analise["status_sugerido"] == "MANIFESTAR"
    print("OK anexar_uso_preserva")
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_analyzer.py
```

Esperado: `ImportError: cannot import name 'anexar_uso'`

- [ ] **Step 3: Implementar**

Em `analyzer.py`, logo depois de `calcular_custo_usd`:

```python
def anexar_uso(analise: dict, tokens_entrada: int, tokens_saida: int) -> dict:
    """Acrescenta consumo e custo à análise. Função pura — ver test_analyzer.py."""
    analise["tokens_entrada"] = tokens_entrada
    analise["tokens_saida"] = tokens_saida
    analise["custo_usd"] = calcular_custo_usd(tokens_entrada, tokens_saida)
    return analise
```

Substituir estas duas linhas (~261-263):

```python
            u = message.usage
            custo_usd = (u.input_tokens / 1_000_000 * 1) + (u.output_tokens / 1_000_000 * 5)
            print(f"[TOKENS] input: {u.input_tokens:,} | output: {u.output_tokens:,} | total: {u.input_tokens + u.output_tokens:,} | custo: USD {custo_usd:.4f} (~R$ {custo_usd*5.7:.2f})")
            return analise
```

por:

```python
            u = message.usage
            analise = anexar_uso(analise, u.input_tokens, u.output_tokens)
            custo_usd = analise["custo_usd"]
            print(f"[TOKENS] input: {u.input_tokens:,} | output: {u.output_tokens:,} | total: {u.input_tokens + u.output_tokens:,} | custo: USD {custo_usd:.4f} (~R$ {custo_usd*5.7:.2f})")
            return analise
```

O `print` continua igual, inclusive o valor aproximado em real: é o que o operador lê
no terminal. Só o dólar é gravado.

- [ ] **Step 4: Rodar e ver passar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_analyzer.py
```

Esperado: 5 linhas `OK`.

- [ ] **Step 5: Commit**

```bash
git add analyzer.py test_analyzer.py && git commit -m "feat: analise passa a carregar tokens e custo em dolar"
```

---

### Task 3: Migração — quatro colunas anuláveis

**Files:** nenhum arquivo do repo. É mudança no banco de produção `hjesbvnxeivphplfymml`.

- [ ] **Step 1: Mostrar o SQL ao Leonardo e esperar confirmação**

Regra dele: mudança de banco não acontece sem ele ver o SQL antes.

```sql
alter table rascunhos
  add column tokens_entrada integer,
  add column tokens_saida   integer,
  add column custo_usd      numeric(10,6);

alter table processos
  add column duracao_extracao_s integer;
```

Todas anuláveis, nenhuma com valor padrão: as linhas existentes ficam `null` e é assim
que a interface distingue "não medimos" de "custou zero".

- [ ] **Step 2: Aplicar**

Usar `mcp__supabase__apply_migration`, nome `add_metricas_custo_e_duracao`.

- [ ] **Step 3: Conferir que as colunas existem e estão vazias**

```sql
select
  (select count(*) from rascunhos) as rascunhos,
  (select count(custo_usd) from rascunhos) as com_custo,
  (select count(*) from processos) as processos,
  (select count(duracao_extracao_s) from processos) as com_duracao;
```

Esperado: `com_custo = 0` e `com_duracao = 0`. Qualquer outro número significa que a
coluna nasceu preenchida, o que não deveria acontecer.

---

### Task 4: O rascunho grava tokens e custo

Hoje `_upsert_rascunho` monta a linha e grava na mesma função, então a montagem não
tem como ser testada sem banco. A montagem sai para uma função pura.

**Files:**
- Create: `test_supabase_writer.py`
- Modify: `supabase_writer.py:152-194`

- [ ] **Step 1: Escrever o teste que falha**

Criar `test_supabase_writer.py`:

```python
"""test_supabase_writer.py — testes da montagem da linha de rascunho.
Rodar: python test_supabase_writer.py"""

from supabase_writer import _montar_linha_rascunho

QUANDO = "2026-08-06T12:00:00+00:00"


def test_linha_carrega_tokens_e_custo():
    linha = _montar_linha_rascunho(
        "proc-1",
        {"status_sugerido": "AGUARDAR", "tokens_entrada": 53_891,
         "tokens_saida": 733, "custo_usd": 0.0576},
        responsavel_id=None,
        data_extracao=QUANDO,
    )
    assert linha["tokens_entrada"] == 53_891
    assert linha["tokens_saida"] == 733
    assert linha["custo_usd"] == 0.0576
    print("OK linha_com_custo")


def test_analise_antiga_sem_custo_nao_quebra():
    # reanalisar.py e rodadas anteriores produzem análise sem esses campos
    linha = _montar_linha_rascunho(
        "proc-2", {"status_sugerido": "MANIFESTAR"},
        responsavel_id=None, data_extracao=QUANDO,
    )
    assert "custo_usd" not in linha
    assert linha["status_sugerido"] == "MANIFESTAR"
    print("OK linha_sem_custo")


def test_custo_zero_nao_e_descartado_como_ausente():
    # a linha descarta None; zero é medição válida e precisa sobreviver
    linha = _montar_linha_rascunho(
        "proc-3",
        {"status_sugerido": "AGUARDAR", "tokens_entrada": 0,
         "tokens_saida": 0, "custo_usd": 0.0},
        responsavel_id=None, data_extracao=QUANDO,
    )
    assert linha["custo_usd"] == 0.0
    print("OK custo_zero_sobrevive")


if __name__ == "__main__":
    test_linha_carrega_tokens_e_custo()
    test_analise_antiga_sem_custo_nao_quebra()
    test_custo_zero_nao_e_descartado_como_ausente()
    print("Todos os testes passaram.")
```

O terceiro teste existe por causa de uma armadilha real: a função hoje termina com
`{k: v for k, v in data.items() if v is not None}`. Um custo de `0.0` passa nesse
filtro (só `None` é descartado), mas é o tipo de coisa que quebra quando alguém troca
`is not None` por um `if v` distraído.

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_supabase_writer.py
```

Esperado: `ImportError: cannot import name '_montar_linha_rascunho'`

- [ ] **Step 3: Implementar**

Em `supabase_writer.py`, criar a função pura logo **antes** de `_upsert_rascunho`:

```python
def _montar_linha_rascunho(
    processo_id: str, analise: dict, responsavel_id: str | None, data_extracao: str
) -> dict:
    """
    Monta a linha da tabela rascunhos a partir da análise.
    Função pura — ver test_supabase_writer.py. Campos None são descartados, para
    não sobrescrever com nulo o que já estava gravado.
    """
    data = {
        "processo_id":                processo_id,
        "status_sugerido":            analise.get("status_sugerido"),
        "responsavel_sugerido":       analise.get("responsavel_sugerido", ""),
        "responsavel_sugerido_id":    responsavel_id,
        "proxima_acao":               analise.get("proxima_acao"),
        "cenario_prazo":              analise.get("cenario_prazo"),
        "prazo_fatal_dias_uteis":     analise.get("prazo_fatal_dias_uteis"),
        "prazo_interno_dias_uteis":   analise.get("prazo_interno_dias_uteis"),
        "justificativa":              analise.get("justificativa"),
        "alerta":                     analise.get("alerta"),
        "classificacao_risco":        analise.get("classificacao_risco"),
        "modelo_ia":                  analise.get("modelo"),
        "documentos_analisados":      analise.get("total_documentos_analisados"),
        "documentos_enviados_modelo": analise.get("documentos_enviados_ao_modelo"),
        "tokens_entrada":             analise.get("tokens_entrada"),
        "tokens_saida":               analise.get("tokens_saida"),
        "custo_usd":                  analise.get("custo_usd"),
        "data_extracao":              data_extracao,
        "status":                     "pendente",
    }
    return {k: v for k, v in data.items() if v is not None}
```

E `_upsert_rascunho` passa a usá-la — substituir todo o bloco que monta `data`
(hoje das linhas 156 a 178) por:

```python
    responsavel_nome = analise.get("responsavel_sugerido", "")
    responsavel_map = _build_responsavel_map(client)
    responsavel_id = responsavel_map.get(responsavel_nome.lower())

    data = _montar_linha_rascunho(
        processo_id, analise, responsavel_id,
        datetime.now(timezone.utc).isoformat(),
    )
```

O resto da função (a consulta por rascunho pendente e o update/insert) fica igual.

- [ ] **Step 4: Rodar e ver passar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_supabase_writer.py
```

Esperado: 3 linhas `OK`.

- [ ] **Step 5: Commit**

```bash
git add supabase_writer.py test_supabase_writer.py && git commit -m "feat: rascunho grava tokens e custo; montagem da linha vira funcao pura"
```

---

### Task 5: O runner cronometra cada processo

**Files:**
- Modify: `runner.py` (import; função pura nova; renomear `processar_cnj`; gravação)
- Modify: `test_runner.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar em `test_runner.py` (import no topo, junto dos outros; chamadas no `__main__`):

```python
from runner import duracao_segundos


def test_duracao_arredonda_para_segundos_inteiros():
    assert duracao_segundos(100.0, 112.4) == 12
    print("OK duracao_arredonda")


def test_duracao_nunca_e_negativa():
    # relógio monotônico não anda para trás, mas gravar número negativo
    # envenenaria a média no painel para sempre
    assert duracao_segundos(200.0, 100.0) == 0
    print("OK duracao_nao_negativa")


def test_duracao_de_processo_instantaneo_e_zero():
    assert duracao_segundos(50.0, 50.0) == 0
    print("OK duracao_zero")
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_runner.py
```

Esperado: `ImportError: cannot import name 'duracao_segundos'`

- [ ] **Step 3: Implementar**

`runner.py` **não importa `time`** hoje. Acrescentar junto dos outros imports:

```python
import time
```

Função pura, perto de `eh_nada_novo`:

```python
def duracao_segundos(inicio: float, fim: float) -> int:
    """
    Segundos inteiros entre dois instantes de time.monotonic().
    Função pura — ver test_runner.py. Nunca negativo: número negativo gravado
    envenena a média do painel de forma silenciosa.
    """
    return max(0, round(fim - inicio))
```

Gravação, perto de `marcar_supabase`:

```python
def gravar_duracao(cnj_id: str, segundos: int) -> None:
    """Quanto tempo este processo levou. Uma linha por CNJ, não em lote."""
    _carregar_env()
    client = _get_client()
    client.table("processos").update(
        {"duracao_extracao_s": segundos}
    ).eq("id", cnj_id).execute()
```

Agora o cronômetro. **Renomear** a função existente `processar_cnj` (linha ~223) para
`_extrair_e_analisar` — só a linha do `def`, o corpo não muda:

```python
async def _extrair_e_analisar(
    info: CNJInfo,
    data_str: str,
    prefixo: str,
    data_corte: str | None = None,
) -> dict | None:
```

E criar o invólucro que mede, logo depois do corpo dela:

```python
async def processar_cnj(
    info: CNJInfo,
    data_str: str,
    prefixo: str,
    data_corte: str | None = None,
) -> dict | None:
    """
    Mesma coisa que _extrair_e_analisar, cronometrada.

    Mede todas as tentativas, inclusive as que falham: tempo gasto num processo que
    deu erro é tempo real. Quais entram na média é decisão da interface, não daqui.
    """
    inicio = time.monotonic()
    resultado = await _extrair_e_analisar(info, data_str, prefixo, data_corte=data_corte)
    if isinstance(resultado, dict):
        resultado["duracao_extracao_s"] = duracao_segundos(inicio, time.monotonic())
    return resultado
```

Por último, gravar. No laço de `processar_por_sistema`, logo **depois** da linha
`cnj_id = ids_map.get(info.numero_cnj) if ids_map else None` (~linha 406):

```python
            if cnj_id and isinstance(resultado, dict) and "duracao_extracao_s" in resultado:
                gravar_duracao(cnj_id, resultado["duracao_extracao_s"])
```

Fica antes das checagens de Chrome morto e sessão caída, de propósito: uma tentativa
que morreu no meio também consumiu tempo. Quando o processo for tentado de novo, o
valor é sobrescrito pelo da tentativa nova.

- [ ] **Step 4: Rodar e ver passar**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && ../../../venv/Scripts/python.exe test_runner.py
```

Esperado: os testes que já existiam mais 3 linhas `OK` novas.

- [ ] **Step 5: Commit**

```bash
git add runner.py test_runner.py && git commit -m "feat: runner cronometra cada CNJ e grava a duracao no processo"
```

---

### Task 6: Suíte inteira e verificação com extração real

- [ ] **Step 1: Rodar os cinco arquivos de teste**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright/.claude/worktrees/wonderful-mestorf-981a3b && for t in test_runner.py test_sistema_auth.py test_agente.py test_analyzer.py test_supabase_writer.py; do echo "=== $t ==="; ../../../venv/Scripts/python.exe $t; done
```

Esperado: `Todos os testes passaram.` nos cinco. Eram 40 testes; agora são 51.

- [ ] **Step 2: Juntar no master local**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright && git merge --ff-only claude/agente-login-detection-9cf7d4
```

- [ ] **Step 3: Verificação com dado real — pedir ao Leonardo**

Isto **não** pode ser feito sozinho: depende de login humano nos sistemas judiciais,
com código temporário que chega no e-mail do Henrique. Pedir ao Leonardo uma extração
quando ele tiver processos novos na fila (ele espera e-mails novos em 06 e 07/08).

Lembrar da ordem que funcionou em 05/08: abrir o `agente-watchdog.bat`, logar nos
quatro sistemas **antes** de clicar em Iniciar, e conferir o RUPE se passar muito tempo
entre uma coisa e outra — a sessão dele morre com ~30 min de ociosidade.

- [ ] **Step 4: Conferir que os números chegaram**

```sql
select p.numero_cnj, p.duracao_extracao_s, r.tokens_entrada, r.tokens_saida, r.custo_usd
from processos p
left join rascunhos r on r.processo_id = p.id
where p.data_ultima_consulta > now() - interval '2 hours'
order by p.data_ultima_consulta desc;
```

Esperado: os processos da rodada com os quatro campos preenchidos. Comparar o
`custo_usd` gravado com o `custo: USD ...` que apareceu na janela preta — têm que ser
o mesmo número.

E conferir que o passado continua vazio, que é o comportamento correto:

```sql
select count(*) as antigos_com_custo
from rascunhos r join processos p on p.id = r.processo_id
where r.custo_usd is not null and p.data_ultima_consulta < current_date;
```

Esperado: `0`.

- [ ] **Step 5: Push, com confirmação do Leonardo**

```bash
cd C:/Users/User/Projects/paes-alves-pequeno-advogados/controladoria-playwright && git push origin master
```

Este repositório não faz deploy automático — o código só chega na máquina do Henrique
quando ele roda o `atualizar.bat`. Ainda assim, pedir confirmação antes.

---

## Depois desta parte

A Parte 2 (os quatro cartões no dashboard) é outro plano, em outro repositório, e só
deve ser escrita **depois** que a Task 6 confirmar dado real nas colunas. Escrever a
tela antes é escrever contra dado imaginado.

Atenção quando chegar lá: o painel sobe para a Vercel automaticamente quando o commit
chega no `main`. Lá, commit e deploy são a mesma coisa.

## O que este plano deliberadamente não faz

- **Não preenche custo histórico.** Impossível: a chamada já aconteceu e o consumo não
  foi guardado. Os 158 processos existentes ficam nulos para sempre.
- **Não amarra o preço ao modelo.** Se alguém trocar o `MODEL` sem mexer nas
  constantes de preço, o custo gravado passa a mentir. Está comentado no código; virar
  tabela de preços por modelo é complexidade que ainda não se paga.
- **Não mede o custo do `reanalisar.py`.** Ele chama o mesmo `analisar_processo`, então
  a análise carrega os campos e o `_upsert_rascunho` grava — funciona de graça. Mas a
  duração não, porque quem cronometra é o runner. Reanálise não tem duração de
  extração, e isso é honesto: ela não extraiu nada.
