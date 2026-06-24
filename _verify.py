import asyncio, time, sys
import rupe_extractor as R
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CNJ = "0372800-08.2026.8.13.0000"
t = time.time()
res = asyncio.run(R.extrair_processo(CNJ))
dt = time.time() - t
if res.get("erro"):
    print("ERRO geral:", res["erro"]); sys.exit(1)
docs = res["documentos"]
erros = [d for d in docs if d.get("erro")]
com_texto = sum(1 for d in docs if (d.get("texto") or "").strip())
print(f"CONCLUIU em {dt:.0f}s")
print(f"total_documentos={res['total_documentos']}  com_texto={com_texto}  com_erro={len(erros)}")
for d in erros:
    print(f"  peça {d.get('numero_documento')}: {str(d.get('erro'))[:70]}")
