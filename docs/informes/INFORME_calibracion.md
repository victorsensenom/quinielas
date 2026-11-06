# Calibración de los % probables y filtro de "forma de jornada"

Fecha: 19/10/2026. Datos: 687 jornadas jugadas de 2017 a 2026 (9.618 partidos 1X2), 48 € por jornada (64 columnas).
Método: **se entrena con 2017-2022** (393 jornadas) y **se evalúa una sola vez en 2023-2026** (294 jornadas).

## Resumen en cuatro frases

1. Los % probables (los que salen de las cuotas) ya están **bien calibrados**. Hay un sesgo pequeño: los favoritos claros ganan algo más de lo que dicen las cuotas (por ejemplo, del 77 % sube a un 81,5 % real) y las sorpresas muy improbables salen algo menos.
2. La corrección (una "temperatura" más un ajuste de empates y de victorias visitantes por tipo de partido) mejora el log-loss fuera de muestra **de forma estadísticamente significativa, pero muy pequeña**: un 0,25 % (de 0,9590 a 0,9567). En la validación con 2017-2022 la mejora no llegaba a ser significativa.
3. Ni la calibración ni el filtro de forma mejoran a `valor_mix` en 2023-2026 de forma clara. En 12+ y 13+ las diferencias son de ±1 o 2 jornadas, todas dentro del ruido, y en ROI sin la mejor jornada unas variantes salen algo mejor y otras algo peor según la versión.
4. **Recomendación: no meterlo en el programa como estrategia por defecto.** Como mucho, la corrección de probabilidades puede servir para que los % mostrados sean un poco más realistas, pero no cambia los resultados de forma que se pueda medir.

---

## Tarea A: calibración de los % probables

### Qué significa "calibrado"
Si las cuotas dicen 60 %, ese signo debería salir más o menos 60 de cada 100 veces. Para medirlo:
- **Fiabilidad por tramos**: se agrupan los partidos por deciles de probabilidad y se compara la probabilidad media con la frecuencia real.
- **Log-loss** (cuanto más bajo, mejor): el castigo medio por haber dado poca probabilidad al signo que salió. Con 1/3-1/3-1/3 saldría 1,099.
- **Brier** (cuanto más bajo, mejor): el error cuadrático medio.
- **Intervalos de confianza al 95 %**: bootstrap remuestreando **jornadas completas**, porque los partidos de una misma jornada no son del todo independientes.

### Resultado global (todos los ficheros en `results/calibracion/`)

| Periodo | Partidos | Log-loss prob [IC 95 %] | Brier | Log-loss % LAE (público) |
|---|---|---|---|---|
| 2017-2026 | 9.618 | 0,9679 [0,958-0,977] | 0,5756 | 0,9973 |
| 2017-2022 | 5.502 | 0,9745 [0,961-0,987] | 0,5801 | 1,0050 |
| 2023-2026 | 4.116 | 0,9590 [0,945-0,973] | 0,5695 | 0,9871 |

En conjunto, las frecuencias observadas de 1, X y 2 coinciden con las previstas con una diferencia menor de 1 punto, y siempre con el 0 dentro del intervalo.

**Fiabilidad por deciles (2017-2026)**, `fiabilidad_deciles_2017_2026.csv`:

| Signo | Tramo más bajo: prevista → real | Tramo más alto: prevista → real |
|---|---|---|
| 1 | 14,8 % → 13,7 % | 77,1 % → **81,5 %** [78,9-83,8] |
| X | 13,7 % → **11,6 %** [9,8-13,8] | 32,7 % → 32,9 % |
| 2 | 7,9 % → **6,2 %** [4,8-7,9] | 64,0 % → 65,8 % |

Es el **sesgo favorito-sorpresa** típico de las casas de apuestas: los favoritos muy claros están algo infravalorados y los signos muy improbables, algo sobrevalorados. En 2023-2026 se nota más: en el decil más alto del 1 la previsión es del 77 % y la frecuencia real del 83 %.

### Por grupos (2017-2026, observado − previsto, en puntos)

`division` es un código interno de la fuente. Además del código, se ha creado una **categoría** a partir de los nombres de los equipos:
- `esp`: códigos 1, 2 y 3 (1ª, 2ª y 1ª RFEF).
- `ext`: código 5, clubes (ligas extranjeras, nórdicas en verano, y competiciones europeas).
- `sel`: los dos equipos son selecciones nacionales.
- `fem`: algún nombre lleva "(F)" o termina en " F".
- `otro`: el resto (4 partidos).

| Grupo | Partidos | Log-loss | 1 | X | 2 |
|---|---|---|---|---|---|
| esp | 6.057 | 0,994 | +0,9 | +0,4 | **−1,2** [−2,3; −0,1] |
| ext | 2.814 | 0,945 | 0,0 | **−2,0** [−3,5; −0,4] | **+2,0** [+0,5; +3,5] |
| sel | 669 | 0,858 | −0,1 | −0,8 | +0,9 |
| fem | 74 | 0,714 | −1,0 | −6,8 | +7,8 (muy pocos partidos) |
| esp en verano (jun-ago) | 564 | 1,032 | **−5,0** | **+4,4** | +0,6 |
| ext en verano (nórdicas, etc.) | 1.061 | 0,971 | −0,9 | −1,7 | +2,6 |

Por meses destaca **agosto** (inicio de la Liga): el 1 sale 7,3 puntos menos de lo previsto [−10,2; −4,2]. En **julio** salen menos empates (−4,7) y más doses (+3,8) que lo previsto (son casi todo ligas nórdicas).
Por temporadas, ninguna se desvía de forma significativa en 1/X/2, aunque el log-loss varía entre 0,94 y 1,01 según lo "rara" que haya sido la temporada. Que los % fueran enteros (2017 y parte de 2018) no empeora la calibración.
Las tablas completas están en `grupos_*.csv`.

### Corrección probada
Para cada partido, el % corregido es proporcional a `exp(T · log p + c_signo)`:
- `T` es la "temperatura". `T > 1` afila las probabilidades: el favorito sube y la sorpresa baja.
- `c_X` y `c_2` desplazan los empates y las victorias visitantes.

Hay un juego de parámetros global y otro por grupo, encogido hacia el global con una penalización (`lam`) para que los grupos con pocos partidos no se sobreajusten. Variantes probadas:
- global;
- por categoría;
- categoría con ext separado en verano;
- **categoría con esp y ext separados en verano** (`cat_verano2`);
- por código de división;
- cada una con o sin el % LAE como dato extra.

**Elección con 2017-2022** (validación cruzada dejando una temporada fuera, `cv_train.csv`): la mejor es `cat_verano2` con lam = 50. Mejora el log-loss en 0,30 milésimas, con un IC de [−1,56; +0,98]: **no es significativa dentro de 2017-2022**. Las variantes con LAE no aportan nada.

**Evaluación en 2023-2026** (parámetros ajustados con 2017-2022, `test_2023_2026.csv`):

| Modelo | Log-loss test | Diferencia (milésimas) [IC 95 %] | Diferencia en Brier |
|---|---|---|---|
| Sin corregir | 0,95902 | — | — |
| Global (T = 1,10) | 0,95736 | −1,66 [−2,75; −0,64] | −0,93 [−1,53; −0,27] |
| **cat_verano2, lam 50 (elegido)** | **0,95666** | **−2,36 [−3,82; −0,90]** | −1,36 [−2,27; −0,48] |

Parámetros ajustados con 2017-2022: T ≈ 1,06-1,17 según el grupo. En la Liga española en verano el ajuste de empates es c_X = +0,17, es decir, sube los empates en agosto. En ligas extranjeras el ajuste del 2 es c_2 = +0,10/+0,15, que sube la victoria visitante.

**Conclusión de la Tarea A:** fuera de muestra, la corrección **sí mejora los % de forma significativa, pero muy poco**: un 0,25 % de log-loss, unas 0,033 unidades de log por jornada de 14 partidos. Eso equivale a dar en torno a un 3 % más de probabilidad a la combinación que sale de verdad. Además, todas las variantes mejoran parecido en el test, lo que indica que el efecto viene sobre todo de la temperatura: los favoritos de 2023-2026 se cumplieron más que en el pasado. Hay que añadir una advertencia: la variante `cat_verano2` se añadió después de ver la tabla descriptiva de 2017-2026, que incluía el test. Ahora bien, el efecto de agosto también aparece solo con 2017-2022 (X +5,2 [+0,2; +10,5]), y la versión global, que no tiene ese sesgo, mejora casi lo mismo.

### Archivos de la Tarea A
- `strategies/calibracion.py`, con `corregir(info, history) -> matriz 14x3 en %`. Solo usa datos previos al partido: % probables, % LAE si falta el probable, nombres de los equipos, código de división y fecha. Toma de `data/calibracion.json` **el ajuste más reciente que use solo temporadas anteriores a la de la jornada**. El parámetro `hasta=2022` fija los parámetros de 2017-2022. En 2017 no hay ajuste previo y devuelve los % originales.
- `data/calibracion.json`: 10 ajustes acumulativos (2017..2017, 2017..2018, …, 2017..2026) con el esquema `cat_verano2` y lam = 50.
- `strategies/valor_mix_cal.py`: igual que `valor_mix` (a = 1, b = 0,5, radius = 1), pero con los % corregidos. El % LAE no se toca.
- `calib_lab.py` (análisis completo, unos 20 s) y `engine/tests/test_calibracion.py` (comprueba que no se usan datos futuros, que el ajuste recupera parámetros conocidos y que las categorías y los filtros de forma son correctos).

---

## Tarea B: filtro de "forma de jornada"

Histórico 2017-2026, con el favorito definido como el signo de mayor % probable y la sorpresa gorda como el de menor:
- Ganan de 5 a 10 favoritos en el **89 %** de las jornadas (no en el 80 %). La media es 7,44.
- Salen de 1 a 5 sorpresas gordas en el **92 %** de las jornadas.

En cambio, las 64 columnas de `valor_mix` llevan casi siempre de **9 a 12 favoritos y 0-1 sorpresas gordas**. El motivo es que cada columna sirve para cubrir los resultados a 1 fallo de distancia.

`strategies/valor_mix_forma.py` solo admite como candidatas las columnas con un número de favoritos entre `fav_min` y `fav_max` y de sorpresas gordas entre `sorp_min` y `sorp_max`, y luego selecciona con `greedy_cover` igual que `valor_mix`. Para que vaya rápido se usa un preselección que da exactamente el mismo resultado (comprobado). La rejilla de 16 combinaciones se probó solo con 2017-2022 (`forma_lab.py`, `results/forma_grid/`):
- favoritos: sin límite, 5-12, 5-11 y 5-10;
- sorpresas: sin límite, máximo 5, mínimo 1 y 1-5.

| Variante (2017-2022) | ROI | Sin la mejor | Sin las 3 mejores | 12+ | 13+ | 14 |
|---|---|---|---|---|---|---|
| sin filtro (= valor_mix) | −44,5 % | −51,5 % | −58,2 % | 12,5 % | 3,1 % | 0,5 % |
| **fav 5-11, sorp ≤ 5 (elegida)** | −41,2 % | **−45,7 %** | −53,4 % | 12,7 % | 3,8 % | 0,3 % |
| fav 5-12, sorp ≤ 5 | −41,9 % | −46,9 % | −52,7 % | 12,7 % | 3,8 % | 0,5 % |
| fav 5-12, sorp 1-5 | −53,6 % | −58,1 % | −62,3 % | 11,7 % | 4,6 % | 0,0 % |
| fav 5-10, sorp ≤ 5 | −54,9 % | −57,5 % | −61,8 % | 12,5 % | 1,3 % | 0,0 % |

- El máximo de 5 sorpresas no cambia nada, porque `valor_mix` nunca llega a ese número.
- Exigir al menos 1 sorpresa o como mucho 10 favoritos empeora los resultados.
- Criterio fijado de antemano: el mejor ROI sin la mejor jornada, que da fav 5-11 y sorp ≤ 5. Aun así, en el entrenamiento la diferencia con `valor_mix` no es significativa: +1 jornada con 12+ y +3 con 13+, con intervalos que incluyen el 0.

---

## Comparación fuera de muestra: 2023-2026 (294 jornadas, 14.112 € gastados)

| Variante | Cobrado | ROI | Sin la mejor | Sin las 3 mejores | 12+ | 13+ | 14 | Temporadas en positivo |
|---|---|---|---|---|---|---|---|---|
| **valor_mix** (referencia) | 56.201 € | +298,2 % | −23,2 % | −38,7 % | 17,7 % | 5,1 % | 0,7 % | 1/4 |
| valor_mix_cal, parámetros fijos 2017-2022 | 9.504 € | −32,7 % | −41,5 % | −55,4 % | 17,0 % | 4,8 % | 0,3 % | 0/4 |
| valor_mix_cal, actualizados cada temporada | 15.959 € | +13,1 % | −20,1 % | −46,6 % | 16,7 % | 5,8 % | 0,7 % | 2/4 |
| valor_mix_forma (fav 5-11, sorp ≤ 5) | 12.777 € | −9,5 % | −35,2 % | −48,8 % | 17,7 % | 3,7 % | 0,0 % | 1/4 |

Comparación jornada a jornada con `valor_mix` (diferencia en el % de jornadas, IC 95 %):
- **cal fija**: 12+ −0,7 puntos [−3,7; +2,4]; 13+ −0,3 [−1,0; 0,0].
- **cal actualizada**: 12+ −1,0 [−4,1; +2,0]; 13+ +0,7 [−0,7; +2,0].
- **forma**: 12+ 0,0 [−3,1; +3,4]; 13+ −1,4 [−3,4; +0,3].

**Ninguna diferencia es significativa.**

Qué hay detrás del ROI:
- El +298 % de `valor_mix` es un solo pleno de 14 + 15 (2026 J65, 45.406 €). Las variantes no lo cogieron porque, al cambiar unas pocas columnas, esa combinación quedó fuera.
- La versión de calibración actualizada cada temporada coge otro 14 (2025 J74, 4.721 €).
- Son golpes de suerte de una sola jornada y no sirven para decidir. Por eso lo importante son el ROI sin la mejor jornada o sin las 3 mejores y el % de 12+ y 13+, y ahí todo está empatado dentro del ruido.

Periodo completo 2017-2026 (entrenamiento y test juntos; la calibración siempre con parámetros de temporadas anteriores):

| Variante | ROI | Sin la mejor | Sin las 3 mejores | 12+ | 13+ | 14 | Temporadas + |
|---|---|---|---|---|---|---|---|
| valor_mix | +102,2 % | −35,4 % | −43,0 % | 14,7 % | 3,9 % | 0,6 % | 1/10 |
| valor_mix_cal (actualizada) | −17,1 % | −31,3 % | −42,6 % | 15,6 % | 4,7 % | 0,7 % | 2/10 |
| valor_mix_cal (fija desde 2023) | −36,7 % | −40,8 % | −47,7 % | 15,7 % | 4,2 % | 0,6 % | 0/10 |
| valor_mix_forma | −27,6 % | −38,7 % | −44,4 % | 14,8 % | 3,8 % | 0,1 % | 1/10 |

La calibración da algo más de 12+ y 13+ **en el entrenamiento** (+2,3 puntos en 12+ [−0,3; +4,8]), pero en el test esa ventaja no se repite.

## Recomendación

- **Calibración**: el mercado ya es casi perfecto. Lo que se gana en log-loss es real pero diminuto, y no se nota en los premios. No compensa la complejidad de meterla en la estrategia. Si se quiere usar, lo razonable sería **solo para mostrar** % algo más realistas en el programa, con la versión actualizada cada temporada (`corregir(info, history)` sin `hasta`), y reajustando `data/calibracion.json` al final de cada temporada con `python calib_lab.py`.
- **Filtro de forma**: no aporta nada. La estadística de "5-10 favoritos" describe el resultado real, pero `valor_mix` cubre a un fallo de distancia, y forzar columnas con menos favoritos solo reparte peor la cobertura. **No meterlo.**
- Mantener `valor_mix` tal cual. El resultado depende casi por completo de acertar o no un 14 alguna jornada: sin la mejor jornada, todas las variantes pierden entre un 20 % y un 45 %.

## Cómo reproducir
```
python calib_lab.py                                    # análisis + data/calibracion.json
python forma_lab.py --procs 10                         # rejilla de forma 2017-2022
python -m engine.run --strategy valor_mix_cal --budget 48 --from 2017 --to 2022 --out results\valor_mix_cal_train
python -m engine.run --strategy valor_mix_cal --budget 48 --from 2023 --to 2026 --param hasta=2022 --out results\valor_mix_cal_test
python -m engine.run --strategy valor_mix_cal --budget 48 --from 2023 --to 2026 --out results\valor_mix_cal_test_wf
python -m engine.run --strategy valor_mix_forma --budget 48 --from 2023 --to 2026 --param fav_min=5 --param fav_max=11 --param sorp_max=5 --out results\valor_mix_forma_test
python metricas.py results\calib_valor_mix_test results\valor_mix_cal_test results\valor_mix_cal_test_wf results\valor_mix_forma_test
```
Referencias recalculadas: `results/calib_valor_mix_train` y `results/calib_valor_mix_test`. Coinciden con la referencia que ya se tenía: +102 % / −35 % / 14,7 % / 3,9 % / 0,6 %.
