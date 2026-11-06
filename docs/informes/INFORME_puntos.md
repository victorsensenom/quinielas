# Sistema de puntos para la Quiniela: ¿funciona alguna fórmula?

Fecha: 2/11/2026. Datos: 704 jornadas escrutadas (2017 a 2027, jornada 17). Gasto máximo: 48 € por jornada (64 columnas).
Pesos y configuración elegidos **solo con 2017-2022** (393 jornadas). Evaluación única en **2023-2026** (294 jornadas). Aparte, **2027** (17 jornadas).

## Resumen en seis frases

1. **Ninguna fórmula de puntos bate a las referencias de forma fiable fuera de muestra.** Los dos mejores de la prueba, `valor_mix` y "valor_mix alimentado con el modelo B", están empatados dentro del ruido.
2. **El sistema propio sin cuotas (A) es claramente peor que las cuotas**: acierta 0,14 signos menos por jornada y su log-loss (el error de sus probabilidades) es peor en 18 milésimas en los partidos de liga. Esa diferencia sí es real, no ruido.
3. **Partir de las cuotas y corregir (B) mejora muy poco las probabilidades** (−2,1 milésimas, significativo), pero casi todo viene de un ajuste general que ya conocíamos: afilar un poco las cuotas. Lo que añaden las variables de fútbol es ruido.
4. **Doble frente a triple: empate.** Ni 3 triples + 1 doble ni las otras formas se distinguen de 6 dobles. Lo que sí importa es qué columnas se juegan: las selecciones tipo `valor_mix` pierden bastante menos que cualquier boleto de fijos, dobles y triples.
5. **Solo una variable vale de verdad: la diferencia de goles por partido**, y solo para quien no mira las cuotas. El resto no aporta nada medible.
6. **Recomendación: seguir con `valor_mix` (b = 0,5).** La tabla de puntos sirve para revisar la jornada y entender los partidos, no para ganar más. La quiniela sigue teniendo esperanza negativa.

## Qué se ha hecho

- Ligas completas de 1ª y 2ª de football-data.co.uk, de 2010/11 a 2026/27 (13.708 partidos, 26/27 hasta el 1/11/2026). No ha hecho falta otra fuente.
- Variables calculadas con **solo lo jugado antes del primer partido de la jornada**, es decir, lo que sabrías al rellenar el boleto. Es más estricto que "antes de cada partido": un partido del domingo no usa lo del sábado. Lo comprueba `engine/tests/test_puntos.py` (borra o altera todo lo posterior y exige el mismo valor). Los 37 tests pasan.
- Referencias: favoritos (6 dobles según los % probables), `valor_mix` (b = 0,5) y columnas aleatorias.

### Cobertura de los datos

| Periodo | Signos con datos de liga | Jornadas sin ninguno | Jornadas con los 14 |
|---|---|---|---|
| 2017-2022 | 60,5 % (3.328 de 5.502) | 135 de 393 | 191 |
| 2023-2026 | 55,5 % (2.283 de 4.116) | 114 de 294 | 124 |
| 2027 | 53,4 % (127 de 238) | 5 de 17 | 1 |
| Total | **58,2 %** (5.738 de 9.856) | 254 de 704 | 316 |

- Emparejamiento: los nombres de **todos** los equipos de football-data se han traducido a los de la quiniela. De los 6.210 partidos de equipos españoles (sin femenino ni selecciones), se empareja el **92,4 %**. El 7,6 % restante son sobre todo Copa, Europa con equipo español y partidos aplazados más de 4 días.
- Sin datos de liga (2.854 de clubes extranjeros y competiciones europeas, 681 de selecciones, 106 femeninos y 472 de Copa y similares): se usan los % probables. Por eso A y B coinciden con las cuotas, o casi, en muchos partidos. **Hay que tenerlo en cuenta: A no es 100 % "sin cuotas"**, solo en el 58 % de los signos.

### Variables que se han quedado fuera

- **Cambio de entrenador, bajas y motivación**: no hay un histórico público fiable y automático. Fuera.
- **Bloque `tecnicos`** (existe desde media 2018): no hay señal de fuga, porque su log-loss es peor que el de los % probables en todas las temporadas. Pero no lleva marca de tiempo propia. Tampoco mejoró la validación en 2017-2022 (0,97399 frente a 0,97380). Fuera.
- **Movimiento `delta_*`**: en los partidos ya empezados al grabarse los % vale 0 en todos salvo 7 de 703, lo que indica que se congela al empezar. Tampoco aporta (0,97379 frente a 0,97380, por debajo del mínimo exigido de 0,1 milésimas). Fuera.

## La fórmula final

### Modelo A: puntos propios, sin cuotas

**Puntos = +4,5 por jugar en casa + 9,5 × Goles − 0,75 × Forma + 1 × CaraCara**

| Variable | Qué es | Efecto |
|---|---|---|
| Casa | Siempre suma | +4,5 |
| Goles | Diferencia de goles por partido del local menos la del visitante (tope ±1,5). Al principio de temporada se mezcla con la temporada pasada, con un peso de 6 partidos | +9,5 por cada gol de diferencia |
| Forma | Puntos por partido en los últimos 5, local menos visitante (tope ±2) | −0,75 por cada punto. Resta porque, a igualdad de goles, una buena racha reciente tiende a volver a su nivel |
| CaraCara | Lo que saca el local al recibir a este rival en las últimas 5 visitas, respecto a 1,6 puntos | +1 por cada punto |

Ejemplo (jornada 20): Valencia - R.Madrid = +4,5 − 14,2 + 1,0 − 0,6 = **−9,3 puntos**, tiende al 2.

Cómo se lee: con **más de +6,75** el 1 pasa del 50 %; con **menos de −6,75**, el 2 pasa del 50 %; entre medias, partido abierto. La probabilidad exacta sale de P(1) = logística((puntos − 6,75)/10), P(2) = logística((−puntos − 6,75)/10), y P(X) es el resto.

### Modelo B: cuotas más corrección

Se parte de los % probables y se elevan a 1,11 (el favorito sube un poco). Después, solo si hay datos de liga, se pasa una pequeña corrección del 2 al 1: **−0,07 × Puntos por partido + 0,09 × Goles − 0,07 × Forma + 0,12 si es derbi**, y un ajuste fijo de −0,06 al 1. Son correcciones diminutas.

### De los puntos a la decisión

Se ordenan los partidos por lo dudosos que son (menor probabilidad del favorito). La configuración elegida en 2017-2022 es `auto50`: **triple si el favorito no llega al 50 %, en los partidos más dudosos, y doble después, mientras quepa en 64 columnas**. En la práctica suele dar 3 triples + 1 doble. El resto son fijos.

## Resultados

- Signos = aciertos de la columna principal por jornada (media).
- 12+, 13+, 14 = % de jornadas que los alcanzan.
- Premios reales. "Sin 1" y "sin 3" = ROI quitando las mejores jornadas.

### Entrenamiento 2017-2022 (393 jornadas)

Ojo: aquí A y B se miden con datos que usaron para ajustarse, así que están favorecidos. Lo que cuenta es el test.

| Modelo | Signos | 12+ | 13+ | 14 | Gasto | Cobrado | ROI | Sin 1 | Sin 3 | Temp. + |
|---|---|---|---|---|---|---|---|---|---|---|
| Favoritos 6 dobles | 7,35 | 10,4 | 2,8 | 0,0 | 18.864 | 6.780 | −64,1 % | −66,6 % | −70,3 % | 0/6 |
| valor_mix | 7,33 | 12,5 | 3,1 | 0,5 | 18.864 | 10.468 | −44,5 % | −51,5 % | −58,2 % | 0/6 |
| Aleatoria | 4,67 | 0,0 | 0,0 | 0,0 | 18.864 | 2.410 | −87,2 % | −89,3 % | −91,6 % | 0/6 |
| A (auto50) | 7,25 | 9,2 | 3,1 | 0,5 | 15.827 | 5.447 | −65,6 % | −71,1 % | −77,7 % | 0/6 |
| B (auto50) | 7,38 | 11,7 | 3,3 | 0,5 | 15.813 | 8.566 | −45,8 % | −61,9 % | −68,6 % | 1/6 |
| A + valor_mix | 6,94 | 9,7 | 2,0 | 0,5 | 18.864 | 8.998 | −52,3 % | −59,3 % | −66,3 % | 0/6 |
| B + valor_mix | 7,34 | 13,5 | 4,1 | 0,8 | 18.864 | 13.277 | −29,6 % | −36,5 % | −45,4 % | 1/6 |

### Test 2023-2026 (294 jornadas): el resultado que cuenta

| Modelo | Signos | 12+ | 13+ | 14 | Gasto | Cobrado | ROI | Sin 1 | Sin 3 | Temp. + |
|---|---|---|---|---|---|---|---|---|---|---|
| Favoritos 6 dobles | 7,57 | 14,6 | 3,4 | 0,3 | 14.112 | 6.100 | −56,8 % | −60,8 % | −66,4 % | 0/4 |
| **valor_mix** | 7,40 | 17,7 | 5,1 | 0,7 | 14.112 | 56.201 | **+298,2 %** | **−23,2 %** | **−38,7 %** | 1/4 |
| Aleatoria | 4,52 | 0,7 | 0,0 | 0,0 | 14.112 | 1.170 | −91,7 % | −93,4 % | −94,4 % | 0/4 |
| A (auto50) | 7,43 | 11,2 | 4,4 | 0,3 | 11.840 | 3.368 | −71,6 % | −74,5 % | −77,7 % | 0/4 |
| B (auto50) | 7,52 | 14,3 | 4,8 | 0,3 | 11.799 | 4.647 | −60,6 % | −63,5 % | −66,9 % | 0/4 |
| A + valor_mix | 7,12 | 13,6 | 4,4 | 0,3 | 14.112 | 6.525 | −53,8 % | −62,2 % | −71,9 % | 0/4 |
| B + valor_mix | 7,33 | 18,7 | 6,1 | 0,3 | 14.112 | 10.781 | −23,6 % | −35,2 % | −50,3 % | 1/4 |

**Atención al +298 %**: es un solo premio de 45.406 € (2026, J65). Sin esa jornada, `valor_mix` pierde un 23 %. Hay que mirar las columnas "sin 1" y "sin 3".

### Log-loss frente a los % probables (cuanto más bajo, mejor)

Diferencia en milésimas, con intervalo de confianza del 95 % remuestreando jornadas.

| Periodo | % probables | A | Dif. A | B | Dif. B |
|---|---|---|---|---|---|
| 2017-2022, todos | 0,9745 | 0,9841 | +9,57 [+5,36; +13,82] | 0,9728 | −1,66 [−2,97; −0,37] |
| 2017-2022, con liga | 1,0061 | 1,0219 | +15,83 [+8,98; +23,09] | 1,0043 | −1,78 [−3,50; −0,07] |
| **2023-2026, todos** | 0,9590 [0,944; 0,974] | 0,9691 [0,954; 0,984] | **+10,06 [+5,58; +14,53]** | 0,9569 [0,941; 0,973] | **−2,11 [−3,49; −0,72]** |
| **2023-2026, con liga** | 0,9978 | 1,0160 | **+18,14 [+10,13; +26,07]** | 0,9959 | **−1,90 [−3,73; −0,03]** |
| 2027, todos | 0,9108 | 0,9325 | +21,65 [+3,35; +43,20] | 0,9056 | −5,20 [−11,63; +0,81] |
| 2027, con liga | 0,9577 | 0,9983 | +40,58 [+6,96; +81,60] | 0,9525 | −5,21 [−13,02; +1,82] |

¿De dónde sale la mejora de B en 2023-2026? Del simple ajuste general de las cuotas (elevar a 1,11): −1,68 [−2,90; −0,44]. Lo que añaden las variables de fútbol, en los partidos con liga, es −0,77 [−2,67; +1,11]: **ruido**. Encaja con lo que ya decía `INFORME_calibracion.md`.

### Diferencias en el test frente a las referencias

| Comparación | Signos | 12+ (puntos) | 13+ (puntos) | ROI recortando las 3 mejores (puntos) | ¿Real o ruido? |
|---|---|---|---|---|---|
| A frente a favoritos | −0,14 [−0,25; −0,03] | −3,4 [−6,8; 0,0] | +1,0 [−1,0; +3,1] | −12,1 [−23,2; −1,6] | **A es peor** |
| B frente a favoritos | −0,04 [−0,11; +0,03] | −0,3 [−3,7; +3,1] | +1,4 [−0,7; +3,4] | −1,3 [−11,6; +8,6] | Ruido (empate) |
| B + valor_mix frente a favoritos | −0,23 [−0,36; −0,11] | +4,1 [0,0; +8,5] | +2,7 [+0,7; +5,1] | +28,1 [+7,4; +51,9] | Mejor, como `valor_mix` |
| A frente a valor_mix | +0,03 [−0,12; +0,17] | −6,5 [−10,2; −3,1] | −0,7 [−3,1; +1,7] | −54,3 [−86,4; −26,4] | **A es peor** |
| B frente a valor_mix | +0,13 [+0,01; +0,24] | −3,4 [−7,1; +0,3] | −0,3 [−2,7; +1,7] | −43,5 [−72,5; −18,2] | **B es peor en dinero** |
| A + valor_mix frente a valor_mix | −0,28 [−0,43; −0,12] | −4,1 [−7,5; −1,0] | −0,7 [−1,7; 0,0] | −48,6 [−78,4; −22,5] | **Empeora** |
| **B + valor_mix frente a valor_mix** | −0,07 [−0,16; +0,03] | **+1,0 [−2,4; +4,4]** | **+1,0 [−0,7; +3,1]** | **−14,1 [−35,8; +4,5]** | **Ruido (empate)** |
| valor_mix frente a favoritos | −0,17 [−0,29; −0,05] | +3,1 [−1,0; +7,1] | +1,7 [−0,7; +4,1] | +42,2 [+16,6; +72,8] | Mejor en dinero |

La última columna recorta en cada estrategia sus 3 mejores jornadas al nivel de la cuarta (distinto de quitarlas, porque así se mantienen emparejadas las jornadas). Todas ganan a la aleatoria con mucha claridad.

Sobre **B + valor_mix**: en el entrenamiento parecía ganar a `valor_mix` (+18,5 puntos [+5,3; +33,5]), pero **esa ventaja no se repite en el test**. Saca algo más de 12+ y 13+ sin que llegue a ser significativo, y queda por debajo en dinero. Es el patrón típico del sobreajuste: conviene no fiarse.

## ¿Doble o triple?

Mismos fijos y misma columna principal; solo cambia la forma del boleto. Con los % probables (favoritos):

| Forma | Columnas | € | Periodo | 12+ | 13+ | 14 | ROI | Sin 3 |
|---|---|---|---|---|---|---|---|---|
| 6 dobles | 64 | 48,00 | Test | 14,6 | 3,4 | 0,3 | −56,8 % | −66,4 % |
| 3 triples + 1 doble | 54 | 40,50 | Test | 15,0 | 4,4 | 0,3 | −64,1 % | −70,6 % |
| 2 triples + 2 dobles | 36 | 27,00 | Test | 12,2 | 4,1 | 0,3 | −62,0 % | −70,1 % |
| 1 triple + 4 dobles | 48 | 36,00 | Test | 12,9 | 4,1 | 0,3 | −61,1 % | −67,5 % |
| 6 dobles | 64 | 48,00 | Entrenamiento | 10,4 | 2,8 | 0,0 | −64,1 % | −70,3 % |
| 3 triples + 1 doble | 54 | 40,50 | Entrenamiento | 12,2 | 4,1 | 0,3 | −58,5 % | −66,9 % |
| 2 triples + 2 dobles | 36 | 27,00 | Entrenamiento | 10,2 | 2,8 | 0,3 | −59,8 % | −70,2 % |
| 1 triple + 4 dobles | 48 | 36,00 | Entrenamiento | 8,9 | 2,5 | 0,3 | −65,2 % | −74,1 % |

- **Test, 3 triples + 1 doble frente a 6 dobles**: 12+ +0,3 puntos [−3,4; +3,7]; 13+ +1,0 [−1,0; +3,1]; ROI recortado −5,1 [−15,7; +4,9]. **Empate.** En el entrenamiento los triples iban algo mejor y en el test algo peor: justo lo que se espera del azar.
- **Tu intuición tiene base, pero no da ventaja.** En el partido más dudoso de cada jornada del test, el tercer signo salió el 25,5 % de las veces: un doble deja fuera 1 de cada 4. Por contra, cada triple obliga a dejar fijo otro partido dudoso. Con las frecuencias del test, los dos boletos cubren más o menos lo mismo: en torno a un 18 % de acertar todos los partidos dudosos que tocan (estimación suponiendo partidos independientes).
- **La única ventaja práctica del triple**: 3 triples + 1 doble cuesta 7,50 € menos por jornada que 6 dobles y da aciertos parecidos. Si te gusta jugar así, no pierdes nada; pero tampoco ganas.
- **Lo que de verdad cambia las cosas no es doble o triple**, sino la selección de columnas: `valor_mix` supera a los 6 dobles en +42 puntos de ROI recortado.

## Qué variables valen

Lo que se pierde al quitar cada variable. Positivo = la variable ayuda, en milésimas de log-loss, sobre los partidos con liga.

**Las 8 candidatas, en validación dentro de 2017-2022** (cada temporada con pesos de las otras cinco):

| Variable | Ayuda en A | Ayuda en B (sobre cuotas) | Veredicto |
|---|---|---|---|
| Diferencia de goles | **+6,83 [+3,88; +9,68]** | +0,42 [−0,04; +0,88] | **La única que vale**, y solo sin cuotas |
| Forma últimos 5 | +0,70 [−0,52; +1,97] | +0,62 [−0,51; +1,72] | Ruido |
| Puntos por partido | −0,50 [−1,24; +0,20] | +0,05 [−0,29; +0,39] | Nada: la dif. de goles ya lo recoge |
| Forma casa/fuera | −0,40 [−0,90; +0,09] | −0,42 [−0,84; 0,00] | No aporta |
| Cara a cara | +0,33 [−0,51; +1,15] | −0,28 [−0,53; −0,04] | Ruido o nada |
| Rachas | −0,07 [−0,53; +0,37] | −0,19 [−0,38; +0,01] | No aporta |
| Descanso | −0,27 [−0,73; +0,19] | −0,87 [−1,47; −0,29] | No aporta (solo ve la liga) |
| Derbi | −0,23 [−0,55; +0,09] | +0,08 [−0,68; +0,79] | Nada |

**Las que quedaron en las fórmulas, medidas en el test con pesos congelados**:

| Modelo | Variable | Aporta [IC 95 %] |
|---|---|---|
| A | Goles | **+56,7 [+42,7; +70,9]** (sin ella, A solo sabría que el local juega en casa) |
| A | Forma | +0,9 [−0,5; +2,3] |
| A | Cara a cara | +0,7 [−0,3; +1,6] |
| B | Puntos por partido | +0,2 [−1,0; +1,4] |
| B | Goles | +1,5 [−0,4; +3,4] |
| B | Forma | +0,9 [−1,0; +2,9] |
| B | Derbi | −0,2 [−0,9; +0,6] |

Conclusión: **rachas, historial, descanso, derbi y forma casa/fuera no sirven, y el mercado ya descuenta todo lo demás.** Quedarse en B con esas cuatro variables fue el resultado del procedimiento fijado de antemano, pero ninguna tiene un intervalo que excluya el cero.

## Las últimas quinielas: 2027 (jornadas 1 a 17)

Pesos congelados de 2017-2022. Son solo 17 jornadas: **no sirven para concluir nada**, y se incluyen para que veas qué habría pasado.

| Modelo | Signos | 12+ | 13+ | 14 | Gasto | Cobrado | ROI | Sin 1 | Sin 3 |
|---|---|---|---|---|---|---|---|---|---|
| Favoritos 6 dobles | 8,24 | 17,6 | 5,9 | 0,0 | 816,00 | 319,68 | −60,8 % | −89,1 % | −93,1 % |
| valor_mix | 8,06 | 23,5 | 11,8 | 0,0 | 816,00 | 264,27 | −67,6 % | −73,0 % | −80,5 % |
| Aleatoria | 4,12 | 0,0 | 0,0 | 0,0 | 816,00 | 25,89 | −96,8 % | −97,7 % | −99,1 % |
| A (auto50) | 8,00 | 17,6 | 11,8 | 0,0 | 675,00 | 121,93 | −81,9 % | −87,7 % | −95,3 % |
| B (auto50) | 8,35 | 17,6 | 11,8 | 0,0 | 696,00 | 183,01 | −73,7 % | −78,8 % | −87,8 % |
| A + valor_mix | 7,24 | 17,6 | 11,8 | 0,0 | 816,00 | 121,28 | −85,1 % | −89,8 % | −98,2 % |
| B + valor_mix | 8,06 | 17,6 | 11,8 | 0,0 | 816,00 | 277,82 | −66,0 % | −70,0 % | −77,3 % |

| J | Partidos con liga | Signos col. principal: favoritos / A / B | Máx. aciertos: favoritos / A / B / valor_mix / B+valor | Cobrado €: favoritos / A / B / valor_mix / B+valor |
|---|---|---|---|---|
| 1 | 13 | 7 / 7 / 7 | 8 / 8 / 7 / 8 / 8 | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 |
| 2 | 14 | 6 / 6 / 6 | 8 / 8 / 9 / 8 / 7 | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 |
| 3 | 10 | 8 / 8 / 8 | 12 / 10 / 11 / 10 / 11 | 236,14 / 2,32 / 24,44 / 13,92 / 47,80 |
| 4 | 10 | 8 / 7 / 8 | 10 / 9 / 11 / 11 / 11 | 13,60 / 0,00 / 40,74 / 30,54 / 30,54 |
| 5 | 0 | 10 / 10 / 11 | 12 / 13 / 13 / 13 / 13 | 8,52 / 43,78 / 43,78 / 39,52 / 39,52 |
| 6 | 10 | 9 / 8 / 8 | 9 / 10 / 10 / 10 / 11 | 0,00 / 6,52 / 3,26 / 6,52 / 13,59 |
| 7 | 7 | 8 / 7 / 8 | 10 / 8 / 9 / 11 / 11 | 6,30 / 0,00 / 0,00 / 56,94 / 38,04 |
| 8 | 10 | 8 / 7 / 8 | 8 / 11 / 10 / 10 / 9 | 0,00 / 4,92 / 0,00 / 0,00 / 0,00 |
| 9 | 10 | 6 / 6 / 6 | 9 / 8 / 8 / 9 / 9 | 0,00 / 0,00 / 0,00 / 0,00 / 0,00 |
| 10 | 0 | 8 / 8 / 8 | 10 / 10 / 10 / 10 / 11 | 5,92 / 2,96 / 2,96 / 2,96 / 20,39 |
| 11 | 10 | 6 / 8 / 7 | 10 / 9 / 9 / 10 / 10 | 13,96 / 0,00 / 0,00 / 3,49 / 6,98 |
| 12 | 13 | 8 / 7 / 9 | 9 / 8 / 11 / 12 / 11 | 0,00 / 0,00 / 7,82 / 34,98 / 19,55 |
| 13 | 0 | 7 / 7 / 7 | 9 / 10 / 10 / 9 / 10 | 0,00 / 3,93 / 3,93 / 0,00 / 3,93 |
| 14 | 10 | 11 / 10 / 11 | 11 / 12 / 12 / 12 / 12 | 8,88 / 28,30 / 28,30 / 36,62 / 19,42 |
| 15 | 0 | 10 / 10 / 10 | 10 / 11 / 11 / 11 / 11 | 0,00 / 6,10 / 3,05 / 9,15 / 12,20 |
| 16 | 10 | 8 / 8 / 8 | 10 / 9 / 10 / 10 / 9 | 3,26 / 0,00 / 1,63 / 3,26 / 0,00 |
| 17 | 0 | 12 / 12 / 12 | 13 / 13 / 13 / 13 / 13 | 23,10 / 23,10 / 23,10 / 26,37 / 25,86 |

La tabla completa, con las columnas de A + valor y aleatoria, está en `results/puntos/jornadas_2027.csv`. Por curiosidad: el boleto fijo de 3 triples + 1 doble con B o con favoritos habría cogido un 14 en la J17 (359,08 € en total), pero `auto50` jugó esa jornada de otra forma y no lo cogió. Es un buen ejemplo de lo mucho que manda el azar.

## Limitaciones

- Solo el 58 % de los signos tiene datos de liga. En Europa, ligas de verano, selecciones, Copa y fútbol femenino el sistema no aporta nada propio. Podrían añadirse otras ligas de la misma web, pero no se ha probado y, visto lo visto, cabe esperar poco.
- El descanso solo ve partidos de liga: no sabe si un equipo jugó Copa o Europa entre semana.
- Los % probables históricos son los últimos antes de cada partido, posiblemente algo posteriores al cierre real del boleto. Eso favorece un poco a todo lo que usa cuotas, también a `valor_mix`.
- En una jornada por jugar, el programa no distingue Copa de Liga si dos equipos de la misma división se enfrentan y aún no han jugado ese partido en liga.
- Entrenamiento con 2020 y 2021, años de estadios vacíos; no se ha corregido.
- Se supone que tu boleto no cambia el reparto de premios.

## Recomendación honesta

1. **Sigue con `valor_mix` (b = 0,5).** Ninguna variante lo mejora de forma demostrable. Con los números de estos años, cuenta con perder entre un 25 % y un 50 % de lo jugado, salvo que caiga un premio gordo.
2. **No uses el modelo A para decidir signos.** Como tabla para entender un partido está bien; como sistema pierde más que los % probables.
3. **`B + valor_mix` no merece el cambio por ahora**: está empatado. Si te apetece, déjalo como observación durante una o dos temporadas sin dinero.
4. **Doble o triple, como prefieras.** Mejor elegir por presupuesto: los triples ahorran 7,50 € por jornada.
5. Juega solo lo que puedas perder: ninguna fórmula de estas gana a la casa.

## Cómo usarlo y reproducirlo

```
python puntos_jornada.py                      # tabla y signos de la próxima jornada abierta
python puntos_jornada.py --jornada 20         # una jornada concreta
python puntos_jornada.py --modelo A --forma 3T1D

python fetch.py 2027 2027 && python build.py  # actualizar histórico
python ligas.py                               # descargar o refrescar ligas
python puntos_features.py                     # recalcular variables
python puntos_ajuste.py                       # pesos (solo 2017-2022)
python puntos_lab.py lanzar 2017 2022 && python puntos_lab.py elegir
python puntos_lab.py lanzar 2023 2026 && python puntos_lab.py lanzar 2027 2027 && python puntos_lab.py informe
python -m unittest discover -s engine/tests -t . -v
```

Estado de las jornadas siguientes (2/11/2026): la J18 está cerrada pero sin escrutar, así que no entra. La **J19 es de competición europea (0 de 14 con datos de liga)**: el sistema se queda en las cuotas. La J20 tiene 10 de 14 con liga, pero aún faltan % probables de 5 partidos, así que conviene relanzarlo cerca del cierre.

Resultados en `results/puntos/`: `metricas_*.csv`, `logloss.csv`, `comparaciones.csv`, `ajuste_*.csv`, `jornadas_2027.csv`, `informe.json` y `runs/`. El detalle del ajuste general frente a las variables se calcula con `scratch/extra.py`, y la comprobación de fuga con `scratch/leak.py`.
