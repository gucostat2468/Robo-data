"""Estúdio (robo/estudio.py): a interface simples no navegador.

O que precisa ser verdade:
  - enviar uma planilha devolve recomendações, o relatório e os downloads;
  - a aba SQL consulta os dados TRATADOS (SQLite em memória) e só lê (DELETE/DROP/; são recusados);
  - só os arquivos da própria entrega são servidos (nada de ../);
  - o servidor só escuta em 127.0.0.1.
"""

import json
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pandas as pd
import pytest

from robo import estudio


@pytest.fixture
def no_ar(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    srv, est = estudio.servidor(cfg, 0, tmp_path / "estudio")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", srv
    srv.shutdown()
    srv.server_close()


def _post_arquivo(url, nome, dados, segmentos="", alvo=""):
    b = uuid.uuid4().hex
    corpo = (f"--{b}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"{nome}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n").encode() + dados + \
        (f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"segmentos\"\r\n\r\n{segmentos}\r\n"
         f"--{b}\r\nContent-Disposition: form-data; name=\"alvo\"\r\n\r\n{alvo}\r\n--{b}--\r\n").encode()
    req = urllib.request.Request(url + "/api/tratar", corpo, {"Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _sql(url, eid, texto):
    req = urllib.request.Request(url + "/api/sql", json.dumps({"sql": texto, "id": eid}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _planilha(tmp_path) -> bytes:
    arq = tmp_path / "pesquisa.xlsx"
    pd.DataFrame({"id_resposta": range(120), "regiao": ["Sul", "Norte", "Sudeste"] * 40,
                  "nota_nps": [10, 9, 3, 8, 7, 10] * 20}).to_excel(arq, index=False)
    return arq.read_bytes()


def teste_envia_planilha_e_recebe_relatorio(no_ar, tmp_path):
    url, srv = no_ar
    assert srv.server_address[0] == "127.0.0.1"
    with urllib.request.urlopen(url + "/", timeout=10) as r:
        assert "Tratar planilha" in r.read().decode()
    j = _post_arquivo(url, "pesquisa.xlsx", _planilha(tmp_path))
    assert j["ok"] and j["linhas"] == 120 and j["recomendacoes"] and j["tabelas"]
    with urllib.request.urlopen(f"{url}/entrega/{j['id']}/relatorio.html", timeout=10) as r:
        assert ">NPS<" in r.read().decode()
    with urllib.request.urlopen(f"{url}/entrega/{j['id']}/base_tratada.xlsx", timeout=10) as r:
        assert r.headers["Content-Disposition"].startswith("attachment")


def teste_sql_nos_dados_tratados_e_so_leitura(no_ar, tmp_path):
    url, _ = no_ar
    j = _post_arquivo(url, "pesquisa.xlsx", _planilha(tmp_path))
    t = j["tabelas"][0]["tabela"]
    st, r = _sql(url, j["id"], f"SELECT regiao, COUNT(*) AS n FROM {t} GROUP BY regiao ORDER BY regiao")
    assert st == 200 and r["colunas"] == ["regiao", "n"] and r["linhas"] == [["Norte", 40], ["Sudeste", 40], ["Sul", 40]]
    for ruim in (f"DELETE FROM {t}", f"DROP TABLE {t}", f"SELECT 1; DELETE FROM {t}"):
        st, r = _sql(url, j["id"], ruim)
        assert st == 400 and "recusada" in r["erro"], ruim
    st, r = _sql(url, j["id"], f"SELECT COUNT(*) FROM {t}")
    assert r["linhas"] == [[120]]  # nada foi apagado


def teste_so_serve_arquivos_da_propria_entrega(no_ar, tmp_path):
    url, _ = no_ar
    j = _post_arquivo(url, "pesquisa.xlsx", _planilha(tmp_path))
    for caminho in (f"/entrega/{j['id']}/../../etc/passwd", f"/entrega/{j['id']}/pesquisa.xlsx", "/entrega/0000000000/relatorio.html"):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + caminho, timeout=10)
        assert e.value.code == 404


def teste_formato_errado_explica(no_ar):
    url, _ = no_ar
    with pytest.raises(urllib.error.HTTPError) as e:
        _post_arquivo(url, "foto.png", b"\x89PNG")
    assert e.value.code == 400 and "Formato" in json.loads(e.value.read())["erro"]


def teste_tudo_fica_salvo_com_certificado_e_historico_do_sql(no_ar, tmp_path):
    """Cada envio vira uma pasta permanente: original, base tratada, indicadores, relatório, manifesto (certificado
    com SHA-256) e o histórico das consultas SQL."""
    import hashlib
    url, _ = no_ar
    dados = _planilha(tmp_path)
    j = _post_arquivo(url, "pesquisa.xlsx", dados)
    pasta = Path(j["pasta"])
    assert pasta.parent == tmp_path / "estudio"
    assert {"original_pesquisa.xlsx", "base_tratada.xlsx", "indicadores.xlsx", "relatorio.html",
            "manifesto.json"} <= {p.name for p in pasta.iterdir()}
    man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    assert man["todas_ok"] and man["original"]["sha256"] == hashlib.sha256(dados).hexdigest()
    assert any("NPS" in c["conferencia"] and c["ok"] for c in man["conferencias"])
    assert man["arquivos"]["relatorio.html"]["sha256"] == hashlib.sha256((pasta / "relatorio.html").read_bytes()).hexdigest()
    _sql(url, j["id"], "SELECT COUNT(*) FROM dados")
    _sql(url, j["id"], "DELETE FROM dados")
    hist = (pasta / "consultas_sql.sql").read_text(encoding="utf-8")
    assert "SELECT COUNT(*) FROM dados" in hist and "1 linha(s)" in hist and "ERRO" in hist
    with urllib.request.urlopen(url + "/api/estado", timeout=10) as r:
        est = json.loads(r.read())
    assert est["entregas"][0]["id"] == j["id"] and est["entregas"][0]["conferido"] is True


def teste_alvo_de_ml_e_modelo_power_bi(no_ar, tmp_path):
    """Com a coluna alvo preenchida, a entrega traz o resultado do ML com o veredito, os arquivos do Power BI ficam
    disponíveis para baixar e as tabelas do modelo estrela entram no SQL."""
    pytest.importorskip("sklearn")
    url, _ = no_ar
    j = _post_arquivo(url, "pesquisa.xlsx", _planilha(tmp_path), alvo="regiao")
    assert j["ml"]["ok"] and j["ml"]["alvo"] == "regiao" and isinstance(j["ml"]["vale"], bool) and j["ml"]["veredito"]
    for nome in ("modelo_powerbi.xlsx", "medidas_dax.txt"):
        with urllib.request.urlopen(f"{url}/entrega/{j['id']}/{nome}", timeout=10) as r:
            assert r.status == 200
    tabelas = {t["tabela"] for t in j["tabelas"]}
    assert "dados" in tabelas and any(t.startswith("fato_") for t in tabelas) and "dim_regiao" in tabelas
