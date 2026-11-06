# Estrategias basadas en los % probables: informe

Presupuesto: 48 € por jornada, es decir, 64 columnas a 0,75 €.
Entrenamiento (para elegir parámetros): temporadas 2017 a 2022, 393 jornadas.
Prueba fuera de muestra (evaluada una sola vez): 2023 a 2026, 294 jornadas.
Fecha: 17/10/2026.

## 1. Resumen

- **Ninguna estrategia gana dinero de forma fiable.** La configuración elegida en entrenamiento, `r2` (64 columnas que maximizan la probabilidad de acertar 12 o más), da **−28,6 % en entrenamiento y +2,0 % en prueba**. Las dos cifras se deben casi por completo a **un solo premio de 14 aciertos** en cada periodo: 6.346 € en la jornada 2019/1 y 8.132 € en la jornada 2026/71. Sin la mejor jornada de cada periodo, la ROI baja a **−62 % en entrenamiento y −56 % en prueba**.
- El intervalo de confianza al 90 % (bootstrap por jornadas) de la ROI de `r2` en prueba va de −62 % a +116 %. Es tan ancho que el +2 % no permite concluir nada. Para saber si `r2` es mejor que la media o solo tuvo suerte harían falta muchas más jornadas, o bien una forma de estimar el valor esperado de los 14 aciertos sin depender de cuántas veces se ha acertado de verdad.
- **La parte "repetible" de la recaudación (premios de 10 a 13 aciertos) devuelve entre el 34 y el 39 % de lo gastado** con cualquier estrategia razonable basada en probabilidades. Eso equivale a una ROI de base de −60 % a −65 %, que es peor que el −45 % medio de la Quiniela. Ese −45 % incluye el bote y el Pleno al 15, que casi nunca se acierta con 64 columnas. Para llegar a ROI positiva hace falta acertar algún 14 bien pagado.
- **Dificultad de la jornada.** En las jornadas "fáciles" (favoritos claros, baja entropía) se cobra con más frecuencia y caen más 13 y 14, en los dos periodos y con todas las estrategias. Aun así, la ROI sigue siendo negativa si se quita la jornada con el premio gordo. **El bote no influye** en lo que cobran estas estrategias.

## 2. Qué se ha probado

### Estrategia `prob_condicionada` (`strategies/prob_condicionada.py`)

1. Con los % probables (prob1/X/2, que salen de las cuotas de apuestas) se calcula la probabilidad de cada una de las 3^14 ≈ 4,8 millones de combinaciones posibles, suponiendo partidos independientes.
2. Opcionalmente, esa distribución se **condiciona** a combinaciones "típicas". Los rangos se aprenden **solo de las jornadas anteriores** (`history`):
   - `filtro=abs`: número de 1, X y 2 entre los percentiles 5 y 95 de los resultados reales anteriores.
   - `filtro=resid`: número esperado de 1/X/2 en esta jornada (suma de probabilidades) más el margen histórico entre lo real y lo esperado, también entre los percentiles 5 y 95.
   - `sorp=auto`: máximo de "sorpresas" (signos con probabilidad < 30 %), fijado por el percentil 95 del histórico.
3. Elige K = 64 columnas con uno de tres objetivos:
   - `radio=0`: las 64 combinaciones más probables (`top64`).
   - `radio=1`: `greedy_cover` para maximizar la probabilidad de acertar 13 o más.
   - `radio=2`: `greedy_cover` para maximizar la probabilidad de acertar 12 o más.
4. **Pleno al 15**: el motor no expone `pleno15.csv` en `JornadaInfo` y `partidos.csv` no trae % para el partido 15. Por eso se pronostica el resultado de goles **más frecuente en el historial anterior**: 1-1 en casi todo el periodo y M-0 al principio.

### Referencias

- `fijo_favoritos`: una sola columna (0,75 €) con el favorito de cada partido.
- `aleatoria`: 64 columnas al azar (semilla 12345).
- `dobles6` (`strategies/prob_dobles6.py`): múltiple al directo con 8 fijos y 6 dobles. Los dobles van a los 6 partidos con el favorito más débil y cubren sus dos signos más probables. Son 2^6 = 64 columnas.

### Ajuste honesto

- La rejilla, de 9 configuraciones, se fijó antes de ver resultados: `top64`, `r1`, `r2`, `r1_abs`, `r1_resid`, `r2_resid`, `r1_sorp`, `r1_resid_sorp` y `r2_resid_sorp`.
- El criterio, también decidido de antemano, fue la mayor ROI en entrenamiento. Ganó `r2`.
- Se evaluó en prueba **una sola vez**. Junto a `r2` se evaluó también `top64`, declarada como referencia secundaria antes de mirar la prueba y sin usarla para elegir.
- Advertencia: con otro criterio más robusto, la ROI sin la mejor jornada, la elegida habría sido `top64` (−56,0 %) o `r2_resid` (−56,5 %), y no `r2` (−62,2 %). El "éxito" de `r2` en entrenamiento también fue un único 14.

## 3. Resultados

"Cobrado": todo procede de premios **reales** de `jornadas.csv`. El cobrado estimado, que el motor usa cuando una categoría queda desierta, fue **0 €** en todas las estrategias: nunca acertamos una categoría que se quedara sin acertantes.

"Sin mejor jornada": ROI quitando la jornada en la que más se cobró. "Racha": jornadas seguidas sin cobrar nada. "DD": caída máxima del saldo acumulado, en euros.

### Entrenamiento 2017–2022 (393 jornadas, 18.864 € de gasto por estrategia de 64 columnas)

| Estrategia | Cobrado € | ROI | Sin mejor jornada | IC90 ROI | 15/14/13/12/11/10 | % jornadas con premio | Mayor premio € | DD € | Racha |
|---|---|---|---|---|---|---|---|---|---|
| **r2 (elegida)** | 13.474 | **−28,6 %** | −62,2 % | [−66, +38] | 0/1/22/115/481/1436 | 65,6 | 6.346 | 6.425 | 6 |
| top64 | 10.702 | −43,3 % | −56,0 % | [−65, −15] | 0/6/32/198/695/1735 | 48,6 | 1.974 | 8.756 | 7 |
| r1_resid (= r1_resid_sorp) | 9.842 | −47,8 % | −63,4 % | [−67, −18] | 1/0/21/154/574/1579 | 59,5 | 2.921 | 10.623 | 6 |
| r1_abs | 9.729 | −48,4 % | −63,9 % | [−68, −18] | 1/0/24/127/566/1488 | 60,3 | 2.921 | 10.712 | 6 |
| r1 (= r1_sorp) | 8.963 | −52,5 % | −68,0 % | [−72, −22] | 1/0/23/150/585/1654 | 59,3 | 2.921 | 11.483 | 6 |
| r2_resid (= r2_resid_sorp) | 8.635 | −54,2 % | −56,5 % | [−62, −46] | 0/0/22/117/457/1400 | 66,7 | 427 | 10.284 | 4 |
| dobles6 | 6.390 | −66,1 % | −68,7 % | [−74, −58] | 0/0/16/135/560/1595 | 43,8 | 160 | 12.812 | 7 |
| aleatoria | 2.410 | −87,2 % | −89,3 % | [−92, −82] | 0/0/0/0/18/81 | 19,1 | 405 | 16.483 | 20 |
| fijo_favoritos (1 col., 295 €) | 145 | −50,9 % | −69,9 % | [−79, −12] | 0/0/3/3/11/34 | 6,1 | 56 | 162 | 75 |

El único 15 (jornada 2017/42, fácil, con 203 acertantes de 15) pagó 2.921 €.

### Prueba 2023–2026 (294 jornadas, 14.112 € de gasto)

| Estrategia | Cobrado € | ROI | Sin mejor jornada | IC90 ROI | 15/14/13/12/11/10 | % jornadas con premio | Mayor premio € | DD € | Racha |
|---|---|---|---|---|---|---|---|---|---|
| **r2 (elegida)** | 14.389 | **+2,0 %** | −55,6 % | [−62, +116] | 0/3/22/102/448/1232 | 67,0 | 8.132 | 7.751 | 4 |
| top64 (ref. secundaria) | 5.310 | −62,4 % | −64,1 % | [−70, −54] | 0/2/20/195/720/1567 | 49,7 | 90 | 8.802 | 7 |
| dobles6 | 6.100 | −56,8 % | −60,8 % | [−68, −44] | 0/1/20/144/580/1498 | 46,3 | 455 | 8.311 | 7 |
| aleatoria | 1.170 | −91,7 % | −93,4 % | [−95, −88] | 0/0/0/2/13/63 | 18,0 | 240 | 12.942 | 30 |
| fijo_favoritos (1 col., 220 €) | 86 | −60,9 % | −69,3 % | [−78, −41] | 0/0/3/3/15/27 | 7,5 | 19 | 134 | 41 |

Por temporada, `r2` en prueba quedó así: 2023 −42 %, 2024 −66 %, 2025 −47 % y 2026 **+156 %**, gracias al 14 de la jornada 71.

### ¿De dónde sale el dinero? (cobrado / gasto, por categoría)

| | 14 | 13 | 12 | 11 | 10 |
|---|---|---|---|---|---|
| r2 entrenamiento | 33,6 % | 7,4 % | 7,5 % | 11,3 % | 11,6 % |
| r2 prueba | 63,3 % | 9,5 % | 8,0 % | 11,5 % | 9,8 % |
| top64 prueba | 1,1 % | 3,9 % | 11,5 % | 11,8 % | 9,3 % |
| dobles6 prueba | 3,2 % | 3,0 % | 11,7 % | 13,7 % | 11,6 % |

Las categorías 10 a 13 devuelven siempre entre el 34 y el 39 % de lo jugado. Lo que separa a unas estrategias de otras son los 14.

Hay un detalle interesante. Los 14 de `top64` pagan poco porque llegan cuando ganan todos los favoritos y hay cientos de acertantes (los 2 de prueba sumaron unos 155 €). Los de `r2` pagaron 6.346 € en entrenamiento y 8.132 €, 721 € y unos 80 € en prueba. Esto tiene una explicación razonable: `r2` reparte las columnas lejos de la combinación "obvia", así que solo acierta 14 cuando hay alguna sorpresa leve y, por tanto, pocos acertantes. Pero son 4 casos en 10 temporadas, demasiado pocos para darlo por probado.

## 4. ¿Depende la ROI del bote o de la dificultad?

Se calcularon tres rasgos conocidos antes de jugar:

- **Entropía**: la suma de la incertidumbre de los 14 partidos. Más alta significa jornada más difícil.
- **log10 de la probabilidad de la combinación más probable**: más alto significa jornada más fácil.
- **Bote**.

Los cortes en terciles se aprendieron **solo con el entrenamiento** (entropía: 19,87 y 20,58 bits; bote: 0 y 865.000 €) y se aplicaron sin cambios a la prueba. El detalle está en `prob_analisis_jornada.json`.

**ROI por tercil de entropía** (fácil / media / difícil):

| | Entrenamiento | Prueba |
|---|---|---|
| r2 | +50 % / −64 % / −72 % | +115 % / −68 % / −62 % |
| top64 | −27 % / −23 % / −80 % | −55 % / −70 % / −65 % |
| dobles6 | −64 % / −63 % / −71 % | −59 % / −75 % / −41 % |
| r1 | −16 % / −67 % / −75 % | — |

- **Dificultad: el efecto existe y se repite fuera de muestra.** En las jornadas fáciles hay muchos más 13 y 14. Con `r2`, 17 de los 23 aciertos de 13 o más del entrenamiento y 21 de los 25 de la prueba cayeron en el tercil fácil. También se cobra más a menudo: 81 % y 77 % de las jornadas, frente a 48 % y 59 % en las difíciles. La correlación de Spearman entre entropía y cobrado/gasto es negativa en los dos periodos y para todas las estrategias (entre −0,15 y −0,29).
- **Pero no hay ROI positiva demostrable.** El +50 % y el +115 % de `r2` en jornadas fáciles salen de los mismos dos premios de 14. Sin la mejor jornada, `r2` en jornadas fáciles da −51 % en entrenamiento y −40 % en prueba. `top64` da −48 % y −58 %. Una regla de "jugar solo las jornadas fáciles" (entropía ≤ 19,87) gastaría un tercio y mejoraría algo la ROI, pero seguiría siendo negativa salvo que caiga un 14.
- **Bote: sin efecto consistente.** La correlación es casi nula (entre −0,08 y +0,06) y los terciles cambian de orden entre entrenamiento y prueba. Tiene sentido: el bote solo engorda la categoría de 15, que con 64 columnas casi nunca se acierta.

## 5. Conclusiones honestas

1. Lo esperable para cualquier jugador es una ROI de alrededor de −45 %. Las estrategias con los % probables mejoran claramente al azar (−87 % / −92 %) y a la múltiple de 6 dobles en entrenamiento, pero su "suelo" repetible está en torno a −55 % / −65 %.
2. La única cifra que supera el −45 % (`r2`: −28,6 % y +2,0 %) depende de un premio de 14 por periodo. Ha salido así dos veces de dos, lo cual es sugerente pero **no es una prueba**: el intervalo de confianza abarca desde −62 % hasta +116 %. **No recomendaría jugar dinero real basándose en esto.**
3. Los filtros por número de 1/X/2 y de sorpresas apenas cambian las columnas que elige `greedy_cover`, porque sus rangos históricos son amplios. El filtro de sorpresas (`sorp=auto`) no llegó a actuar nunca. Las diferencias entre `r1`, `r1_abs` y `r1_resid`, y entre `r2` y `r2_resid`, se explican por uno o dos premios. Son ruido.
4. Si se quiere seguir investigando, lo más prometedor es estimar el valor esperado de un 14 según "lo lejos del favorito" que esté la columna, porque eso no depende de haber acertado 14 de verdad. Para ello habría que modelar cuántos acertantes tendría cada combinación, por ejemplo con los % LAE jugados. Ese es el terreno de las estrategias de "valor" del otro agente.

## 6. Supuestos y limitaciones

- Todos son los del motor: nuestro boleto no altera el reparto de premios, y una columna cobra solo su categoría máxima. En la Quiniela real, quien acierta el 15 cobra también el 14. Esto solo afecta al 15 de `r1`, por unos 636 €.
- Los % probables tienen sello de tiempo en el fin de semana de la jornada (ver `data/README.md`). Puede haber una pequeña fuga en los partidos del domingo si los % se congelaron después del sábado. Si existiera, haría los resultados algo optimistas.
- No se ha modificado el motor (`engine/`).

## 7. Ficheros y reproducción

- `strategies/prob_condicionada.py` y `strategies/prob_dobles6.py`: las estrategias.
- `prob_experimento.py`: el script del experimento, con estas fases:
  - `python prob_experimento.py train` para la rejilla de entrenamiento.
  - `python prob_experimento.py test r2 top64` para la evaluación fuera de muestra.
  - `python prob_experimento.py tabla` para la tabla de métricas.
  - `python prob_experimento.py analisis r2 top64 dobles6 r1` para el análisis por tipo de jornada.
- `results/prob_train_<config>/` y `results/prob_test_<config>/`: `jornadas.csv`, `temporadas.csv` y `resumen.txt`, en el mismo formato que `engine.run`.
- `results/prob_metricas.csv`: todas las métricas, con el intervalo de confianza bootstrap y la ROI sin la mejor jornada.
- `results/prob_analisis_jornada.json`: la ROI por terciles de entropía, probabilidad máxima y bote.
- Equivalente con la CLI: `python -m engine.run --strategy prob_condicionada --param radio=2 --budget 48 --from 2023 --to 2026 --out results\prob_test_r2`.
