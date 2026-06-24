# Instalação em uma máquina nova (Windows)

Passo a passo para rodar o agente da controladoria do zero numa máquina nova
(ex.: computador do escritório). Siga na ordem.

## 1. Pré-requisitos (instalar antes)

- **Python 3.11+** — baixar de [python.org](https://www.python.org/downloads/)
  (botão "Download the latest version for Windows").
  - ⚠️ **NÃO** usar a versão da Microsoft Store (trava o agente com erro `exit 49`).
  - Na primeira tela do instalador, **marcar "Add Python to PATH"**.
- **Google Chrome** instalado em `C:\Program Files\Google\Chrome\Application\chrome.exe`.

## 2. Copiar a pasta do projeto

Copiar a pasta `controladoria-playwright` para a máquina (pen drive, Drive ou zip).
**Sem** as pastas `venv/` e o arquivo `.env` — eles são recriados/configurados aqui.

## 3. Abrir o terminal na pasta

Abrir o PowerShell e entrar na pasta copiada, por exemplo:

```powershell
cd C:\Users\<usuario>\controladoria-playwright
```

## 4 e 5. Criar o venv e instalar as dependências

**Jeito fácil:** dar **duplo-clique no `setup.bat`**. Ele faz tudo isto sozinho
(criar o venv + instalar as dependências + o navegador) e avisa quando terminar.

**Manualmente (se preferir):**

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## 6. Criar o arquivo `.env`

Criar um arquivo chamado `.env` na raiz da pasta, com as chaves (peça ao Leonardo
por um canal seguro — não mandar por e-mail/WhatsApp aberto):

```
ANTHROPIC_API_KEY=...
SUPABASE_URL=https://SEU_PROJETO.supabase.co
SUPABASE_KEY=...          # anon/public key
SUPABASE_SERVICE_KEY=...  # service_role key
```

## 7. Testar

Dar duplo-clique em `agente.bat` (ou no atalho da área de trabalho). A janela deve
abrir e ficar "ouvindo" os comandos do app. Deixar essa janela aberta enquanto usa.

## 8. (Opcional) Atalho na área de trabalho

Para criar o atalho de "Agente Controladoria", rodar no PowerShell:

```powershell
$bat = "$PWD\agente.bat"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Agente Controladoria.lnk")
$sc.TargetPath = $bat; $sc.WorkingDirectory = "$PWD"; $sc.Save()
```

## Erros comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `exit 49` / abre a Microsoft Store | Python da Store | Desinstalar e instalar do python.org |
| `ModuleNotFoundError` | venv não ativado ou deps não instaladas | Repetir passos 5 |
| App diz "agente sem resposta" | Janela do `agente.bat` fechada | Reabrir o atalho |
| `.env` não encontrado | Faltou o passo 6 | Criar o `.env` na raiz |
