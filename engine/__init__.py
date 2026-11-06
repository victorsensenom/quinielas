"""Motor de backtesting para estrategias de La Quiniela.

Modulos:
    data      carga de CSV -> objetos Jornada (completa) y JornadaInfo (solo pre-partido)
    strategy  interfaz de estrategia, Column/ColumnSet y helpers de probabilidades
    rules     reglas de acierto/categoria y estimacion de premios (reparto LAE)
    backtest  walk-forward, control de presupuesto y metricas
    reduce    utilidades de reduccion: bases, filtros y seleccion greedy 13+/12+
    run       CLI
"""
