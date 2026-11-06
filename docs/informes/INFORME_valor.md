# La Quiniela: ¿compensa jugar columnas probables pero poco jugadas?

Backtest de 2017 a 2026 (temporadas nombradas por el año en que terminan). Se juegan 48 € por jornada (64 columnas a 0,75 €). Los parámetros se eligieron con 2017-2022 (393 jornadas) y la configuración elegida se evaluó **una sola vez** en 2023-2026 (294 jornadas).

## Resumen en pocas líneas

1. **La idea de fondo se confirma, pero sola no da beneficios.** Las columnas de "valor" (probables según las cuotas pero poco jugadas según los % LAE) cobran bastante más por cada premio. Con 12 aciertos cobran unos 15-22 € de media, frente a 10 € con los favoritos, y con 11 y 10 aciertos pasa lo mismo. Como aciertan algo menos, el resultado neto sigue siendo positivo: en las categorías de 10, 11 y 12 aciertos la mezcla `valor_mix` devuelve **+9,6 puntos más por euro que los favoritos en entrenamiento y +24,6 en test**. En ambos periodos el intervalo de confianza del 90 % excluye el cero.
2. **Ninguna estrategia gana dinero de forma fiable.** ROI con 48 €/jornada:

   | | Entrenamiento 2017-2022 | Test 2023-2026 | Test sin su mejor jornada |
   |---|---|---|---|
   | Favoritos (`valor_mix b=0`, referencia) | **-64,3 %** | **-66,5 %** | -67,7 % |
   | `valor_mix` (b=0,5) | **-44,5 %** | **+298,2 %** | -23,5 % |
   | `valor_ev` (delta=1) | **-67,9 %** | **+31,9 %** | -2,4 % |

   El +298 % del test sale casi entero de **un solo boleto de Pleno al 15** (45.365 € en 2026 J65). Sin esa jornada la ROI es -23,5 %. El +31,9 % de `valor_ev` depende de cinco 13 aciertos y, sin su mejor jornada, se queda en -2,4 %. Los intervalos de confianza son enormes: [-40 %, +936 %] y [-44 %, +130 %]. Como orden de magnitud realista, jugar con criterio de valor reduce las pérdidas (de perder ~65 % a perder ~25-50 %), pero no las convierte en ganancias.
3. **El modelo de premio esperado es demasiado optimista justo donde importa.** Para las columnas de `valor_ev` promete 2,2 € por euro jugado y en entrenamiento devolvió 0,32 €. Acierta bien *cuántos* premios llegan, pero sobrestima *cuánto* paga cada uno en los resultados más raros, que son los que elige el optimizador ("maldición del ganador").
4. **No he encontrado un criterio fiable de "esta jornada merece apostar más".** El valor esperado estimado antes de jugar no se correlaciona con lo cobrado (correlación ≈ 0 en ambos periodos). El umbral elegido en entrenamiento no mejora el test, y subir a 100 € en las jornadas "buenas" tampoco. El bote acumulado previo no da una señal útil.

---

## 1. Qué se ha construido

### 1.1 Modelo de premio esperado por columna (`strategies/valor_model.py`)

Para cada una de las 3^14 = 4.782.969 combinaciones posibles y cada categoría (14, 13, 12, 11 y 10 aciertos, más el Pleno al 15):

- **Probabilidad real** de cada resultado: los % probables (de cuotas), mezclados un 10 % con los % LAE (`prob^0,9 × lae^0,1`). Ese 0,9 se eligió por log-loss en 2017-2022. Sin la mezcla, el modelo exagera la ventaja de las cuotas sobre el público cuando se combinan 14 partidos: la "sorpresa" media del resultado real frente al público sería 0,53 nats y en realidad es 0,42. Con la mezcla, el valor esperado y el observado coinciden (0,423 frente a 0,427).
- **Acertantes rivales**: se estiman con los % LAE suponiendo que el público rellena cada partido de forma independiente: rivales = columnas jugadas × probabilidad de que una columna del público tenga exactamente esos fallos. Las columnas jugadas (recaudación / 0,75) **no se conocen antes de la jornada**. Se estiman con la media de las 6 jornadas anteriores del mismo tipo (fin de semana o entre semana) y un ajuste por el bote acumulado. El error típico es del 26 %.
- **Premio**: fondo de la categoría según el reparto SELAE (16 % para 14, 7,5 % para 13, 12 y 11, 9 % para 10 y 7,5 % + bote para el 15), dividido entre rivales + 1 (nosotros), con la fórmula de Poisson. Se aplica el **gravamen del 20 %** por encima del mínimo exento vigente. He comprobado que los premios de `jornadas.csv` son netos: el mínimo exento era 2.500 € hasta 07/2018, 10.000 € el resto de 2018, 20.000 € en 2019 y 40.000 € desde 2020.
- **Bote del 15**: solo con información previa. Es la reserva de fondos de 15 y 14 que quedaron desiertos en jornadas anteriores, multiplicada por la proporción histórica que se aplica. Solo cuenta en jornadas de fin de semana, que son las que suelen llevar bote. Correlación con el bote real: 0,72.
- **Calibración en dos etapas, siempre con jornadas anteriores**:
  1. Corrección del nº de rivales: cociente entre acertantes reales y predichos, por tramos.
  2. Corrección del premio: cociente entre premio real y predicho, por tramos. Cada predicción histórica se hizo con *su* propia historia previa.

  Resultado en las jornadas 41-700 (`valor_calibracion/resumen.txt`):

  | Categoría | Correlación (log) premio predicho vs real | Error mediano |
  |---|---|---|
  | 14 | 0,95 | 44 % |
  | 13 | 0,98 | 29 % |
  | 12 | 0,98 | 22 % |
  | 11 | 0,98 | 15 % |
  | 10 | 0,98 | 10 % |

  Por deciles el cociente real/predicho queda entre 0,87 y 1,23 en todas las categorías. La etapa 1 sola sobrestimaba el decil más alto de 13 y de 12 (0,66 y 0,49).

El valor esperado de una columna suma, para cada distancia d = 0…4 (es decir, 14…10 aciertos), la probabilidad de cada resultado a esa distancia por el premio esperado en ese resultado. Se calcula para las 4,8 M de columnas a la vez con una recursión por partido (unos 2 s por jornada). He comprobado que coincide con la suma por fuerza bruta.

### 1.2 Estrategias

- **`strategies/valor_ev.py`**: elige 64 columnas con un greedy de valor esperado y diversificación. La ganancia de añadir una columna es su EV menos `delta × (la parte de sus premios de 14/13/12 que ya cubren las columnas elegidas)`. Con `delta=0` toma las 64 de mayor EV; con `delta=1` cada resultado posible solo cuenta una vez. Parámetro principal: `delta`.
- **`strategies/valor_mix.py`**: el peso de cada columna es `prob^a × (prob/lae)^b`, y la selección se hace con `engine.reduce.greedy_cover` (maximiza la probabilidad, con esos pesos, de 13+ si `radius=1` o de 12+ si `radius=2`). Con `b=0` es la estrategia de **favoritos** (solo probabilidad), que uso como referencia.
- Las dos aceptan `ev_min` (no jugar si el EV estimado por euro es menor) y `ev_alto`/`n_alto` (jugar más columnas si lo supera), para el punto 6.
- **Pleno al 15**: el marcador más probable según los % probables de goles de `pleno15.csv` (solo se leen las columnas `prob_*`/`lae_*`, nunca el resultado).

### 1.3 Qué información se usa

- Antes del partido: % LAE, % probables, fecha (día de la semana) y % de goles del pleno.
- De jornadas anteriores: recaudación, bote, acertantes y premios.
- **Los % quinielista no se usan en ningún sitio**, porque su marca de tiempo es la de la descarga.
- La recaudación y el bote de la jornada en curso no se usan: se estiman.

## 2. Ajuste honesto

- Rejilla pequeña, fijada de antemano: `valor_ev` con delta ∈ {0; 0,5; 1}; `valor_mix` con a=1, b ∈ {0; 0,5; 1} y radius=1, y b ∈ {0; 0,5} con radius=2.
- Regla de elección fijada antes de mirar: la mejor ROI de entrenamiento dentro de cada familia (para `valor_mix`, solo b>0). El resultado fue **`valor_ev delta=1`** y **`valor_mix b=0,5 radius=1`**. La referencia es **favoritos = `valor_mix b=0 radius=1`**.
- Los umbrales de EV para seleccionar jornadas también se eligieron en entrenamiento, el que maximizaba la ROI entre los cuantiles 20/40/50/60/80 %. Están guardados en `valor_ajuste/eleccion.json`.
- El script de test solo lee esa elección. En test no se miraron otras configuraciones.

### 2.1 Entrenamiento 2017-2022 (393 jornadas, 18.864 € de gasto por estrategia)

| Configuración | Cobrado (€) | ROI | IC 90 % | ROI sin la mejor jornada | 15/14/13/12 | Jornadas con premio | Mayor premio (€) | Drawdown máx. (€) | Racha máx. sin premio |
|---|---|---|---|---|---|---|---|---|---|
| mix b=0 r=2 (favoritos 12+) | 85.182 | +351,6 % | [-66, +1178] | -62,3 % | 1/0/22/115 | 65,6 % | 78.046 (un Pleno al 15) | 6.417 | 6 |
| **mix b=0,5 r=1** | 10.468 | **-44,5 %** | [-59, -27] | -51,6 % | 0/2/23/140 | 54,7 % | 1.159 | 8.617 | 6 |
| mix b=0,5 r=2 | 9.834 | -47,9 % | [-60, -35] | -52,4 % | 0/1/14/96 | 61,6 % | 828 | 9.342 | 4 |
| mix b=1 r=1 | 9.463 | -49,8 % | [-65, -32] | -57,2 % | 0/1/18/105 | 44,3 % | 1.159 | 9.501 | 8 |
| **favoritos (mix b=0 r=1)** | 6.738 | **-64,3 %** | [-71, -56] | -67,8 % | 0/1/23/151 | 59,3 % | 636 | 12.126 | 6 |
| **ev delta=1** | 6.062 | **-67,9 %** | [-78, -56] | -71,7 % | 0/0/1/35 | 29,8 % | 728 | 12.802 | 19 |
| ev delta=0,5 | 4.995 | -73,5 % | [-82, -64] | -76,8 % | 0/0/2/35 | 27,2 % | 304 | 13.869 | 20 |
| ev delta=0 | 4.501 | -76,1 % | [-84, -68] | -79,6 % | 0/0/2/34 | 26,0 % | 304 | 14.363 | 20 |

- En todas las filas, cobrado real = cobrado y `cobrado_estimado` = 0 €: ninguna columna ganó una categoría desierta, así que no hizo falta estimar ningún premio.
- El primer puesto (favoritos con cobertura 12+) se debe a un único Pleno al 15 (2019 J45). Por eso la regla de elección excluía b=0 de la familia "valor".
- La diversificación ayuda: en `valor_ev`, delta=1 es mejor que delta=0.
- Con 100 € (133 columnas), los favoritos r=1 también acertaron ese Pleno al 15 (+144 %). `mix b=0,5 r=1` quedó en -7,9 % (-29 % sin su mejor jornada).

### 2.2 Test 2023-2026 (294 jornadas, 14.112 € de gasto por estrategia), evaluado una sola vez

| Estrategia | Cobrado (€) | ROI | IC 90 % | ROI sin la mejor jornada | 15/14/13/12/11/10 | Jornadas con premio | Mayor premio (€) | Drawdown máx. (€) | Racha máx. sin premio |
|---|---|---|---|---|---|---|---|---|---|
| `valor_ev` delta=1 | 18.620 | **+31,9 %** | [-44, +130] | -2,4 % | 0/0/5/46/240/820 | 30,3 % | 4.078 | 2.727 | 12 |
| `valor_mix` b=0,5 r=1 | 56.201 | **+298,2 %** | [-40, +936] | -23,5 % | 1/1/18/149/570/1364 | 55,1 % | 45.365 (Pleno al 15) | 3.187 | 7 |
| favoritos | 4.725 | **-66,5 %** | [-72, -61] | -67,7 % | 0/1/19/155/591/1426 | 60,5 % | 98 | 9.387 | 7 |

- Cobrado real = cobrado; `cobrado_estimado` = 0 € en las tres.
- ROI por temporada en test:
  - favoritos: -67, -71, -63 y -66 %.
  - `valor_mix`: -22, -23, -2 y +1197 % (el Pleno al 15).
  - `valor_ev`: -21, +108, -15 y +56 %.
- `valor_mix` supera a favoritos en 9 de las 10 temporadas de 2017-2026. La excepción es 2017, que es además el periodo en que la calibración todavía tenía poca historia.
- Los números del CLI `engine.run` coinciden al céntimo con los del laboratorio en todas las salidas oficiales: `results/valor_{ev,mix,fav}_{train,test}`, `valor_mix_test_umbral` (-48,05 %) y `valor_mix_test_100si` (+215,96 %). En `valor_mix_test_umbral`, el `resumen.txt` del motor cuenta como "jugadas" las 294 jornadas, pero en 212 de ellas no se apostó (0 columnas).

## 3. ¿Mejora el enfoque de valor? Análisis con menos ruido

El ROI total depende de muy pocos premios gordos (13, 14 y 15 aciertos), así que es casi todo suerte. La señal más limpia está en los premios pequeños y frecuentes (10, 11 y 12 aciertos), que se cuentan por cientos (`valor_test/baja_varianza.txt`):

| | € por cada 12 | € por cada 11 | € por cada 10 | Retorno de 10-12 por € jugado | Diferencia con favoritos (IC 90 %) |
|---|---|---|---|---|---|
| **Entrenamiento** favoritos | 10,0 | 3,0 | 1,20 | 28,0 % | — |
| Entrenamiento `valor_mix` b=0,5 | 14,7 | 5,0 | 1,72 | 37,7 % | **+9,6 pp [+4,1; +15,8]** |
| Entrenamiento `valor_ev` d=1 | 55,8 | 14,1 | 3,22 | 32,0 % | +3,6 pp [-7,1; +16,6] |
| **Test** favoritos | 10,2 | 2,4 | 0,98 | 31,1 % | — |
| Test `valor_mix` b=0,5 | 21,9 | 4,7 | 1,48 | 56,3 % | **+24,6 pp [+13,2; +39,2]** |
| Test `valor_ev` d=1 | 81,4 | 11,4 | 2,64 | 61,2 % | **+28,8 pp [+9,4; +54,4]** |

Cómo se lee la tabla:

- Las columnas de valor aciertan menos veces, pero cada premio vale de 1,5 a 8 veces más. El balance es positivo: la mezcla moderada (`b=0,5`) gana a favoritos de forma estadísticamente clara en los dos periodos.
- El extremo (`valor_ev`, que solo busca valor) acierta tan poco que en entrenamiento no se distingue de los favoritos. En test sí gana.
- La hipótesis "elegir columnas probables y poco jugadas mejora el rendimiento esperado aunque no aumenten los aciertos" queda **respaldada en su versión moderada**.
- Aun así, el retorno total esperado sigue por debajo del 100 % del gasto. Ni con los premios pequeños ni contando los grandes con su frecuencia histórica se llega a beneficio.

**Por qué el modelo promete más de lo que da.** Comparando lo esperado con lo obtenido para las columnas elegidas (`valor_ajuste/resumen.txt`, apartado "esperado por el modelo vs obtenido"):

- El *número* de premios coincide bien. Para `valor_mix` en entrenamiento: 130 doces esperados frente a 140 reales, y 509 onces frente a 529.
- Los *euros* por premio se sobrestiman en los resultados raros: en `valor_ev`, los 12 aciertos valían 5.206 € esperados y se cobraron 1.954 €.

El público no rellena los partidos de forma independiente: hay quinielas al azar, sistemas y peñas. Por eso los resultados "que nadie juega" tienen más acertantes de los que predice la independencia. Al buscar los EV más altos entre 4,8 millones de columnas, el optimizador elige precisamente donde el modelo se equivoca a favor. Ese es el motivo de que el EV estimado por euro (2,2 para `valor_ev` y 1,15 para `valor_mix`) no sea creíble como cifra absoluta.

## 4. Selección de jornadas y tamaño de la apuesta

Para cada jornada se calcula, antes de jugar, el EV estimado por euro del boleto. Se probaron dos reglas con el umbral elegido en entrenamiento: (a) jugar solo si el EV supera el umbral y (b) jugar 100 € (133 columnas) en esas jornadas y 48 € en el resto.

| Test 2023-2026 | Jugar siempre 48 € | Jugar siempre 100 € | (a) solo si EV ≥ umbral | (b) 100 € si EV ≥ umbral, si no 48 € |
|---|---|---|---|---|
| `valor_ev` (umbral 1,53) | +31,9 % | +5,0 % | +36,4 % (249 jornadas) | +5,8 % |
| `valor_mix` (umbral 1,42) | +298,2 % | +229,0 % | -48,1 % (82 jornadas) | +216,0 % |
| favoritos (umbral 0,56) | -66,5 % | -63,6 % | -61,5 % (88 jornadas) | -63,4 % |

- **Correlación entre el EV estimado y la ROI de cada jornada**: -0,03 / 0,11 / 0,02 en entrenamiento y -0,02 / 0,01 / 0,07 en test. Por quintiles de EV la ROI sube y baja sin patrón.
  - La única excepción es `valor_mix` en entrenamiento, donde el retorno de 10-12 sube del 23 % al 55 % del quintil bajo al alto.
  - En test ese patrón no se repite (25, 73, 79, 43 y 63 %).
- **Bote**: el EV estimado sube en jornadas con bote esperado, pero la ROI real no.
  - Entrenamiento: favoritos -61,5 % sin bote esperado y -66,7 % con bote; `valor_mix` -46,6 % y -42,7 %; `valor_ev` -65,9 % y -69,6 %.
  - En test, el Pleno al 15 de `valor_mix` cayó en una jornada con bote esperado. Es un único suceso: en el resto de categorías la diferencia no aparece.
  - El Pleno al 15 requiere acertar 14 y además el marcador (con 64 columnas, del orden de 1 vez cada 2.000 jornadas), así que ni un bote de varios millones mueve mucho el valor esperado real.
- **Conclusión**: no hay ningún criterio fiable para jugar más en unas jornadas que en otras. Las mejoras aparentes de una regla en un periodo no se repiten en el otro.

## 5. Limitaciones y supuestos

- **Pocos premios gordos**: con 393 o 294 jornadas, un solo 14 o 15 cambia la ROI en cientos de puntos. Por eso doy la ROI sin la mejor jornada, intervalos de confianza por remuestreo y el análisis de 10-12 aciertos.
- **Reglas del motor** (no he cambiado el código del motor):
  - Una columna cobra solo su categoría máxima: el 15 no cobra además el 14. Es conservador.
  - Nuestras columnas no reducen el premio de los demás. Si se contara que también somos acertantes, la ROI de test bajaría de +298,2 % a +276,6 % en `valor_mix` y de +31,9 % a +30,9 % en `valor_ev`. En entrenamiento el efecto es nulo.
- **Avisos sobre el motor (no son fallos, no he modificado nada)**:
  1. La columna `bote` de `jornadas.csv` **es el bote recibido por la categoría 15 en esa jornada**. Comprobado: 2027 J8 premio15 = neto(7,5 % × recaudación + bote). Así que `--use-bote` sería lo correcto si hubiera que estimar un 15 desierto.
  2. `estimate_prize` da premios brutos, pero los publicados son netos de impuestos.
  3. En `data.default_price` el corte de temporada (`>= 2019`) supone la etiqueta por año de inicio, pero las etiquetas van por año final. No afecta, porque `precio_apuesta` siempre viene informado.

  En estos backtests `cobrado_estimado` fue 0 €, así que 1 y 2 no influyen.
- **% probables y LAE**: se toman como pre-partido, tal como pide el enunciado. En 2017 y parte de 2018 los % probables son enteros. El modelo necesita unas 40 jornadas de historia para calibrarse: en la primera mitad de 2017 usa valores por defecto.
- Tests del motor: `python -m unittest discover -s engine/tests -t . -v` pasa (24 tests).

## 6. Ficheros

| Ruta | Contenido |
|---|---|
| `strategies/valor_model.py` | Modelo de premio esperado, calibración y selección (`select_ev`, `select_mix`) |
| `strategies/valor_ev.py`, `strategies/valor_mix.py` | Estrategias para `engine.run` |
| `valor_lab.py` | `calib` (calibración) y `grid` (rejilla; cada jornada se modela una vez y se evalúa con `engine.rules.evaluate`) |
| `valor_analisis.py` | `train` (elige), `test` (evalúa lo elegido) y `extra` (análisis de 10-12 aciertos y quintiles) |
| `results/valor_calibracion/` | Calibración del premio predicho frente al real |
| `results/valor_grid/rows_train.csv`, `rows_test.csv` | Una fila por jornada × configuración × presupuesto (48 y 100 €), con premios reales y esperados |
| `results/valor_ajuste/` | Tablas de la rejilla, `eleccion.json`, temporadas, esperado frente a obtenido |
| `results/valor_test/` | Resultado fuera de muestra, análisis de baja varianza y temporadas |
| `results/valor_{mix,fav,ev}_{train,test}/`, `results/valor_mix_test_umbral/`, `results/valor_mix_test_100si/` | Salidas oficiales de `engine.run` (`jornadas.csv`, `temporadas.csv`, `resumen.txt`) |

Para reproducir, desde `quiniela\`:

```
python valor_lab.py calib
python valor_lab.py grid --from 2017 --to 2026 --workers 4      (unos 75 min)
python valor_analisis.py train
python valor_analisis.py test
python valor_analisis.py extra
python -m engine.run --strategy valor_mix --budget 48 --from 2023 --to 2026 --out results\valor_mix_test --param b=0.5 --param radius=1
python -m engine.run --strategy valor_ev  --budget 48 --from 2023 --to 2026 --out results\valor_ev_test  --param delta=1
python -m engine.run --strategy valor_mix --budget 100 --from 2023 --to 2026 --out results\valor_mix_test_100si --param b=0.5 --param radius=1 --param n=64 --param ev_alto=1.423204 --param n_alto=133
```
