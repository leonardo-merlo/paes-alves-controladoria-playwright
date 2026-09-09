"""test_supabase_writer.py — testes da montagem da linha de rascunho.
Rodar: python test_supabase_writer.py"""

from supabase_writer import _montar_linha_rascunho, _chave_responsavel

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


def test_chave_responsavel_nome_normal():
    assert _chave_responsavel("Henrique") == "henrique"
    print("OK chave_responsavel_nome_normal")


def test_chave_responsavel_nulo_nao_estoura():
    """O bug de 09/09: chave presente com null derrubava a gravacao inteira."""
    assert _chave_responsavel(None) == ""
    print("OK chave_responsavel_nulo_nao_estoura")


def test_chave_responsavel_vazio_e_espaco():
    assert _chave_responsavel("") == ""
    assert _chave_responsavel("   ") == ""
    print("OK chave_responsavel_vazio_e_espaco")


def test_chave_responsavel_ignora_espaco_em_volta():
    assert _chave_responsavel("  Julia  ") == "julia"
    print("OK chave_responsavel_ignora_espaco_em_volta")


if __name__ == "__main__":
    test_linha_carrega_tokens_e_custo()
    test_analise_antiga_sem_custo_nao_quebra()
    test_custo_zero_nao_e_descartado_como_ausente()
    test_chave_responsavel_nome_normal()
    test_chave_responsavel_nulo_nao_estoura()
    test_chave_responsavel_vazio_e_espaco()
    test_chave_responsavel_ignora_espaco_em_volta()
    print("Todos os testes passaram.")
