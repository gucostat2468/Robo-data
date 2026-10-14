"""Robô de Planilhas — ETL local de planilhas monitorando pastas do OneDrive.

Fluxo: Bases-Limpeza  ->  leitura  ->  limpeza  ->  validação  ->  modelagem  ->  Bases-Tratadas
Se houver qualquer erro bloqueante, o arquivo vai para Bases-Erros com um relatório explicando o motivo.
"""

__version__ = "1.0.0"
