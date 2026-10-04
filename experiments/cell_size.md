# Tessellation cell size – sensitivity

Slope statistics for four runs at four cell sizes. Two of the four are separate OpenStreetMap ways that both carry the name "Olympia Abfahrt"; they are distinct features, not a duplicate row. The question is not which value is *right* but where the numbers stop moving.

| Run | Cell | Triangles | Mean slope | p90 slope |
|---|---:|---:|---:|---:|
| Kandahar-Abfahrt | 5 m | 25648 | 20.24° | 30.60° |
| Kandahar-Abfahrt | 10 m | 7222 | 19.99° | 29.96° |
| Kandahar-Abfahrt | 20 m | 2282 | 19.75° | 29.28° |
| Kandahar-Abfahrt | 40 m | 895 | 19.59° | 28.61° |
| Olympia Abfahrt | 5 m | 1770 | 24.34° | 37.03° |
| Olympia Abfahrt | 10 m | 589 | 23.85° | 34.96° |
| Olympia Abfahrt | 20 m | 264 | 23.58° | 32.19° |
| Olympia Abfahrt | 40 m | 167 | 23.91° | 30.98° |
| Olympia Abfahrt | 5 m | 11239 | 17.91° | 26.73° |
| Olympia Abfahrt | 10 m | 3289 | 17.59° | 25.78° |
| Olympia Abfahrt | 20 m | 1117 | 17.43° | 25.06° |
| Olympia Abfahrt | 40 m | 477 | 17.30° | 24.98° |
| Osterfelder-Abfahrt | 5 m | 5051 | 18.78° | 28.64° |
| Osterfelder-Abfahrt | 10 m | 1514 | 18.43° | 27.40° |
| Osterfelder-Abfahrt | 20 m | 552 | 18.16° | 25.83° |
| Osterfelder-Abfahrt | 40 m | 272 | 17.95° | 25.21° |

## Drift from the finest cell to the coarsest

| Run | Cells | Mean slope | p90 slope |
|---|---|---:|---:|
| Kandahar-Abfahrt | 5 m to 40 m | -3.2% | -6.5% |
| Olympia Abfahrt | 5 m to 40 m | -1.8% | -16.3% |
| Olympia Abfahrt | 5 m to 40 m | -3.4% | -6.5% |
| Osterfelder-Abfahrt | 5 m to 40 m | -4.4% | -12.0% |

Across 4 runs and an eightfold change in cell size the mean moves by at most 4.4% and the 90th percentile by at most 16.3%, always downward as cells coarsen. The mean survives a change of mesh resolution; the percentile does not, and is not comparable between datasets unless the cell size is quoted with it. That is why the cell is derived from the DEM rather than chosen, and why both the value and the rule are written into the build report.
