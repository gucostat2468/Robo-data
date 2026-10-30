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
    """O estado do estúdio. Cada entrega fica numa pasta própria, para sempre, em entrega.pasta_entregas()
    (Documentos/Robo de Planilhas/Entregas): original, base tratada, indicadores, relatório, certificado de conferência
    (manifesto.json) e o histórico das consultas SQL feitas sobre ela."""

    def __init__(self, cfg, pasta: Path | None = None):
        from robo import entrega
        self.cfg = cfg
        self.pasta = Path(pasta) if pasta else entrega.pasta_entregas(cfg)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._sqlite: dict[str, sqlite3.Connection] = {}
        self._trava = threading.Lock()

    # ------------------------------------------------------------------ entregas guardadas
    def _pasta_da(self, eid: str) -> Path | None:
        """Só pastas de entrega que estão DENTRO da pasta de entregas (nada de ../)."""
        if not re.fullmatch(r"Entrega_[\w.\-]+", eid or ""):
            return None
        p = self.pasta / eid
        return p if p.is_dir() and p.parent.resolve() == self.pasta.resolve() else None

    def historico(self, limite: int = 30) -> list[dict]:
        saida = []
        for p in sorted((x for x in self.pasta.glob("Entrega_*") if x.is_dir()), key=lambda x: x.stat().st_mtime,
                        reverse=True)[:limite]:
            man = {}
            try:
                man = json.loads((p / "manifesto.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            saida.append({"id": p.name, "arquivo": (man.get("original") or {}).get("nome") or p.name,
                          "quando": time.strftime("%d/%m %H:%M", time.localtime(p.stat().st_mtime)),
                          "conferido": man.get("todas_ok"), "linhas": man.get("linhas")})
        return saida

    # ------------------------------------------------------------------ tratar
    def tratar(self, nome: str, dados: bytes, segmentos: list[str] | None = None, alvo: str | None = None) -> dict:
        from robo import entrega
        nome = Path(nome or "planilha.xlsx").name
        if Path(nome).suffix.lower() not in EXTENSOES:
            raise ValueError(f"Formato não suportado: envie {', '.join(sorted(EXTENSOES))}")
        with tempfile.TemporaryDirectory(prefix="robo_estudio_") as tmp:
            entrada = Path(tmp) / nome
            entrada.write_bytes(dados)
            r = entrega.entregar(self.cfg, entrada, self.pasta, segmentos, alvo)  # copia o original para a entrega
        eid = Path(r["pasta"]).name
        return {"id": eid, "ok": r["ok"], "arquivo": nome, "recomendacoes": r["recomendacoes"], "erros": r["erros"],
                "linhas": r["linhas"], "arquivos": r["arquivos"], "tabelas": self.esquema(eid), "pasta": r["pasta"],
                "conferencias": r.get("conferencias") or [], "ml": r.get("ml"), "qualidade": r.get("qualidade")}

    def _tabelas(self, eid: str) -> dict[str, pd.DataFrame]:
        p = self._pasta_da(eid)
        if not p or not (p / "base_tratada.xlsx").exists():
            return {}
        saida = {_nome_tabela(aba): df for aba, df in pd.read_excel(p / "base_tratada.xlsx", sheet_name=None).items()}
        if (p / "modelo_powerbi.xlsx").exists():  # o modelo estrela também vira tabela (JOIN fato × dimensões)
            for aba, df in pd.read_excel(p / "modelo_powerbi.xlsx", sheet_name=None).items():
                saida.setdefault(_nome_tabela(aba), df)
        return saida

    def esquema(self, eid: str) -> list[dict]:
        return [{"tabela": t, "linhas": len(df), "colunas": [str(c) for c in df.columns]}
                for t, df in self._tabelas(eid).items()]

    # ------------------------------------------------------------------ SQL
    def _conexao(self, eid: str) -> sqlite3.Connection:
        with self._trava:
            if eid not in self._sqlite:
                tabelas = self._tabelas(eid)
                if not tabelas:
                    raise ValueError("Envie uma planilha primeiro (aba Tratar planilha) ou escolha uma entrega.")
                conn = sqlite3.connect(":memory:", check_same_thread=False)
                for t, df in tabelas.items():
                    df.to_sql(t, conn, index=False)
                conn.execute("PRAGMA query_only = ON")  # depois de carregar: dali em diante, só leitura
                self._sqlite[eid] = conn
            return self._sqlite[eid]

    def _registrar_sql(self, eid: str | None, texto: str, resultado: str) -> None:
        """Toda consulta fica registrada na pasta da entrega (consultas_sql.sql): o que foi perguntado e o que veio."""
        p = self._pasta_da(eid or "")
        if not p:
            return
        with open(p / "consultas_sql.sql", "a", encoding="utf-8") as f:
            f.write(f"-- {time.strftime('%d/%m/%Y %H:%M:%S')} · {resultado}\n{texto.strip()}\n;\n\n")

    def sql(self, texto: str, eid: str | None = None, fonte: str = "planilha") -> dict:
        from robo import consultas
        try:
            consultas.validar_leitura(texto)  # um comando só, SELECT/WITH, nada que altere (mesma regra do painel)
            inicio = time.perf_counter()
            if fonte == "postgres":
                if not (self.cfg.banco or {}).get("habilitado"):
                    raise ValueError("O PostgreSQL não está configurado neste computador (python -m robo preparar-pc).")
                from robo.banco import Banco
                r = consultas.executar_texto(Banco(self.cfg.banco, self.cfg.base), texto, LIMITE_LINHAS)
                r = {**r, "linhas": [[_json(v) for v in l] for l in r["linhas"]]}
            else:
                conn = self._conexao(eid)
                with self._trava:
                    cur = conn.execute(texto)
                    colunas = [d[0] for d in cur.description] if cur.description else []
                    linhas = cur.fetchmany(LIMITE_LINHAS + 1)
                r = {"colunas": colunas, "linhas": [[_json(v) for v in l] for l in linhas[:LIMITE_LINHAS]],
                     "truncado": len(linhas) > LIMITE_LINHAS, "duracao": round(time.perf_counter() - inicio, 3)}
        except (ValueError, sqlite3.Error) as e:
            self._registrar_sql(eid, texto, f"ERRO: {e}")
            raise
        self._registrar_sql(eid, texto, f"{len(r['linhas'])} linha(s) · fonte {fonte}")
        return r

    def arquivo(self, eid: str, nome: str) -> Path | None:
        """Só os arquivos da própria entrega, pelo nome exato."""
        p = self._pasta_da(eid)
        if not p or nome not in {"relatorio.html", "indicadores.xlsx", "base_tratada.xlsx", "manifesto.json",
                                 "consultas_sql.sql", "modelo_powerbi.xlsx", "medidas_dax.txt"}:
            return None
        f = p / nome
        return f if f.exists() else None

    def abrir_pasta(self, eid: str | None = None) -> str:
        """Abre a pasta da entrega (ou a de entregas) no Explorador de Arquivos deste computador."""
        import os
        import subprocess
        import sys
        alvo = self._pasta_da(eid or "") or self.pasta
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(alvo))  # noqa: S606 (só abre a pasta, local)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(alvo)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
        return str(alvo)


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
            m = re.fullmatch(r"/entrega/([^/]+)/([a-z_]+\.(?:html|xlsx|json|sql|txt))", caminho)
            if m:
                p = est.arquivo(m.group(1), unquote(m.group(2)))
                if not p:
                    return self._json(404, {"erro": "arquivo não encontrado"})
                tipo = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                        ".sql": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8"}.get(p.suffix,
                                                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                extra = {"Content-Disposition": f'attachment; filename="{p.name}"'} if p.suffix == ".xlsx" else {}
                return self._resp(200, p.read_bytes(), tipo, extra)
            if caminho == "/api/estado":
                return self._json(200, {"postgres": bool((est.cfg.banco or {}).get("habilitado")),
                                        "pasta": str(est.pasta), "entregas": est.historico()})
            if caminho.startswith("/api/esquema/"):
                return self._json(200, {"tabelas": est.esquema(unquote(caminho.rsplit("/", 1)[-1]))})
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
                    arquivo, segmentos, alvo = None, None, None
                    for parte in msg.iter_parts():
                        nome_campo = parte.get_param("name", header="content-disposition")
                        if nome_campo == "arquivo":
                            arquivo = (parte.get_filename(), parte.get_payload(decode=True))
                        elif nome_campo == "segmentos":
                            txt = (parte.get_payload(decode=True) or b"").decode("utf-8").strip()
                            segmentos = [s.strip() for s in txt.split(",") if s.strip()] or None
                        elif nome_campo == "alvo":
                            alvo = (parte.get_payload(decode=True) or b"").decode("utf-8").strip() or None
                    if not arquivo or not arquivo[1]:
                        return self._json(400, {"erro": "nenhum arquivo enviado"})
                    return self._json(200, est.tratar(arquivo[0], arquivo[1], segmentos, alvo))
                if caminho == "/api/abrir":
                    p = json.loads(corpo or b"{}")
                    return self._json(200, {"pasta": est.abrir_pasta(p.get("id"))})
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
button.link{background:none;border:0;color:var(--p);text-decoration:underline;cursor:pointer;font:inherit;padding:0}
.hist{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;margin-top:8px}
.hist div{border:1px solid var(--l);border-radius:8px;padding:8px 10px;cursor:pointer;font-size:13px} .hist div:hover{background:var(--f)}
.certok{background:#eaf5ea;color:var(--b);border-radius:8px;padding:8px 12px;margin-bottom:10px}
.certno{background:#fdecea;color:var(--r);border-radius:8px;padding:8px 12px;margin-bottom:10px}
.tab-list span{display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;background:var(--f);border-radius:6px;font-size:12px;cursor:pointer}
</style></head><body>
<header><h1>Robô de Planilhas · Estúdio</h1>
<nav><button class="ativo" data-aba="tratar">1. Tratar planilha</button><button data-aba="sql">2. SQL</button></nav>
<span class="nota">Tudo roda neste computador. Cada entrega fica salva em <b id="pastaraiz"></b>
 <button class="link" id="abrirraiz">abrir</button></span></header>
<main>
<section id="tratar" class="aba ativa">
 <div class="caixa">
  <div id="soltar">Arraste a planilha aqui ou <b>clique para escolher</b><br><span class="nota">.xlsx, .xls, .csv — vendas, financeiro, RH, logística, estoque, marketing, pesquisa…</span></div>
  <input id="arquivo" type="file" accept=".xlsx,.xlsm,.xls,.csv,.txt" hidden>
  <div class="linha" style="margin-top:12px">
   <div><label>Segmentos (opcional, separados por vírgula)</label><input id="segmentos" type="text" placeholder="ex.: regiao, curso, canal"></div>
   <div><label>Machine Learning: coluna a prever (opcional)</label><input id="alvo" type="text" placeholder="ex.: cancelou, valor_venda"></div>
   <div style="flex:0"><button class="acao" id="enviar" disabled>Tratar e analisar</button></div>
  </div>
  <p id="status" class="nota"></p>
 </div>
 <div class="caixa"><b>Entregas salvas</b> <span class="nota">(clique para abrir de novo)</span><div id="historico" class="hist"></div></div>
 <div id="saida" hidden>
  <div class="caixa"><div id="cert"></div><b>Recomendações</b><ol id="recs"></ol>
   <div class="downloads">Baixar: <a id="d1" target="_blank">relatório (HTML)</a><a id="d2">indicadores.xlsx</a><a id="d3">base tratada.xlsx</a><a id="d4" target="_blank">certificado (manifesto.json)</a><a id="d5">modelo Power BI (.xlsx)</a><a id="d6" target="_blank">medidas DAX</a></div>
   <p class="nota">Salvo em <b id="pastaent"></b> <button class="link" id="abrirent">abrir a pasta</button> — original, base tratada, indicadores, relatório, certificado e o histórico do SQL.</p>
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
 const fd=new FormData();fd.append('arquivo',arquivo);fd.append('segmentos',$('#segmentos').value);fd.append('alvo',$('#alvo').value);
 $('#enviar').disabled=true;$('#status').className='nota';$('#status').textContent='Lendo, limpando, padronizando, conferindo e analisando… ('+($('#alvo').value?'com Machine Learning: até 1 minuto':'alguns segundos')+')';
 try{const r=await fetch('/api/tratar',{method:'POST',body:fd});const j=await r.json();
  if(!r.ok)throw new Error(j.erro||'falhou');
  $('#status').className=j.ok?'ok':'erro';
  $('#status').textContent=j.ok?`Pronto: ${j.linhas.toLocaleString('pt-BR')} linhas tratadas e analisadas.`:'A planilha teve problemas: veja o relatório.';
  await mostrarEntrega(j.id,j.arquivo,j.recomendacoes,j.conferencias,j.pasta);
 }catch(e){$('#status').className='erro';$('#status').textContent='Erro: '+e.message}
 $('#enviar').disabled=false};
async function mostrarEntrega(id,arquivo,recs,conf,pasta){
 atual=id;const base=`/entrega/${encodeURIComponent(id)}/`;
 if(!recs){try{const m=await (await fetch(base+'manifesto.json')).json();recs=m.recomendacoes||[];conf=m.conferencias||[];arquivo=(m.original||{}).nome||id}catch(e){recs=[];conf=[]}}
 const ok=conf.filter(c=>c.ok).length;
 $('#cert').className=conf.length&&ok===conf.length?'certok':'certno';
 $('#cert').textContent=conf.length?`Certificado de conferência: ${ok} de ${conf.length} conferências batem${ok===conf.length?' ✓':' — veja no relatório'}`:'Sem certificado (entrega antiga ou planilha não lida)';
 $('#recs').innerHTML=recs.map(x=>'<li>'+esc(x).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')+'</li>').join('');
 $('#d1').href=base+'relatorio.html';$('#d2').href=base+'indicadores.xlsx';$('#d3').href=base+'base_tratada.xlsx';$('#d4').href=base+'manifesto.json';$('#d5').href=base+'modelo_powerbi.xlsx';$('#d6').href=base+'medidas_dax.txt';
 $('#pastaent').textContent=pasta||id;$('#relatorio').src=base+'relatorio.html';$('#saida').hidden=false;
 await carregarFontes();const r=await (await fetch('/api/esquema/'+encodeURIComponent(id))).json();mostrarTabelas(r.tabelas);
 if(r.tabelas.length)$('#consulta').value=`-- ${arquivo}: as 20 primeiras linhas\nSELECT * FROM ${r.tabelas[0].tabela} LIMIT 20`;}
$('#abrirent').onclick=()=>fetch('/api/abrir',{method:'POST',body:JSON.stringify({id:atual})});
$('#abrirraiz').onclick=()=>fetch('/api/abrir',{method:'POST',body:'{}'});
async function carregarFontes(){const r=await (await fetch('/api/estado')).json();const s=$('#fonte');s.innerHTML='';
 $('#pastaraiz').textContent=r.pasta;
 $('#historico').innerHTML=r.entregas.map(e=>`<div data-id="${esc(e.id)}"><b>${esc(e.arquivo)}</b><br><span class="nota">${esc(e.quando)} · ${e.linhas??'?'} linhas · ${e.conferido?'conferido ✓':'sem certificado'}</span></div>`).join('')||'<span class="nota">Nenhuma ainda.</span>';
 $('#historico').querySelectorAll('div[data-id]').forEach(d=>d.onclick=()=>mostrarEntrega(d.dataset.id));
 r.entregas.forEach(e=>s.add(new Option(`Planilha tratada: ${e.arquivo} (${e.quando})`,'p:'+e.id)));
 if(r.postgres)s.add(new Option('PostgreSQL do robô (somente leitura)','pg'));
 if(atual)s.value='p:'+atual;}
$('#fonte').onchange=async()=>{const v=$('#fonte').value;if(v.startsWith('p:')){atual=v.slice(2);const r=await (await fetch('/api/esquema/'+encodeURIComponent(atual))).json();mostrarTabelas(r.tabelas)}
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
