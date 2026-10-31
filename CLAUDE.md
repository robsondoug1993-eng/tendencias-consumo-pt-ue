# CLAUDE.md — Tendências de Consumo Portugal × UE27

Projeto de portfólio de BI (Robson Douglas de Almeida): estudo de mercado do **setor de retalho em Portugal × UE27**, de 2010 a 2026, com previsão até 2027. Cobre três frentes: comércio local, grandes redes e online. Os dados são públicos do Eurostat. O fluxo é ETL em Python → modelo estrela em Power BI (PBIP/TMDL) → previsão → relatório e apresentação, com conclusões por departamento (Direção, Marketing, Expansão, E-commerce, Pricing, Finanças).

- Repositório: https://github.com/robsondoug1993-eng/tendencias-consumo-pt-ue (público, branch `main`)
- Pasta local: `C:\Users\Robson\Desktop\Projetos\Tendencias_Consumo_PT_UE\`

## Como trabalhar neste projeto

- **Língua:** escrever em português de Portugal (retalho, faturação, ficheiro, utilizador), com decimal em vírgula (`+1,5%`).
- **Estilo:** respostas diretas e concisas.
- **Dados brutos:** nunca editar os ficheiros de `dados brutos/`. Tudo o que é derivado sai dos scripts.
- **Números:** qualquer número novo no relatório, na apresentação ou no README tem de vir dos CSV de `saida/` ou ser calculado a partir deles. Não inventar valores. Se o valor vier de uma fonte externa, indicar a fonte e o ano.
- **Depois de alterar dados ou scripts:** correr o ETL e a previsão de novo, e confirmar que `saida/validacao_totais.csv` continua coerente.

## Estrutura

```
dados brutos/        TSV originais do Eurostat (≈270 MB, NÃO versionados — ver .gitignore)
scripts/
  etl_consumo.py     ETL: TSV largo → formato longo, filtros, modelo estrela em saida/
  previsao.py        previsão por canal (2026–2027) + curva de adoção online até 2030
saida/               fatos, dimensões e resultados da previsão (CSV) + gráficos PNG
modelo/
  script_modelo.tmdl script único que cria o modelo no Power BI (tabelas, relações, medidas)
  medidas.dax        medidas DAX documentadas
  GUIA_POWER_BI.md   guia de montagem do modelo
Tendencias_Consumo_PT_UE.pbip            projeto Power BI (abrir no Power BI Desktop)
Tendencias_Consumo_PT_UE.Report/         páginas e visuais (PBIR, JSON)
Tendencias_Consumo_PT_UE.SemanticModel/  modelo semântico (TMDL)
entregaveis/         relatório (PDF/DOCX), apresentação (PDF/PPTX), dashboard em PDF
prints/              páginas do dashboard exportadas (PNG + PDF)
docs/                imagens usadas no README (dashboard e slides)
```

## Comandos

```bash
pip install pandas numpy scipy matplotlib
python scripts/etl_consumo.py "dados brutos" saida
python scripts/previsao.py "dados brutos" saida
```

- Os dois scripts recebem `<pasta_raw> <pasta_saida>`, com `.` e `./saida` por omissão.
- `previsao.py` depende de `saida/fato_compras_online.csv`, por isso o ETL corre primeiro.
- `statsmodels` não é usado: os modelos de previsão estão implementados em numpy/scipy.
- Para descarregar um dataset bruto:
  `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/<código>?format=TSV&compressed=false`

## Dados (Eurostat)

| Código | Conteúdo |
|---|---|
| isoc_ec_ibuy (≤2019) / isoc_ec_ib20 (2020+) | % de pessoas que compram online, por perfil |
| isoc_ec_ibgs | categorias compradas online |
| sts_trtu_m | índices mensais de vendas do retalho (NACE G47…), SCA/NSA, base 2021 = 100 |
| sbs_sc_dt_r2 (≤2020) / sbs_sc_ovw (2021+) | empresas por dimensão (micro, pequena, média, grande) |
| prc_hicp_aind | inflação (IHPC) por COICOP |
| nama_10_co3_p3 | despesa de consumo das famílias |

**Formato dos TSV:** largo, uma coluna por período. `:` significa sem dado. As letras depois do número são flags: b = quebra de série, e = estimado, p = provisório, u = baixa fiabilidade. Os filtros são os 27 países da UE mais o agregado `EU27_2020`, a partir de 2010.

## Convenções dos CSV de `saida/`

- Separador `;`, decimal `,`, codificação `utf-8-sig`.
- Prefixos `fato_` e `dim_`. Colunas em MAIÚSCULAS: `CO_` para códigos, `NO_` para nomes, `IDX_` para índices, `PCT_` para percentagens.
- **Fatos:**
  - `fato_vendas_retalho` (mês × país × atividade)
  - `fato_compras_online`
  - `fato_categorias_online`
  - `fato_estrutura_retalho`
  - `fato_inflacao`
  - `fato_consumo_familias`
  - `fato_previsao`
  - `fato_projecao_online`
- **Auxiliares:** `previsao_resumo_anual`, `previsao_metricas`, `previsao_q4_2026`, `validacao_totais`.
- **Dimensões:**
  - `dim_tempo`, `dim_ano` (FASE: "1. Pré-pandemia (≤2019)", "2. Pandemia (20-21)", "3. Inflação (22-23)", "4. Pós-inflação (24+)")
  - `dim_pais`
  - `dim_atividade` (NIVEL, CANAL)
  - `dim_perfil`, `dim_categoria_online`, `dim_coicop`, `dim_dimensao_empresa`

## Cuidados analíticos (importantes)

- Índices e percentagens **não se somam**: usar a média ou o valor filtrado.
- Não somar CO_NACE de níveis diferentes. Por exemplo, G47 já inclui G471/G472 e G479 inclui G4791. Usar `dim_atividade[NIVEL]`.
- Há quebras de série em 2020 (ibuy → ib20) e em 2021 (sbs_sc_dt_r2 → sbs_sc_ovw). Juntar estas séries com cuidado.
- Contagens de empresas, pessoas e volume de negócios somam-se entre dimensões. A soma pode ficar abaixo do total publicado, porque o Eurostat oculta células confidenciais.

## Power BI

- O modelo foi criado com o script TMDL (`modelo/script_modelo.tmdl`, colado na Exibição TMDL). A data/hora automática está **desativada** neste ficheiro.
- O caminho dos CSV está no parâmetro `PastaSaida` (`expressions.tmdl`), que aponta para `C:\Users\Robson\...\saida\`. Noutro computador, alterar em *Transformar dados › Gerir parâmetros*.
- As medidas estão em `_Medidas`. A pasta "7. Previsão" tem as medidas da página Perspetivas.
- **Páginas:**
  1. Visão geral
  2. Quem compra online
  3. Canais de venda
  4. Estrutura do retalho
  5. Preços e consumo
  6. Perspetivas 2026–2027

  As páginas 1 a 5 têm o filtro de país sincronizado.
- Ao editar o PBIR à mão (`visual.json`), seguir o schema `visualContainer` 2.13.0. Reabrir o `.pbip` para validar.
- `.pbi/cache.abf` e `.pbi/localSettings.json` não vão para o git.
- O editor TMDL pode mostrar avisos de lint que são falsos positivos.

## Previsão (`previsao.py`)

- **Séries:** volume de vendas com ajuste sazonal (SCA), para Portugal e UE27, em quatro canais: retalho total (G47), super e hipermercados (G4711), comércio alimentar especializado (G472) e online (G4791).
- **Modelos:**
  - ETS (Holt-Winters com tendência amortecida)
  - AR (12 desfasamentos, tendência e mês)
  - Ingénuo

  O modelo de cada série é escolhido pelo menor MAPE num backtest. Treino até ago/2025, teste nos 12 meses seguintes.
- **Meses COVID:** mar–jun/2020 e jan–mar/2021 são tratados como outliers e interpolados.
- **Intervalos:** 80% e 95%, a partir de 2000 simulações por bootstrap dos resíduos (centrados).
- **Adoção online:** curva logística (`curve_fit`). É um **cenário**, não uma previsão.
- **Resultados de referência (Portugal):**
  - Retalho: +3,0% em 2026 e +1,5% em 2027 (UE +0,4%).
  - MAPE: 0,7% no retalho total e 4,8% no online.
  - Compradores online: 68% em 2027 e 75% em 2030 (UE 83%).

## Entregáveis

- **Relatório:** "Consumo em Portugal 2010–2027: o que muda para o retalho" (Claude Docs). Exportado para `entregaveis/Relatorio_Consumo_PT_UE.pdf` e `.docx`.
- **Apresentação:** 12 slides. A fonte editável é o deck em Claude Slides. Em `entregaveis/` está a versão PDF/PPTX, com uma imagem por slide e notas do apresentador.
  - Cores: Portugal a verde (#0E7C66) quando o valor é positivo e a vermelho (#C0392B) quando é negativo; UE a azul (#2F6DB5).
  - Fundo #FBFBF8 e azul-marinho #14213D. Tipos de letra: Source Serif 4 nos títulos e Public Sans no texto.
- **Slide 8:** o "top 10" das maiores empresas do retalho é só para curiosidade. Os valores vêm de fontes externas (relatórios das empresas e imprensa, 2024–25), não do Eurostat.
- **Dashboard:** `entregaveis/Dashboard_Tendencias_Consumo_PT_UE.pdf` e `prints/*.png`. Depois de mudar o dashboard, exportar de novo e atualizar as imagens em `docs/dashboard/`.

## Git

- O README é a montra do portfólio: mantê-lo atualizado quando mudarem números, páginas ou entregáveis.
- Não versionar `dados brutos/`. Nenhum ficheiro pode passar de 100 MB.
- Mensagens de commit em português, curtas e no imperativo (ex.: "Adiciona prints do dashboard").
