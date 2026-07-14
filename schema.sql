-- ============================================================
-- Schema — Controladoria Paes Alves Pequeno Advogados
-- Cole este SQL no SQL Editor do novo projeto Supabase
-- e clique em RUN. Rode o arquivo inteiro de uma vez.
-- ============================================================

-- 1. USUÁRIOS
CREATE TABLE IF NOT EXISTS public.usuarios (
  id          uuid        NOT NULL DEFAULT gen_random_uuid(),
  nome        text        NOT NULL,
  email       text        NOT NULL,
  oab         text,
  papel       text        NOT NULL,
  ativo       bool        DEFAULT true,
  criado_em   timestamptz DEFAULT now(),
  CONSTRAINT usuarios_pkey PRIMARY KEY (id),
  CONSTRAINT usuarios_email_key UNIQUE (email),
  CONSTRAINT usuarios_papel_check CHECK (papel = ANY (ARRAY['gestor','advogado','estagiario']))
);

-- 2. EMAILS RECEBIDOS
CREATE TABLE IF NOT EXISTS public.emails_recebidos (
  id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
  remetente           text        NOT NULL,
  assunto             text,
  data_recebimento    timestamptz NOT NULL,
  data_processamento  timestamptz DEFAULT now(),
  total_cnj           int4        DEFAULT 0,
  CONSTRAINT emails_recebidos_pkey PRIMARY KEY (id)
);

-- 3. PROCESSOS
CREATE TABLE IF NOT EXISTS public.processos (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid(),
  numero_cnj            text        NOT NULL,
  vara                  text,
  comarca               text,
  classe_processual     text,
  polo_ativo            text,
  polo_passivo          text,
  status_atual          text,
  data_ajuizamento      date,
  data_ultima_consulta  timestamptz,
  data_criacao          timestamptz DEFAULT now(),
  sistema               text,
  tipo                  text,
  pje_status            text,
  observacoes           text,
  email_id              uuid,
  responsavel_id        uuid,
  total_documentos      int4,
  proxima_acao          text,
  fonte                 text        DEFAULT 'manual',
  duplicata             bool        DEFAULT false,
  motivo_ignorado       text,
  data_entrada          timestamptz DEFAULT now(),
  lote_id               text,
  numero_publicacao     text,
  CONSTRAINT processos_pkey PRIMARY KEY (id),
  CONSTRAINT processos_numero_cnj_key UNIQUE (numero_cnj),
  CONSTRAINT processos_email_id_fkey FOREIGN KEY (email_id) REFERENCES public.emails_recebidos (id),
  CONSTRAINT processos_responsavel_id_fkey FOREIGN KEY (responsavel_id) REFERENCES public.usuarios (id),
  CONSTRAINT processos_status_atual_check CHECK (status_atual = ANY (ARRAY['PENDENTE','EM_ANDAMENTO','ARQUIVADO','CONTESTACAO','SENTENCA_ACORDO','EXECUCAO','AGUARDAR','MANIFESTAR'])),
  CONSTRAINT processos_pje_status_check CHECK (pje_status IS NULL OR (pje_status = ANY (ARRAY['pendente','processado','ignorado','erro_browser','captcha_bloqueado'])))
);

CREATE INDEX IF NOT EXISTS idx_processos_numero_cnj ON public.processos USING btree (numero_cnj);
CREATE INDEX IF NOT EXISTS idx_processos_status     ON public.processos USING btree (status_atual);

-- 4. DOCUMENTOS
CREATE TABLE IF NOT EXISTS public.documentos (
  id               uuid        NOT NULL DEFAULT gen_random_uuid(),
  processo_id      uuid        NOT NULL,
  indice           int4        NOT NULL,
  numero_documento text,
  url_iframe       text,
  texto            text,
  erro             text,
  data_extracao    timestamptz DEFAULT now(),
  titulo           text,
  data_documento   text,
  juntado_por      text,
  cargo            text,
  CONSTRAINT documentos_pkey PRIMARY KEY (id),
  CONSTRAINT documentos_processo_id_indice_key UNIQUE (processo_id, indice),
  CONSTRAINT documentos_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES public.processos (id)
);

-- 5. RASCUNHOS
CREATE TABLE IF NOT EXISTS public.rascunhos (
  id                        uuid        NOT NULL DEFAULT gen_random_uuid(),
  processo_id               uuid        NOT NULL,
  status_sugerido           text,
  prazo_fatal_dias_uteis    int4,
  prazo_interno_dias_uteis  int4,
  cenario_prazo             text,
  justificativa             text,
  alerta                    text,
  status                    text        DEFAULT 'pendente',
  data_revisao              timestamptz,
  data_criacao              timestamptz DEFAULT now(),
  classificacao_risco       text,
  responsavel_sugerido_id   uuid,
  proxima_acao              text,
  modelo_ia                 text,
  data_extracao             timestamptz,
  documentos_analisados     int4,
  documentos_enviados_modelo int4,
  responsavel_sugerido      text,
  CONSTRAINT rascunhos_pkey PRIMARY KEY (id),
  CONSTRAINT rascunhos_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES public.processos (id),
  CONSTRAINT rascunhos_responsavel_sugerido_id_fkey FOREIGN KEY (responsavel_sugerido_id) REFERENCES public.usuarios (id),
  CONSTRAINT rascunhos_status_sugerido_check CHECK (status_sugerido = ANY (ARRAY['CONTESTACAO','SENTENCA_ACORDO','EXECUCAO','AGUARDAR','MANIFESTAR'])),
  CONSTRAINT rascunhos_cenario_prazo_check CHECK (cenario_prazo = ANY (ARRAY['EXPLICITO','VIA_ARTIGO','INFERIDO'])),
  CONSTRAINT rascunhos_status_check CHECK (status = ANY (ARRAY['pendente','aprovado','rejeitado']))
);

CREATE INDEX IF NOT EXISTS idx_rascunhos_status ON public.rascunhos USING btree (status);

-- 6. TAREFAS
CREATE TABLE IF NOT EXISTS public.tarefas (
  id              uuid        NOT NULL DEFAULT gen_random_uuid(),
  rascunho_id     uuid        NOT NULL,
  processo_id     uuid        NOT NULL,
  responsavel_id  uuid        NOT NULL,
  prazo_fatal     date,
  prazo_interno   date,
  status_tarefa   text        DEFAULT 'aberta',
  observacoes     text,
  notificado_em   timestamptz,
  criado_em       timestamptz DEFAULT now(),
  atualizado_em   timestamptz DEFAULT now(),
  CONSTRAINT tarefas_pkey PRIMARY KEY (id),
  CONSTRAINT tarefas_rascunho_id_fkey FOREIGN KEY (rascunho_id) REFERENCES public.rascunhos (id),
  CONSTRAINT tarefas_processo_id_fkey FOREIGN KEY (processo_id) REFERENCES public.processos (id),
  CONSTRAINT tarefas_responsavel_id_fkey FOREIGN KEY (responsavel_id) REFERENCES public.usuarios (id),
  CONSTRAINT tarefas_status_tarefa_check CHECK (status_tarefa = ANY (ARRAY['aberta','concluida','revisao']))
);

CREATE INDEX IF NOT EXISTS idx_tarefas_prazo_fatal ON public.tarefas USING btree (prazo_fatal);
CREATE INDEX IF NOT EXISTS idx_tarefas_responsavel ON public.tarefas USING btree (responsavel_id);

-- 7. COMANDOS
CREATE TABLE IF NOT EXISTS public.comandos (
  id            uuid        NOT NULL DEFAULT gen_random_uuid(),
  acao          text        NOT NULL DEFAULT 'iniciar',
  status        text        NOT NULL DEFAULT 'pendente',
  mensagem      text,
  criado_em     timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT comandos_pkey PRIMARY KEY (id)
);
COMMENT ON TABLE public.comandos IS 'Fila de comandos do app para o agente local da controladoria. status: pendente|em_andamento|concluido|erro';

CREATE INDEX IF NOT EXISTS comandos_status_criado_idx ON public.comandos USING btree (status, criado_em);

-- 8. CONFIGURAÇÕES
CREATE TABLE IF NOT EXISTS public.configuracoes (
  id            uuid        NOT NULL DEFAULT gen_random_uuid(),
  chave         text        NOT NULL,
  valor         text        NOT NULL,
  descricao     text,
  atualizado_em timestamptz DEFAULT now(),
  CONSTRAINT configuracoes_pkey PRIMARY KEY (id),
  CONSTRAINT configuracoes_chave_key UNIQUE (chave)
);

-- ============================================================
-- Row Level Security
-- RLS habilitado em todas as tabelas. Apenas processos e documentos
-- possuem policies (leitura/insert/update para o papel authenticated).
-- As demais ficam com RLS ligado sem policy — acesso somente via
-- service_role (idêntico ao projeto de origem).
-- ============================================================
ALTER TABLE public.usuarios          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emails_recebidos  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rascunhos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tarefas           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.documentos        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.configuracoes     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comandos          ENABLE ROW LEVEL SECURITY;

-- processos
CREATE POLICY "Usuarios autenticados podem ler processos"
  ON public.processos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Usuarios autenticados podem inserir processos"
  ON public.processos FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Usuarios autenticados podem atualizar processos"
  ON public.processos FOR UPDATE TO authenticated USING (true);

-- documentos
CREATE POLICY "Usuarios autenticados podem ler documentos"
  ON public.documentos FOR SELECT TO authenticated USING (true);
CREATE POLICY "Usuarios autenticados podem inserir documentos"
  ON public.documentos FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Usuarios autenticados podem atualizar documentos"
  ON public.documentos FOR UPDATE TO authenticated USING (true);
