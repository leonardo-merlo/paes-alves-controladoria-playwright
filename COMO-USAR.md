# Como usar o PJE Extractor

## Modo rápido (recomendado): um comando só

```bash
.\venv\Scripts\activate
python iniciar.py
```

O `iniciar.py` consulta os processos pendentes no Supabase, abre o Chrome já nas
abas dos sistemas necessários e fica observando o login. **Assim que você loga em
todos os sistemas, a extração começa sozinha** — sem precisar apertar Enter nem
rodar um segundo comando.

No Windows também dá pra dar duplo-clique em `iniciar.bat`.

> Timeout padrão de login: 10 minutos. Se um sistema não logar nesse tempo, o
> script avisa quais faltaram e encerra.

O fluxo manual em duas etapas (`preparar.py` + `runner.py`) continua disponível
para depuração — veja as seções abaixo.

---

## 1. Abrir o Chrome com CDP habilitado

**Windows:**
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug
```

**Mac:**
```
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-debug
```

> Depois de abrir, logar normalmente no PJE (com OTP se necessário).
> Deixar esse Chrome aberto enquanto o script roda.

---

## 2. Ativar o ambiente virtual

```bash
# Windows
.\venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

---

## 3. Testar a conexão CDP

```bash
python test_connection.py
```

Deve imprimir `✅ CDP OK` e listar as abas abertas.

---

## 4. Rodar a extração

```bash
python pje_extractor.py 5006107-76.2025.8.13.0384
```

O resultado é impresso como JSON. Para salvar em arquivo:

```bash
python pje_extractor.py 5006107-76.2025.8.13.0384 > resultado.json
```

---

## Erros comuns

| Erro | Causa | Solução |
|---|---|---|
| `Connection refused` | Chrome não está rodando com CDP | Abrir Chrome com o comando correto |
| `sessao_expirada` | PJE deslogou o Henrique | Henrique faz login novamente |
| `reCAPTCHA detectado` | PJE ativou verificação | Resolver manualmente no Chrome, depois rodar de novo |
| `Processo não encontrado` | Número CNJ errado ou não aparece nos resultados | Verificar o número e tentar novamente |
| `PDF_ESCANEADO` | PDF não tem texto extraível | Screenshot salvo em `/tmp/doc_screenshot.png` |

---

## Estrutura do JSON retornado

```json
{
  "sistema": "pje",
  "numero_cnj": "5006107-76.2025.8.13.0384",
  "total_documentos": 12,
  "metadados_timeline": [...],
  "documentos": [
    {
      "indice": 1,
      "numero_documento": "12345678",
      "url_iframe": "https://pje.tjmg.jus.br/...",
      "texto": "Conteúdo extraído do documento...",
      "erro": null
    }
  ],
  "erros": []
}
```
