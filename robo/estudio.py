"""Estúdio: a interface simples do produto, no navegador. Sem pastas, sem painel 3D, sem robô ligado.

    python -m robo estudio            abre http://127.0.0.1:8765 no navegador

Duas abas:
  1. Tratar planilha  envia o arquivo (arrastar ou escolher) → limpeza, padronização, modelagem e análise
                      (robo/entrega.py) → o relatório aparece na tela, com os downloads (relatório, indicadores,
                      base tratada)
  2. SQL              consulta os dados TRATADOS da planilha enviada (cada aba vira uma tabela, num banco SQLite em
                      memória: não precisa instalar nada) ou o PostgreSQL do robô, quando ele estiver configurado
                      (sempre só leitura: mesmas camadas de proteção do painel, robo/consultas.py)

Só escuta em 127.0.0.1 (este computador): ninguém da rede acessa, e a planilha não sai da máquina.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from email.parser import BytesParser
from email.policy import default as politica_email
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import pandas as pd

log = logging.getLogger("robo")

PORTA_PADRAO = 8765
TAMANHO_MAXIMO = 60 * 1024 * 1024  # 60 MB por planilha
EXTENSOES = {".xlsx", ".xlsm", ".xls", ".csv", ".txt"}
LIMITE_LINHAS = 500


class Estudio:
    """O estado do estúdio: as entregas feitas nesta sessão e o banco SQLite de cada uma."""

    def __init__(self, cfg, pasta: Path | None = None):
        self.cfg = cfg
        self.pasta = Path(pasta or tempfile.mkdtemp(prefix="robo_estudio_"))
        self.entregas: dict[str, dict] = {}
        self._trava = threading.Lock()

    # ------------------------------------------------------------------ tratar
    def tratar(self, nome: str, dados: bytes, segmentos: list[str] | None = None) -> dict:
        from robo import entrega
        nome = Path(nome or "planilha.xlsx").name
        if Path(nome).suffix.lower() not in EXTENSOES:
            raise ValueError(f"Formato não suportado: envie {', '.join(sorted(EXTENSOES))}")
        eid = uuid.uuid4().hex[:10]
        entrada = self.pasta / eid / nome
        entrada.parent.mkdir(parents=True)
        entrada.write_bytes(dados)
        r = entrega.entregar(self.cfg, entrada, entrada.parent, segmentos)
        pasta = Path(r["pasta"])
        tabelas = {}
        if (pasta / "base_tratada.xlsx").exists():
            for aba, df in pd.read_excel(pasta / "base_tratada.xlsx", sheet_name=None).items():
                tabelas[_nome_tabela(aba)] = df
        with self._trava:
            self.entregas[eid] = {"id": eid, "arquivo": nome, "pasta": pasta, "tabelas": tabelas, "sqlite": None,
                                  "quando": time.strftime("%d/%m %H:%M")}
        return {"id": eid, "ok": r["ok"], "arquivo": nome, "recomendacoes": r["recomendacoes"], "erros": r["erros"],
                "linhas": r["linhas"], "arquivos": r["arquivos"], "tabelas": self.esquema(eid)}

    def esquema(self, eid: str) -> list[dict]:
        e = self.entregas.get(eid) or {}
        return [{"tabela": t, "linhas": len(df), "colunas": [str(c) for c in df.columns]}
                for t, df in (e.get("tabelas") or {}).items()]

    # ------------------------------------------------------------------ SQL
    def _sqlite(self, eid: str) -> sqlite3.Connection:
        e = self.entregas.get(eid)
        if not e:
            raise ValueError("Envie uma planilha primeiro (aba Tratar planilha).")
        if e["sqlite"] is None:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            for t, df in e["tabelas"].items():
                df.to_sql(t, conn, index=False)
            conn.execute("PRAGMA query_only = ON")  # depois de carregar: dali em diante, só leitura
            e["sqlite"] = conn
        return e["sqlite"]

    def sql(self, texto: str, eid: str | None = None, fonte: str = "planilha") -> dict:
        from robo import consultas
        consultas.validar_leitura(texto)  # um comando só, SELECT/WITH, nada que altere (mesma regra do painel)
        inicio = time.perf_counter()
        if fonte == "postgres":
            if not (self.cfg.banco or {}).get("habilitado"):
                raise ValueError("O PostgreSQL não está configurado neste computador (python -m robo preparar-pc).")
            from robo.banco import Banco
            r = consultas.executar_texto(Banco(self.cfg.banco, self.cfg.base), texto, LIMITE_LINHAS)
            return {**r, "linhas": [[_json(v) for v in l] for l in r["linhas"]]}
        conn = self._sqlite(eid)
        with self._trava:
            cur = conn.execute(texto)
            colunas = [d[0] for d in cur.description] if cur.description else []
            linhas = cur.fetchmany(LIMITE_LINHAS + 1)
        return {"colunas": colunas, "linhas": [[_json(v) for v in l] for l in linhas[:LIMITE_LINHAS]],
                "truncado": len(linhas) > LIMITE_LINHAS, "duracao": round(time.perf_counter() - inicio, 3)}

    def arquivo(self, eid: str, nome: str) -> Path | None:
        """Só os arquivos da própria entrega (nada de ../ para sair da pasta)."""
        e = self.entregas.get(eid)
        if not e or nome not in {"relatorio.html", "indicadores.xlsx", "base_tratada.xlsx"}:
            return None
        p = e["pasta"] / nome
        return p if p.exists() else None


def _nome_tabela(aba: str) -> str:
    t = re.sub(r"[^a-z0-9_]", "_", str(aba).lower()).strip("_") or "dados"
    return t if not t[0].isdigit() else f"t_{t}"


def _json(v):
    if v is None or isinstance(v, (int, float, str, bool)):
        return None if isinstance(v, float) and v != v else v
    return str(v)


# =============================================================================== servidor HTTP
def _handler(est: Estudio):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso no terminal
            pass

        def _resp(self, codigo: int, corpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, codigo: int, dados: dict):
            self._resp(codigo, json.dumps(dados, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            caminho = urlparse(self.path).path
            if caminho in ("/", "/index.html"):
                return self._resp(200, PAGINA.encode(), "text/html; charset=utf-8")
            m = re.fullmatch(r"/entrega/([0-9a-f]{10})/([a-z_]+\.(?:html|xlsx))", caminho)
            if m:
                p = est.arquivo(m.group(1), unquote(m.group(2)))
                if not p:
                    return self._json(404, {"erro": "arquivo não encontrado"})
                tipo = "text/html; charset=utf-8" if p.suffix == ".html" else \
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                extra = {} if p.suffix == ".html" else {"Content-Disposition": f'attachment; filename="{p.name}"'}
                return self._resp(200, p.read_bytes(), tipo, extra)
            if caminho == "/api/estado":
                return self._json(200, {"postgres": bool((est.cfg.banco or {}).get("habilitado")),
                                        "entregas": [{"id": e["id"], "arquivo": e["arquivo"], "quando": e["quando"]}
                                                     for e in est.entregas.values()]})
            if caminho.startswith("/api/esquema/"):
                return self._json(200, {"tabelas": est.esquema(caminho.rsplit("/", 1)[-1])})
            return self._json(404, {"erro": "não encontrado"})

        def do_POST(self):
            caminho = urlparse(self.path).path
            tamanho = int(self.headers.get("Content-Length") or 0)
            if tamanho > TAMANHO_MAXIMO:
                return self._json(413, {"erro": f"arquivo maior que {TAMANHO_MAXIMO // 2**20} MB"})
            corpo = self.rfile.read(tamanho)
            try:
                if caminho == "/api/tratar":
                    msg = BytesParser(policy=politica_email).parsebytes(
                        b"Content-Type: " + self.headers.get("Content-Type", "").encode() + b"\r\n\r\n" + corpo)
                    arquivo, segmentos = None, None
                    for parte in msg.iter_parts():
                        nome_campo = parte.get_param("name", header="content-disposition")
                        if nome_campo == "arquivo":
                            arquivo = (parte.get_filename(), parte.get_payload(decode=True))
                        elif nome_campo == "segmentos":
                            txt = (parte.get_payload(decode=True) or b"").decode("utf-8").strip()
                            segmentos = [s.strip() for s in txt.split(",") if s.strip()] or None
                    if not arquivo or not arquivo[1]:
                        return self._json(400, {"erro": "nenhum arquivo enviado"})
                    return self._json(200, est.tratar(arquivo[0], arquivo[1], segmentos))
                if caminho == "/api/sql":
                    p = json.loads(corpo or b"{}")
                    return self._json(200, est.sql(p.get("sql", ""), p.get("id"), p.get("fonte", "planilha")))
            except (ValueError, sqlite3.Error) as e:
                return self._json(400, {"erro": str(e)})
            except Exception as e:  # erro inesperado: a tela mostra o motivo, o estúdio continua no ar
                log.exception("Estúdio: falha em %s", caminho)
                return self._json(500, {"erro": f"{type(e).__name__}: {e}"})
            return self._json(404, {"erro": "não encontrado"})
    return H


def servidor(cfg, porta: int = PORTA_PADRAO, pasta: Path | None = None) -> tuple[ThreadingHTTPServer, Estudio]:
    est = Estudio(cfg, pasta)
    return ThreadingHTTPServer(("127.0.0.1", porta), _handler(est)), est


def abrir(cfg, porta: int = PORTA_PADRAO, navegador: bool = True) -> None:
    srv, _ = servidor(cfg, porta)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Estúdio aberto em {url}  (feche esta janela ou aperte Ctrl+C para encerrar)")
    if navegador:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# =============================================================================== a página
PAGINA = r"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Robô de Planilhas — Estúdio</title>
<style>
:root{--p:#1F4E79;--t:#1A1A1A;--s:#5F6B7A;--l:#E3E7ED;--f:#F6F8FB;--r:#C62828;--b:#2E7D32}
*{box-sizing:border-box} body{margin:0;background:var(--f);color:var(--t);font:15px/1.5 "Segoe UI",Arial,sans-serif}
header{background:#fff;border-bottom:1px solid var(--l);padding:14px 20px;display:flex;gap:24px;align-items:center;flex-wrap:wrap}
h1{font-size:19px;margin:0;color:var(--p)} nav button{background:none;border:0;font:inherit;padding:8px 14px;border-radius:8px;cursor:pointer;color:var(--s)}
nav button.ativo{background:var(--f);color:var(--p);font-weight:600}
main{max-width:1100px;margin:0 auto;padding:20px 16px 48px} .aba{display:none} .aba.ativa{display:block}
.caixa{background:#fff;border:1px solid var(--l);border-radius:12px;padding:18px;margin-bottom:16px}
#soltar{border:2px dashed #b9c3d0;border-radius:12px;padding:36px;text-align:center;color:var(--s);cursor:pointer;background:#fff}
#soltar.sobre{border-color:var(--p);background:#eef4fa}
input[type=text],textarea,select{width:100%;padding:9px 10px;border:1px solid var(--l);border-radius:8px;font:inherit}
textarea{font-family:Consolas,monospace;min-height:130px} label{font-size:13px;color:var(--s)}
button.acao{background:var(--p);color:#fff;border:0;border-radius:8px;padding:10px 18px;font:inherit;cursor:pointer}
button.acao:disabled{opacity:.5} .linha{display:flex;gap:12px;flex-wrap:wrap;align-items:end} .linha>*{flex:1;min-width:200px}
.downloads a{margin-right:14px;color:var(--p)} iframe{width:100%;height:75vh;border:1px solid var(--l);border-radius:12px;background:#fff}
table{border-collapse:collapse;width:100%;font-size:13px;background:#fff} th,td{border-bottom:1px solid var(--l);padding:6px 8px;text-align:left}
th{background:var(--f);position:sticky;top:0} .resultado{max-height:60vh;overflow:auto;border:1px solid var(--l);border-radius:8px}
.erro{color:var(--r)} .ok{color:var(--b)} .nota{color:var(--s);font-size:12px} code{background:var(--f);padding:1px 5px;border-radius:4px}
.tab-list span{display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;background:var(--f);border-radius:6px;font-size:12px;cursor:pointer}
</style></head><body>
<header><h1>Robô de Planilhas · Estúdio</h1>
<nav><button class="ativo" data-aba="tratar">1. Tratar planilha</button><button data-aba="sql">2. SQL</button></nav>
<span class="nota">Tudo roda neste computador. A planilha não sai dele.</span></header>
<main>
<section id="tratar" class="aba ativa">
 <div class="caixa">
  <div id="soltar">Arraste a planilha aqui ou <b>clique para escolher</b><br><span class="nota">.xlsx, .xls, .csv — pesquisa (NPS, CSAT, CES), vendas, financeiro, RH, logística…</span></div>
  <input id="arquivo" type="file" accept=".xlsx,.xlsm,.xls,.csv,.txt" hidden>
  <div class="linha" style="margin-top:12px">
   <div><label>Segmentos (opcional, separados por vírgula)</label><input id="segmentos" type="text" placeholder="ex.: regiao, curso, canal"></div>
   <div style="flex:0"><button class="acao" id="enviar" disabled>Tratar e analisar</button></div>
  </div>
  <p id="status" class="nota"></p>
 </div>
 <div id="saida" hidden>
  <div class="caixa"><b>Recomendações</b><ol id="recs"></ol>
   <div class="downloads">Baixar: <a id="d1" target="_blank">relatório (HTML)</a><a id="d2">indicadores.xlsx</a><a id="d3">base tratada.xlsx</a></div>
   <p class="nota">Quer cruzar ou filtrar do seu jeito? Vá na aba <b>2. SQL</b>: os dados tratados já estão lá como tabela.</p></div>
  <iframe id="relatorio" title="Relatório"></iframe>
 </div>
</section>
<section id="sql" class="aba">
 <div class="caixa">
  <div class="linha">
   <div><label>Consultar</label><select id="fonte"></select></div>
  </div>
  <p class="nota" style="margin:10px 0 4px">Tabelas (clique para inserir):</p><div id="tabelas" class="tab-list"><span class="nota">Envie uma planilha na aba 1.</span></div>
  <p class="nota" style="margin:12px 0 4px">Sua consulta (só leitura: SELECT ou WITH)</p>
  <textarea id="consulta" spellcheck="false">-- exemplo: as 20 primeiras linhas
SELECT * FROM dados LIMIT 20</textarea>
  <div class="linha" style="margin-top:10px"><div style="flex:0"><button class="acao" id="rodar">Executar (Ctrl+Enter)</button></div><div id="sqlstatus" class="nota"></div></div>
 </div>
 <div class="resultado" id="resultado"></div>
</section>
</main>
<script>
const $=s=>document.querySelector(s); let atual=null, arquivo=null;
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('ativo',x===b));
 document.querySelectorAll('.aba').forEach(a=>a.classList.toggle('ativa',a.id===b.dataset.aba));});
const solto=$('#soltar');
solto.onclick=()=>$('#arquivo').click();
$('#arquivo').onchange=e=>escolher(e.target.files[0]);
['dragover','dragenter'].forEach(ev=>solto.addEventListener(ev,e=>{e.preventDefault();solto.classList.add('sobre')}));
['dragleave','drop'].forEach(ev=>solto.addEventListener(ev,e=>{e.preventDefault();solto.classList.remove('sobre')}));
solto.addEventListener('drop',e=>escolher(e.dataTransfer.files[0]));
function escolher(f){if(!f)return;arquivo=f;solto.innerHTML='Arquivo: <b></b> <span class="nota">(clique para trocar)</span>';solto.querySelector('b').textContent=f.name;$('#enviar').disabled=false}
function esc(t){const d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML}
$('#enviar').onclick=async()=>{
 const fd=new FormData();fd.append('arquivo',arquivo);fd.append('segmentos',$('#segmentos').value);
 $('#enviar').disabled=true;$('#status').className='nota';$('#status').textContent='Lendo, limpando, padronizando e analisando… (alguns segundos)';
 try{const r=await fetch('/api/tratar',{method:'POST',body:fd});const j=await r.json();
  if(!r.ok)throw new Error(j.erro||'falhou');
  atual=j.id;$('#status').className=j.ok?'ok':'erro';
  $('#status').textContent=j.ok?`Pronto: ${j.linhas.toLocaleString('pt-BR')} linhas tratadas e analisadas.`:'A planilha teve problemas: veja o relatório.';
  $('#recs').innerHTML=j.recomendacoes.map(x=>'<li>'+esc(x).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')+'</li>').join('');
  $('#d1').href=`/entrega/${j.id}/relatorio.html`;$('#d2').href=`/entrega/${j.id}/indicadores.xlsx`;$('#d3').href=`/entrega/${j.id}/base_tratada.xlsx`;
  $('#d3').style.display=j.arquivos.includes('base_tratada.xlsx')?'':'none';$('#d2').style.display=j.arquivos.includes('indicadores.xlsx')?'':'none';
  $('#relatorio').src=`/entrega/${j.id}/relatorio.html`;$('#saida').hidden=false;
  await carregarFontes();mostrarTabelas(j.tabelas);
  if(j.tabelas.length)$('#consulta').value=`-- ${j.arquivo}: as 20 primeiras linhas\nSELECT * FROM ${j.tabelas[0].tabela} LIMIT 20`;
 }catch(e){$('#status').className='erro';$('#status').textContent='Erro: '+e.message}
 $('#enviar').disabled=false};
async function carregarFontes(){const r=await (await fetch('/api/estado')).json();const s=$('#fonte');s.innerHTML='';
 r.entregas.slice().reverse().forEach(e=>s.add(new Option(`Planilha tratada: ${e.arquivo} (${e.quando})`,'p:'+e.id)));
 if(r.postgres)s.add(new Option('PostgreSQL do robô (somente leitura)','pg'));
 if(atual)s.value='p:'+atual;}
$('#fonte').onchange=async()=>{const v=$('#fonte').value;if(v.startsWith('p:')){atual=v.slice(2);const r=await (await fetch('/api/esquema/'+atual)).json();mostrarTabelas(r.tabelas)}
 else $('#tabelas').innerHTML='<span class="nota">PostgreSQL: use schema.tabela (ex.: tratado.minha_base). Só leitura.</span>'};
function mostrarTabelas(t){$('#tabelas').innerHTML=t.map(x=>`<span title="${esc(x.colunas.join(', '))}">${esc(x.tabela)} (${x.linhas})</span>`).join('')||'<span class="nota">Nenhuma tabela.</span>';
 $('#tabelas').querySelectorAll('span').forEach((s,i)=>s.onclick=()=>{const ta=$('#consulta');ta.setRangeText(t[i].tabela,ta.selectionStart,ta.selectionEnd,'end');ta.focus()})}
async function rodar(){const v=$('#fonte').value||'';const corpo={sql:$('#consulta').value,fonte:v==='pg'?'postgres':'planilha',id:v.startsWith('p:')?v.slice(2):atual};
 $('#sqlstatus').className='nota';$('#sqlstatus').textContent='Executando…';
 try{const r=await fetch('/api/sql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(corpo)});const j=await r.json();
  if(!r.ok)throw new Error(j.erro);
  $('#sqlstatus').className='ok';$('#sqlstatus').textContent=`${j.linhas.length} linha(s) em ${j.duracao}s${j.truncado?' — mostrando as primeiras 500':''}`;
  $('#resultado').innerHTML='<table><tr>'+j.colunas.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>'+j.linhas.map(l=>'<tr>'+l.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</table>';
 }catch(e){$('#sqlstatus').className='erro';$('#sqlstatus').textContent='Erro: '+e.message;$('#resultado').innerHTML=''}}
$('#rodar').onclick=rodar;$('#consulta').onkeydown=e=>{if(e.ctrlKey&&e.key==='Enter')rodar()};
carregarFontes();
</script></body></html>"""
