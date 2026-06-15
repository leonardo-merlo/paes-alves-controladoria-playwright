# Skill: Extrator de CNJs do Gmail → Supabase

## O que faz
A cada execução, lê e-mails não lidos do Gmail, extrai números CNJ e dados do cabeçalho do processo (vara, comarca, polo ativo, polo passivo, classe processual), e registra diretamente na tabela `processos` (campo `pje_status = 'pendente'`) para processamento automático pelo runner.py.

## Quando rodar
A cada 2 horas, ou manualmente quando o Henrique receber um lote de processos.

## Instruções

1. Acesse o Gmail via MCP (conector Gmail disponível no Cowork).

2. Busque e-mails não lidos na conta do Henrique (henrique@paespequenoadv.com.br)
   que contenham números de processo CNJ.
   - Filtro sugerido: `is:unread subject:processo OR subject:CNJ OR subject:prazo OR subject:Publicações`

3. Para cada e-mail encontrado, extraia:

   **CNJ** (obrigatório):
   - Padrão: `\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}`
   - Exemplo: `5009135-81.2025.8.13.0439`

   **Vara e Comarca** (quando disponível):
   - Padrão: `Vara:\s*(.+?)\s+da\s+Comarca\s+de\s+([^\n\|]+)`
   - Exemplo: `Vara: 3ª Vara Cível da Comarca de Muriaé` → vara=`3ª Vara Cível`, comarca=`Muriaé`
   - Alternativa sem "Vara:": procurar linha que contenha "Vara" e "Comarca" juntos

   **Polo Ativo** (quando disponível):
   - Padrão: `POLO ATIVO:\s*([^\n\|]+)`

   **Polo Passivo** (quando disponível):
   - Padrão: `POLO PASSIVO:\s*([^\n\|]+?)(?:\s+(?:ADVOGADO|CPF)|$)`

   **Classe Processual** (quando disponível):
   - Padrão: `CLASSE:\s*(?:\[.+?\]\s*)?([^\n\(\|]+)`
   - Exemplo: `CLASSE: [CIVEL] PROCEDIMENTO COMUM CIVEL (7)` → `PROCEDIMENTO COMUM CIVEL`

4. Para cada CNJ extraído, chame `inserir_processos_pendentes()` do `runner.py` passando um dict com:
   ```python
   {
     "numero_cnj": "5009135-81.2025.8.13.0439",
     "vara": "3ª Vara Cível",          # ou None
     "comarca": "Muriaé",              # ou None
     "polo_ativo": "LENISSE MONTEIRO", # ou None
     "polo_passivo": "BANCO X",        # ou None
     "classe_processual": "PROCEDIMENTO COMUM CIVEL",  # ou None
   }
   ```
   Com `fonte="email"` e `lote_id=<assunto do e-mail>`.

   Se preferir inserir via Supabase direto (sem runner.py), use:
   - URL: `https://elxfggiidacmhwprbfev.supabase.co`
   - Tabela: `processos`
   - Campos obrigatórios: `numero_cnj`, `pje_status: "pendente"`, `fonte: "email"`, `lote_id`
   - Campos opcionais: `vara`, `comarca`, `polo_ativo`, `polo_passivo`, `classe_processual`
   - Use upsert com `on_conflict=numero_cnj` — não sobrescreve se já existir com status diferente de pendente

5. Marque os e-mails processados como lidos no Gmail.

6. Reporte um resumo:
   - Quantos e-mails foram processados
   - Quantos CNJs foram extraídos
   - Quais campos de cabeçalho foram encontrados
   - Se houve algum erro

## Observações
- CNJs duplicados (já existentes em `processos` com qualquer status) são marcados como `duplicata=true` e `pje_status='ignorado'` automaticamente.
- Não precisa verificar duplicatas manualmente — `inserir_processos_pendentes()` faz isso.
- Se não houver e-mails novos, apenas reporte "Nenhum e-mail novo encontrado."
- Os campos vara/comarca/polos são opcionais — se o e-mail não contiver, deixar como null.

## Credenciais necessárias (configurar no Cowork)
- Gmail MCP: conta do Henrique
- Supabase service_role key: salva nas configurações do Cowork
