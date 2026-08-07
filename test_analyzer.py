"""test_analyzer.py — testes do cálculo de custo e da lista de status.
Rodar: python test_analyzer.py"""

from analyzer import PROMPT_USER, STATUS_SUGERIDOS, anexar_uso, calcular_custo_usd

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


if __name__ == "__main__":
    test_status_do_prompt_sao_exatamente_os_que_o_banco_aceita()
    test_prompt_oferece_todos_os_status_ao_modelo()
    test_custo_de_um_milhao_de_tokens_de_cada_lado()
    test_custo_de_chamada_real_medida_em_05_08_2026()
    test_chamada_sem_tokens_custa_zero()
    test_anexar_uso_poe_os_tres_campos_na_analise()
    test_anexar_uso_preserva_o_que_ja_estava_na_analise()
    print("Todos os testes passaram.")
