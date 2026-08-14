"""
debug_sistema.py — Mapeia automaticamente a estrutura de qualquer sistema judicial.

Uso:
  python debug_sistema.py              # analisa todas as abas abertas
  python debug_sistema.py pje.tjmg     # analisa só a aba que contém esse domínio
  python debug_sistema.py --cnj 5009135-81.2025.8.13.0439  # tenta buscar um CNJ

Salva o relatório em debug_outputs/<dominio>_<timestamp>.json
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page

CDP_URL    = "http://127.0.0.1:9222"
OUTPUT_DIR = Path("debug_outputs")

SISTEMAS_CONHECIDOS = {
    "pje.tjmg.jus.br":      "PJE TJMG (1ª instância)",
    "eproc.tjmg.jus.br":    "eProc TJMG",
    "tjrj.pje.jus.br":      "PJE TJRJ",
    "eproc1g.tjrj.jus.br":  "eProc TJRJ (1ª instância)",
    "eproc.trf6.jus.br":    "eProc TRF6",
    "eproc.trf2.jus.br":    "eProc TRF2",
    "pe.tjmg.jus.br":       "TJMG 2ª Instância",
}

CNJ_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


def detectar_sistema(url: str) -> str:
    for dominio, nome in SISTEMAS_CONHECIDOS.items():
        if dominio in url:
            return nome
    return "Sistema desconhecido"


async def mapear_formularios(page: Page) -> list[dict]:
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('form')).map((form, fi) => ({
            indice: fi,
            id: form.id || null,
            action: form.action || null,
            campos: Array.from(form.querySelectorAll('input, select, textarea')).map(el => ({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                name: el.name || null,
                type: el.type || null,
                placeholder: el.placeholder || null,
                value: el.value || null,
                visible: el.offsetParent !== null,
            }))
        }))
    """)


async def mapear_botoes(page: Page) -> list[dict]:
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], a.btn, [class*=btn]'))
            .slice(0, 30)
            .map(el => ({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                texto: (el.innerText || el.value || '').trim().slice(0, 60),
                type: el.type || null,
                onclick: (el.getAttribute('onclick') || '').slice(0, 100),
                visible: el.offsetParent !== null,
                class: el.className.slice(0, 80),
            }))
    """)


async def mapear_iframes(page: Page) -> list[dict]:
    iframes = []
    for frame in page.frames:
        iframes.append({"name": frame.name, "url": frame.url})
    dom_iframes = await page.evaluate("""
        () => Array.from(document.querySelectorAll('iframe')).map(f => ({
            id: f.id || null,
            name: f.name || null,
            src: f.src || null,
            class: f.className || null,
        }))
    """)
    return {"playwright_frames": iframes, "dom_iframes": dom_iframes}


async def mapear_inputs_visíveis(page: Page) -> list[dict]:
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('input:not([type=hidden])'))
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                id: el.id || null,
                name: el.name || null,
                type: el.type || null,
                placeholder: el.placeholder || null,
                label: (() => {
                    if (el.id) {
                        const lbl = document.querySelector(`label[for="${el.id}"]`);
                        if (lbl) return lbl.innerText.trim();
                    }
                    const parent = el.closest('td, div, li');
                    if (parent) {
                        const lbl = parent.querySelector('label, span');
                        if (lbl) return lbl.innerText.trim().slice(0, 60);
                    }
                    return null;
                })()
            }))
    """)


async def detectar_campo_cnj(page: Page) -> list[dict]:
    """Tenta detectar campos que parecem ser para número de processo/CNJ."""
    return await page.evaluate("""
        () => {
            const suspeitos = [];
            document.querySelectorAll('input').forEach(el => {
                const ctx = [el.id, el.name, el.placeholder,
                    el.closest('label')?.innerText,
                    el.closest('td')?.innerText,
                    el.closest('div')?.querySelector('label')?.innerText
                ].filter(Boolean).join(' ').toLowerCase();

                if (/processo|cnj|numero|n.mero|sequen|digito|ano|origem|tribunal/.test(ctx)) {
                    suspeitos.push({
                        id: el.id || null,
                        name: el.name || null,
                        placeholder: el.placeholder || null,
                        contexto: ctx.slice(0, 100),
                        selector: el.id ? `[id="${el.id}"]` : (el.name ? `[name="${el.name}"]` : null),
                    });
                }
            });
            return suspeitos;
        }
    """)


async def buscar_cnj(page: Page, numero_cnj: str) -> dict:
    """Tenta preencher e submeter uma busca por CNJ."""
    campos_cnj = await detectar_campo_cnj(page)
    if not campos_cnj:
        return {"tentativa": False, "motivo": "Nenhum campo de CNJ detectado"}

    # tenta preencher o primeiro campo suspeito com o número inteiro
    primeiro = campos_cnj[0]
    if primeiro.get("selector"):
        try:
            await page.fill(primeiro["selector"], numero_cnj.split("-")[0])
            return {
                "tentativa": True,
                "campo_usado": primeiro["selector"],
                "aviso": "Campo preenchido com a parte sequencial do CNJ. Verifique manualmente."
            }
        except Exception as e:
            return {"tentativa": False, "erro": str(e)}

    return {"tentativa": False, "motivo": "Seletor não encontrado"}


async def mapear_links_processo(page: Page) -> list[dict]:
    """Captura links que parecem apontar para processos."""
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
            .filter(a => /processo|autos|detalhe|consulta/i.test(a.href + a.innerText))
            .slice(0, 10)
            .map(a => ({
                texto: a.innerText.trim().slice(0, 80),
                href: a.href.slice(0, 150),
                title: a.title || null,
            }))
    """)


async def analisar_aba(page: Page, numero_cnj: str | None = None) -> dict:
    url     = page.url
    titulo  = await page.title()
    sistema = detectar_sistema(url)

    print(f"\n  Analisando: {sistema}")
    print(f"  URL: {url[:100]}")

    resultado: dict = {
        "sistema": sistema,
        "url": url,
        "titulo": titulo,
        "logado": "/login" not in url and "Login" not in titulo,
        "formularios": await mapear_formularios(page),
        "botoes": await mapear_botoes(page),
        "iframes": await mapear_iframes(page),
        "inputs_visiveis": await mapear_inputs_visíveis(page),
        "campos_cnj_detectados": await detectar_campo_cnj(page),
        "links_processo": await mapear_links_processo(page),
    }

    if numero_cnj and resultado["logado"]:
        print(f"  Tentando buscar CNJ {numero_cnj}...")
        resultado["tentativa_busca"] = await buscar_cnj(page, numero_cnj)

    return resultado


async def main() -> None:
    args = sys.argv[1:]
    filtro_dominio = None
    numero_cnj     = None

    i = 0
    while i < len(args):
        if args[i] == "--cnj" and i + 1 < len(args):
            numero_cnj = args[i + 1]
            i += 2
        else:
            filtro_dominio = args[i]
            i += 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"Erro ao conectar ao Chrome: {e}")
            print("Abra o Chrome com: chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\ChromeControladoria")
            return

        print(f"Chrome conectado. {len(browser.contexts)} contexto(s).\n")

        abas_para_analisar = []
        for ctx in browser.contexts:
            for page in ctx.pages:
                url = page.url
                if filtro_dominio and filtro_dominio not in url:
                    continue
                eh_sistema = any(d in url for d in SISTEMAS_CONHECIDOS)
                if not filtro_dominio and not eh_sistema:
                    continue
                abas_para_analisar.append(page)

        if not abas_para_analisar:
            print("Nenhuma aba de sistema judicial encontrada.")
            print("Abas abertas:")
            for ctx in browser.contexts:
                for page in ctx.pages:
                    print(f"  {page.url[:100]}")
            await browser.close()
            return

        print(f"Abas para analisar: {len(abas_para_analisar)}")
        resultados = []

        for page in abas_para_analisar:
            resultado = await analisar_aba(page, numero_cnj)
            resultados.append(resultado)

            # salvar por sistema
            dominio = next((d for d in SISTEMAS_CONHECIDOS if d in page.url), "desconhecido")
            dominio_safe = dominio.replace(".", "_").replace("/", "_")
            arquivo = OUTPUT_DIR / f"{dominio_safe}_{timestamp}.json"
            arquivo.write_text(
                json.dumps(resultado, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"  Salvo em: {arquivo}")

        await browser.close()

    # resumo
    print(f"\n{'='*50}")
    print("RESUMO DO MAPEAMENTO")
    print('='*50)
    for r in resultados:
        print(f"\n{r['sistema']}")
        print(f"  Logado: {'SIM' if r['logado'] else 'NAO'}")
        print(f"  Formulários: {len(r['formularios'])}")
        print(f"  Inputs visíveis: {len(r['inputs_visiveis'])}")
        print(f"  Campos CNJ detectados: {len(r['campos_cnj_detectados'])}")
        if r["campos_cnj_detectados"]:
            for c in r["campos_cnj_detectados"]:
                print(f"    → {c.get('selector') or c.get('id') or c.get('name')} ({c.get('contexto','')[:50]})")
        print(f"  Iframes no DOM: {len(r['iframes']['dom_iframes'])}")
        if r['iframes']['dom_iframes']:
            for f in r['iframes']['dom_iframes']:
                print(f"    → id={f['id']} src={str(f['src'])[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
