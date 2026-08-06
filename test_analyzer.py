"""test_analyzer.py — testes do cálculo de custo. Rodar: python test_analyzer.py"""

from analyzer import anexar_uso, calcular_custo_usd


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


if __name__ == "__main__":
    test_custo_de_um_milhao_de_tokens_de_cada_lado()
    test_custo_de_chamada_real_medida_em_05_08_2026()
    test_chamada_sem_tokens_custa_zero()
    test_anexar_uso_poe_os_tres_campos_na_analise()
    test_anexar_uso_preserva_o_que_ja_estava_na_analise()
    print("Todos os testes passaram.")
