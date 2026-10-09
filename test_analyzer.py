"""test_analyzer.py — testes do cálculo de custo e da lista de status.
Rodar: python test_analyzer.py"""

from analyzer import (
    PROMPT_USER, STATUS_SUGERIDOS, _formatar_documentos, anexar_uso, calcular_custo_usd,
    revisar_analise,
)

# Cópia literal do CHECK de rascunhos.status_sugerido no banco, escrita à mão.
# É de propósito que esteja duplicada: se alguém mexer em STATUS_SUGERIDOS sem
# migrar o banco, o teste quebra aqui em vez de a gravação quebrar em produção.
STATUS_NO_BANCO = {
    "CONTESTACAO", "SENTENCA_ACORDO", "EXECUCAO", "AGUARDAR", "MANIFESTAR",
    "APELACAO", "AGRAVO_INSTRUMENTO", "EMBARGOS_DECLARACAO", "RECURSO_ESPECIAL",
    "RECURSO_EXTRAORDINARIO", "CONTRARRAZOES", "CONTRARRAZOES_RECURSO_ADESIVO",
    "PETICAO", "PETICAO_PROVAS", "COMPROVAR_HIPOSSUFICIENCIA", "EMENDA_INICIAL",
    "JUNTAR_DOCUMENTOS", "CUMPRIMENTO_SENTENCA", "CIENCIA", "ALEGACOES_FINAIS",
    "REPLICA",
}


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


def test_status_do_prompt_sao_exatamente_os_que_o_banco_aceita():
    assert set(STATUS_SUGERIDOS) == STATUS_NO_BANCO
    assert len(STATUS_SUGERIDOS) == len(STATUS_NO_BANCO)  # sem repetido
    print("OK status_batem_com_o_banco")


def test_prompt_oferece_todos_os_status_ao_modelo():
    prompt = PROMPT_USER.format(
        numero_cnj="0000000-00.0000.0.00.0000", sistema="pje_tjmg",
        data_hoje="2026-08-06", responsaveis_lista="- Henrique", eventos_formatados="",
        documentos_formatados="", responsaveis_opcoes="Henrique",
        status_opcoes="|".join(STATUS_SUGERIDOS),
    )
    # cada status precisa aparecer nas opções do JSON e ter uma regra explicando
    # quando usá-lo; sem a regra o modelo cai sempre nos mesmos três
    for status in STATUS_SUGERIDOS:
        assert status in prompt, f"{status} fora das opções do prompt"
        assert f"- {status}:" in prompt, f"{status} sem regra de quando usar"
    print("OK prompt_com_os_21_status")


def test_revisar_troca_treplica_por_replica_quando_somos_autor():
    analise = revisar_analise({"nosso_polo": "ATIVO", "status_sugerido": "REPLICA",
                               "proxima_acao": "PROTOCOLAR TRÉPLICA"})
    assert analise["proxima_acao"] == "PROTOCOLAR RÉPLICA"
    print("OK treplica_vira_replica")


def test_revisar_mantem_treplica_quando_somos_reu():
    analise = revisar_analise({"nosso_polo": "PASSIVO", "status_sugerido": "PETICAO",
                               "proxima_acao": "PROTOCOLAR TRÉPLICA"})
    assert analise["proxima_acao"] == "PROTOCOLAR TRÉPLICA"
    print("OK treplica_reu_intacta")


def test_revisar_avisa_aguardar_com_texto_de_protocolar():
    analise = revisar_analise({"status_sugerido": "AGUARDAR", "alerta": None,
                               "proxima_acao": "PROTOCOLAR CONTRARRAZÕES"})
    assert "AGUARDAR" in analise["alerta"]
    print("OK aviso_aguardar_com_protocolar")


def test_revisar_avisa_status_de_ato_com_texto_de_aguardar():
    analise = revisar_analise({"status_sugerido": "CIENCIA", "alerta": "Prazo inferido.",
                               "proxima_acao": "AGUARDAR — audiência"})
    assert analise["alerta"].startswith("Prazo inferido. Conferir:")
    print("OK aviso_preserva_alerta")


def test_revisar_nao_mexe_em_analise_coerente():
    analise = revisar_analise({"nosso_polo": "ATIVO", "status_sugerido": "AGUARDAR",
                               "alerta": None, "proxima_acao": "AGUARDAR — sentença"})
    assert analise["alerta"] is None
    print("OK analise_coerente_intacta")


def test_certidao_de_migracao_sai_da_integra_e_nao_gasta_vaga():
    docs = [{"indice": i, "numero_documento": str(i), "titulo": "Certidão de Erro de Migração",
             "data_documento": "01/10/2026", "texto": "certidão"} for i in range(8)]
    docs.append({"indice": 9, "numero_documento": "9", "titulo": "Despacho",
                 "data_documento": "30/09/2026", "texto": "Intime-se para réplica."})
    texto, na_integra = _formatar_documentos(docs)
    assert na_integra == 1 and "Intime-se para réplica." in texto
    print("OK migracao_nao_gasta_vaga")


def test_revisar_poe_o_responsavel_do_tipo_de_caso():
    analise = revisar_analise({"status_sugerido": "REPLICA", "responsavel_sugerido": "Henilda",
                               "alerta": None, "proxima_acao": "PROTOCOLAR RÉPLICA"})
    assert analise["responsavel_sugerido"] == "Júlia"
    print("OK responsavel_por_status")


def test_revisar_mantem_responsavel_de_status_fora_da_tabela():
    analise = revisar_analise({"status_sugerido": "AGRAVO_INSTRUMENTO", "responsavel_sugerido": "Henilda",
                               "alerta": None, "proxima_acao": "PROTOCOLAR AGRAVO"})
    assert analise["responsavel_sugerido"] == "Henilda"
    print("OK responsavel_fora_da_tabela")


def test_revisar_prazo_interno_vence_dois_dias_uteis_antes_do_fatal():
    analise = revisar_analise({"status_sugerido": "REPLICA", "prazo_fatal_dias_uteis": 15,
                               "prazo_interno_dias_uteis": 12, "alerta": None, "proxima_acao": "PROTOCOLAR RÉPLICA"})
    assert analise["prazo_interno_dias_uteis"] == 13
    print("OK prazo_interno_menos_2")


def test_revisar_prazo_interno_nunca_fica_antes_do_primeiro_dia():
    analise = revisar_analise({"status_sugerido": "CIENCIA", "prazo_fatal_dias_uteis": 2,
                               "alerta": None, "proxima_acao": "VERIFICAR — intimação"})
    assert analise["prazo_interno_dias_uteis"] == 1
    print("OK prazo_interno_minimo")


if __name__ == "__main__":
    test_revisar_troca_treplica_por_replica_quando_somos_autor()
    test_revisar_mantem_treplica_quando_somos_reu()
    test_revisar_avisa_aguardar_com_texto_de_protocolar()
    test_revisar_avisa_status_de_ato_com_texto_de_aguardar()
    test_revisar_nao_mexe_em_analise_coerente()
    test_certidao_de_migracao_sai_da_integra_e_nao_gasta_vaga()
    test_status_do_prompt_sao_exatamente_os_que_o_banco_aceita()
    test_prompt_oferece_todos_os_status_ao_modelo()
    test_custo_de_um_milhao_de_tokens_de_cada_lado()
    test_custo_de_chamada_real_medida_em_05_08_2026()
    test_chamada_sem_tokens_custa_zero()
    test_anexar_uso_poe_os_tres_campos_na_analise()
    test_anexar_uso_preserva_o_que_ja_estava_na_analise()
    test_revisar_poe_o_responsavel_do_tipo_de_caso()
    test_revisar_mantem_responsavel_de_status_fora_da_tabela()
    test_revisar_prazo_interno_vence_dois_dias_uteis_antes_do_fatal()
    test_revisar_prazo_interno_nunca_fica_antes_do_primeiro_dia()
    print("Todos os testes passaram.")
