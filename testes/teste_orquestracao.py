"""Equipe de orquestração (Airflow): fluxos coerentes, DAG gerada e conferida, SLA das rotinas, trava entre programas
e a competência de treino 'orquestracao'."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from robo import orquestracao, rotinas, ti, treino
from robo.comandos import principal


def _cfg_arquivo(tmp_path, cfg):
    caminho = tmp_path / "config.yaml"
    caminho.write_text(yaml.safe_dump(cfg.dados, allow_unicode=True), encoding="utf-8")
    return caminho


def teste_fluxos_atuais_sem_problema_e_toda_rotina_tem_funcao(cfg_factory):
    cfg = cfg_factory()
    assert orquestracao.validar_fluxos() == []
    for nome in rotinas.ROTINAS:
        assert callable(rotinas.funcao(cfg, nome))
    with pytest.raises(KeyError):
        rotinas.funcao(cfg, "nao_existe")


def teste_validacao_recusa_desenho_ruim():
    ruins = orquestracao.validar_fluxos({
        "a": {"cron": "*/5 * * * *", "a_cada_min": 5, "rotinas": ["treino", "inventada"]},
        "b": {"cron": "*/10 * * * *", "a_cada_min": 15, "rotinas": ["treino"]},
        "c": {"cron": "0 * * * *", "a_cada_min": 60, "rotinas": ["ronda_ti"]},
    })
    texto = " | ".join(ruins)
    assert "inventada não existe" in texto
    assert "dois fluxos" in texto                        # treino em a e b
    assert "não bate" in texto                           # b: cron de 10 com 'a cada 15'
    assert "ronda_ti" in texto and "ficaria atrasada" in texto  # ronda precisa de 30 min, fluxo de 60
    assert "backup não está em nenhum fluxo" in texto


def teste_caminho_wsl_e_comando():
    assert orquestracao.caminho_wsl(r"C:\Users\Gustavo Costa\Robo-data") == "/mnt/c/Users/Gustavo Costa/Robo-data"
    cmd = orquestracao.comando_rotina(r"C:\Users\Gustavo Costa\Robo-data", r"C:\Python313\python.exe", True)
    assert cmd == "cd '/mnt/c/Users/Gustavo Costa/Robo-data' && /mnt/c/Python313/python.exe -m robo rotina"


def teste_dag_gerada_compila_e_desatualizacao_e_apontada(cfg_factory, tmp_path):
    cfg = cfg_factory(rotinas={"dag_airflow": str(tmp_path / "dags" / "robo_empresa.py")})
    destino = orquestracao.destino_padrao(cfg)
    assert destino.parent == tmp_path / "dags"           # nunca escreve na pasta do projeto durante o teste
    r = orquestracao.gerar_dag(cfg, wsl=False)
    texto = destino.read_text(encoding="utf-8")
    compile(texto, str(destino), "exec")
    assert set(r["dags"]) == set(orquestracao.FLUXOS) and "-m robo rotina" in r["comando"]
    assert ti.chk_fluxos(cfg) == []                      # DAG igual ao desenho atual
    destino.write_text(texto.replace(f'ASSINATURA = "{r["assinatura"]}"', 'ASSINATURA = "0000"'), encoding="utf-8")
    assert any("desatualizada" in a for a in ti.chk_fluxos(cfg))
    destino.write_text("# editada à mão\n", encoding="utf-8")
    assert any("editada à mão" in a for a in ti.chk_fluxos(cfg))


def _cenario_base():
    cen = {"sessao_min_atras": 600, "execucoes": [],
           "estado": [{"nome": n, "verif_min_atras": 0.1, "ultimo_status": "fez"} for n in rotinas.ROTINAS]}
    for nome in ("backup", "pdca", "licoes", "estudo"):
        cen["execucoes"] += [{"nome": nome, "fim_min_atras": 300 - 30 * i, "segundos": 10, "status": "fez"} for i in range(8)]
    return cen


def teste_sla_aponta_exatamente_o_plantado(cfg_factory):
    cfg = cfg_factory()
    cen = _cenario_base()
    next(e for e in cen["estado"] if e["nome"] == "backup")["verif_min_atras"] = 24 * 60 * 2      # atrasada (> 1,5 × 24 h)
    next(e for e in cen["estado"] if e["nome"] == "estudo")["verif_min_atras"] = 84 * 60 * 1.2    # perto, mas dentro
    cen["execucoes"].append({"nome": "pdca", "fim_min_atras": 1, "segundos": 4, "status": "erro"})
    cen["execucoes"].append({"nome": "licoes", "fim_min_atras": 1, "segundos": 200, "status": "fez"})   # lenta
    cen["execucoes"].append({"nome": "estudo", "fim_min_atras": 5, "segundos": 4, "status": "erro"})   # erro já resolvido
    cen["execucoes"].append({"nome": "estudo", "fim_min_atras": 1, "segundos": 45, "status": "fez"})   # 4,5× mas < +60 s
    orquestracao.gravar_cenario(cfg, cen)
    r = orquestracao.analisar_sla(cfg)
    assert (r["atrasadas"], r["com_erro"], r["lentas"]) == (["backup"], ["pdca"], ["licoes"]), r
    assert r["falhas_24h"] == {"pdca": 1, "estudo": 1} and r["responsaveis"]["backup"] == "dba"
    assert "backup" in orquestracao.texto_sla(r)
    with pytest.raises(RuntimeError):                    # nunca planta cenário num banco que já tem execuções
        orquestracao.gravar_cenario(cfg, cen)


def teste_carencia_ao_abrir_e_computador_novo(cfg_factory):
    cfg = cfg_factory()
    assert orquestracao.analisar_sla(cfg)["ok"]          # nunca aberto: nada contra o que medir
    cen = {"sessao_min_atras": 5, "execucoes": [], "estado": []}
    orquestracao.gravar_cenario(cfg, cen)
    r = orquestracao.analisar_sla(cfg)
    assert r["carencia_abertura"] and not r["atrasadas"]


def teste_trava_entre_programas_e_saida_99(cfg_factory, tmp_path):
    cfg = cfg_factory()
    cfg.criar_pastas()
    caminho = _cfg_arquivo(tmp_path, cfg)
    raiz = Path(__file__).resolve().parents[1]
    segura = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(raiz)!r})
        from robo.config import carregar_config
        from robo import rotinas
        cfg = carregar_config({str(caminho)!r})
        with rotinas._trava_entre_programas(cfg, "pdca") as ok:
            print("TRAVADO" if ok else "FALHOU", flush=True)
            time.sleep(30)
    """)
    outro = subprocess.Popen([sys.executable, "-c", segura], stdout=subprocess.PIPE, text=True)
    try:
        assert outro.stdout.readline().strip() == "TRAVADO"
        chamadas = []
        r = rotinas.executar(cfg, "pdca", lambda: chamadas.append(1))
        assert r == {"em_andamento": True, "rotina": "pdca", "outro_programa": True} and not chamadas
        assert principal(["--config", str(caminho), "rotina", "pdca"]) == 99
    finally:
        outro.kill()
        outro.wait()
    assert principal(["--config", str(caminho), "rotina", "pdca"]) == 0   # o outro programa morreu: a trava foi solta


def teste_comando_rotina_devolve_1_no_erro(cfg_factory, tmp_path, monkeypatch):
    cfg = cfg_factory()
    cfg.criar_pastas()
    caminho = _cfg_arquivo(tmp_path, cfg)

    def quebra():
        raise RuntimeError("falha de propósito")
    monkeypatch.setattr(rotinas, "funcao", lambda c, nome: quebra)
    assert principal(["--config", str(caminho), "rotina", "pdca"]) == 1
    assert principal(["--config", str(caminho), "rotina", "nao_existe"]) == 2
    assert next(e for e in rotinas.estado(cfg) if e["nome"] == "pdca")["ultimo_status"] == "erro"


def teste_equipe_de_airflow_no_quinto_andar_e_provas():
    ids = {"airflow_especialista", "airflow_pleno", "airflow_estagiario"}
    assert ids <= set(ti.POR_ID)
    provas = ti.provas_ti()
    for pid in ids:
        assert provas[pid] and all(ok for _, ok in provas[pid]), provas[pid]


def teste_competencia_orquestracao_nos_5_niveis(cfg_factory):
    cfg = cfg_factory()
    cfg.criar_pastas()
    assert "orquestracao" in treino.competencias_de("airflow_pleno", cfg)
    for nivel in range(1, 6):
        caso = treino.criar_caso(cfg, "orquestracao", nivel, semente=40 + nivel)
        assert caso["estado"] == "validado", caso.get("revisao")
        r = treino.tentar(cfg, "airflow_pleno", "orquestracao", caso, f"T{nivel}")
        assert r["acertou"], (nivel, r["detalhe"])


def teste_revisor_reprova_gabarito_errado(cfg_factory, tmp_path):
    from robo.treino_casos import CATALOGO
    cfg = cfg_factory()
    c = CATALOGO["orquestracao"]
    caso = c.gerar(4, 7, tmp_path, cfg)
    caso["nivel"] = 4
    assert c.conferir(caso, cfg) == []
    caso["gabarito"]["lentas"] = []                      # gabarito adulterado
    assert any("lentas" in p for p in c.conferir(caso, cfg))
    errado = {"dados": {"atrasadas": caso["gabarito"]["atrasadas"], "com_erro": [], "lentas": ["backup"]}}
    acertou, nota, tipo, _ = c.corrigir({**caso, "gabarito": {**caso["gabarito"], "lentas": []}}, errado)
    assert not acertou and 0 < nota < 1


@pytest.mark.skipif(not os.environ.get("ROBO_TESTE_AIRFLOW_PYTHON"), reason="sem Apache Airflow instalado para o teste")
def teste_dag_carrega_no_airflow_de_verdade(cfg_factory, tmp_path):
    cfg = cfg_factory()
    pasta = tmp_path / "dags"
    orquestracao.gerar_dag(cfg, pasta / "robo_empresa.py", wsl=False)
    codigo = ("from airflow.models.dagbag import DagBag; import sys; b = DagBag(dag_folder=sys.argv[1], include_examples=False);"
              "assert not b.import_errors, b.import_errors; print(sorted(b.dags))")
    saida = subprocess.run([os.environ["ROBO_TESTE_AIRFLOW_PYTHON"], "-c", codigo, str(pasta)], capture_output=True, text=True,
                           env={**os.environ, "AIRFLOW_HOME": str(tmp_path / "home")}, timeout=300)
    assert saida.returncode == 0, saida.stderr[-2000:]
    assert all(d in saida.stdout for d in orquestracao.FLUXOS)
