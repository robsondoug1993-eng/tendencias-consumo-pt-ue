# Guia de montagem no Power BI – Tendências de Consumo PT x UE

## 1. Criar o modelo de uma vez (script TMDL)

O ficheiro `script_modelo.tmdl` cria tudo de uma vez: as 14 tabelas (importadas dos CSV de `saida`), as 21 relações, as ordenações e as 39 medidas DAX.

1. Abra o Power BI Desktop com um relatório em branco.
2. Na barra lateral esquerda, clique em **Exibição TMDL** (ícone `</>`, abaixo de Relatório/Tabela/Modelo).
   - Se não aparecer, ative-a em *Ficheiro > Opções e definições > Opções > Funcionalidades de pré-visualização > Exibição TMDL* e reinicie o Power BI.
3. Abra `script_modelo.tmdl` no Bloco de Notas, copie tudo (Ctrl+A, Ctrl+C) e cole no editor TMDL.
4. Clique em **Aplicar** (botão ▶ no topo do editor).
5. Volte à vista de Relatório e clique em **Atualizar** (Base > Atualizar) para carregar os dados.
6. Guarde como `saida\Tendencias_Consumo_PT_UE.pbix`.

O caminho dos CSV fica no parâmetro `PastaSaida`. Se mudar a pasta de lugar, altere-o em *Transformar dados > Editar parâmetros*.

**Alternativa manual (se a Exibição TMDL não estiver disponível):** importe cada CSV com *Obter dados > Texto/CSV* (delimitador ponto e vírgula, origem 65001 UTF-8, região Português (Portugal)). Crie as relações da secção 2 e as medidas a partir de `medidas.dax`.

## 2. Modelo estrela

```
                 dim_ano ──► dim_tempo ──► fato_vendas_retalho ◄── dim_atividade
                    │                              ▲                     │
                    │                         dim_pais                   │
                    ▼                              │                     ▼
 fato_compras_online, fato_categorias_online, fato_estrutura_retalho, fato_inflacao, fato_consumo_familias
        ▲                     ▲                       ▲                      ▲
   dim_perfil      dim_categoria_online      dim_dimensao_empresa        dim_coicop
```

- Todas as relações são muitos-para-um, filtrando da dimensão para a fato (direção única).
- **dim_ano** filtra todas as fatos. A de vendas, que é mensal, é filtrada através de dim_tempo. Assim, um único filtro de ano serve para todas as páginas.
- **dim_pais** e **dim_ano** são partilhadas por todas as fatos.
- As colunas-chave das fatos ficam ocultas: use sempre os campos das dimensões nos visuais.

## 3. Medidas (tabela `_Medidas`)

| Pasta | Medidas principais | Regra padrão |
|---|---|---|
| 1. Vendas do retalho | Índice de volume / valor, Volume vs 2019 %, Volume var. homóloga %, Variação de preços desde 2021 %, Volume por canal, Online vs retalho desde 2019 (pp) | Sem atividade filtrada → retalho total (G47) |
| 2. Compras online | % comprou online (12 e 3 meses), % online PT / UE27, Diferença PT vs UE (pp), Var. vs ano anterior (pp), Ranking UE | Sem perfil filtrado → total da população |
| 3. Categorias online | % pessoas que compraram, % dos compradores, % pessoas · último ano disponível | Idem |
| 4. Estrutura do retalho | Nº de empresas, Pessoas, Volume de negócios, % por dimensão, VN por empresa, Quota grandes / micro, Var. vs 2010 | Sem atividade filtrada → G47 |
| 5. Preços e consumo | Inflação anual %, Índice de preços, Inflação acumulada desde 2021 %, Despesa, Peso na despesa %, Variação real %, Despesa por habitante | Sem categoria filtrada → total (CP00) |
| 6. Formatação | Cor de destaque | Portugal verde, UE27 cinzento escuro, restantes cinzento claro |

Regras importantes:
- Índices e percentagens são **médias**, nunca somas.
- **País** é um segmentador de seleção única em todas as páginas (padrão: Portugal). Sem ele, as medidas misturam países.
- Nos cartões das páginas, fixe o ano no filtro do visual: 2025 para online e vendas, 2024 para a estrutura de empresas.

## 4. Páginas do dashboard

Segmentadores sincronizados em todas as páginas (*Ver > Sincronizar segmentações*):
- **País:** `dim_pais[NO_PAIS]`, seleção única, padrão Portugal.
- **Ano:** `dim_ano[ANO]`, intervalo.

### Página 1 – Visão geral (estratégico)
- **Cartões:**
  - % comprou online (12 meses), com ano 2025
  - Diferença PT vs UE (pp)
  - Volume vs 2019 %, com ano 2025
  - Online vs retalho desde 2019 (pp)
  - Quota das grandes empresas no VN %, com ano 2024
  - Inflação acumulada desde 2021 %
- **Linhas mensais:** eixo `dim_tempo[DATA]`; valores Volume · Retalho total, Volume · Online, Volume · Super e hipermercados e Volume · Comércio alimentar especializado.
- **Linhas anuais:** eixo `dim_ano[ANO]`; valores % online · Portugal e % online · UE27.
- **Caixa de texto:** 3 conclusões (ver secção 6).

### Página 2 – Quem compra online
- **Linhas:** % comprou online (12 meses) por `dim_ano[ANO]`, com PT e UE27 como 2 medidas.
- **Barras por perfil:** `dim_perfil[NO_PERFIL]` × % comprou online (12 meses), ano 2025. Segmentador de botões com `dim_perfil[GRUPO]` (Idade, Escolaridade, Rendimento, Urbanização, Sexo, Situação profissional).
- **Ranking UE:** barras `dim_pais[NO_PAIS]` × % comprou online (12 meses). Cor das barras: fx > Valor do campo > Cor de destaque. O filtro de país deste visual fica desligado (*Formatar > Editar interações*).
- **Cartão:** Ranking UE · compras online.
- **Barras por categoria:** `dim_categoria_online[NO_CATEGORIA]` × % pessoas · último ano disponível, com filtro `TIPO`. Para comparar com antes, use barras agrupadas com legenda `dim_ano[ANO]` filtrada em 2020 e 2024.

### Página 3 – Canais de venda (local, grandes superfícies, online)
- **Linhas mensais:** Índice de volume por `dim_atividade[NO_ATIVIDADE]`, com filtro CO_NACE = G4711, G472, G478, G4791.
- **Barras:** Volume vs 2019 % por `dim_atividade[NO_ATIVIDADE]` (NIVEL 2 e 3), ano 2025.
- **Linhas:** Índice de valor e Índice de volume (retalho total). O afastamento entre as duas é o efeito dos preços. Ao lado, cartão Variação de preços desde 2021 %.
- **Matriz:** linhas `NO_ATIVIDADE`, colunas `dim_ano[FASE]`, valor Índice de volume, com escala de cores.

### Página 4 – Estrutura do retalho (pequeno comércio x grandes empresas)
- **Colunas 100% empilhadas:** eixo `dim_ano[ANO]`, legenda `dim_dimensao_empresa[NO_DIMENSAO]`, valor % das empresas.
- **Colunas 100% empilhadas:** igual ao anterior, com o valor % do volume de negócios. O contraste entre os dois gráficos é a mensagem principal.
- **Linhas:** Nº de empresas por ano. Adicione uma linha de referência em 2020/2021: é a quebra de série, explicada em nota.
- **Barras:** Volume de negócios por empresa (mil €) por dimensão.
- **Tabela:** `dim_atividade[NO_ATIVIDADE]` (NIVEL 2) × Quota das grandes empresas no VN %.

### Página 5 – Preços e consumo (contexto)
- **Colunas:** Inflação anual % por ano.
- **Barras:** Inflação acumulada desde 2021 % por `dim_coicop[NO_COICOP]` (sem Total).
- **Barras agrupadas:** Peso na despesa % por `NO_COICOP`, anos 2010 e último ano.
- **Linhas:** Variação real do consumo %.
- **Dispersão UE:** X = % comprou online (12 meses); Y = Quota das grandes empresas no VN %; detalhes `dim_pais[NO_PAIS]`, ano 2024. Responde se os países mais digitais têm o retalho mais concentrado.

## 5. Homologação – valores esperados

Confira estes números depois de atualizar. Foram calculados diretamente dos CSV.

| Verificação | Filtro | Valor esperado |
|---|---|---|
| % comprou online (12 meses) | Portugal, 2025 | 60,5% |
| % comprou online (12 meses) | UE27, 2025 | 73,6% |
| Diferença PT vs UE (pp) | 2025 | −13,1 |
| Ranking UE · compras online | Portugal, 2025 | 23 |
| % comprou online, 25-34 anos / 65-74 anos | Portugal, 2025 | 86,6% / 19,8% |
| % comprou online, ensino superior / escolaridade baixa | Portugal, 2025 | 84,8% / 31,2% |
| Volume vs 2019 % – retalho total | Portugal, 2025 | +15,2% |
| Volume vs 2019 % – super e hipermercados | Portugal, 2025 | +19,3% |
| Volume vs 2019 % – comércio alimentar especializado | Portugal, 2025 | −5,3% |
| Volume vs 2019 % – online | Portugal, 2025 | +42,0% (UE: +54,9%) |
| Nº de empresas | Portugal, 2010 → 2024 | 154 467 → 123 721 |
| % das empresas – micro | Portugal, 2024 | 95,8% |
| Quota das grandes empresas no VN % | Portugal, 2010 → 2024 | 36,3% → 44,3% |
| Inflação acumulada desde 2021 % | Portugal, 2025 | 19,4% |
| Inflação anual % | Portugal, 2022 | 8,1% |

## 6. Primeiras conclusões (para a caixa de texto / relatório)

1. **O online cresceu, mas Portugal continua atrás.** A percentagem de compradores online passou de 15% para 61% entre 2010 e 2025. Mesmo assim, o país está em 23º lugar na UE e a 13 pp da média europeia, com um fosso grande por idade e escolaridade.
2. **Quem ganhou foram as grandes superfícies, não o comércio local.** Desde 2019, os super e hipermercados cresceram 19% em volume, enquanto as lojas alimentares especializadas caíram 5%.
3. **O retalho concentrou-se.** Há menos 30 mil empresas do que em 2010, quase todas microempresas. As 97 grandes empresas faturam 44% do total.

## 7. Notas metodológicas
- Fonte: Eurostat. Dados descarregados a 11/10/2026; o detalhe está em `LEIA-ME.md`.
- **Quebras de série:** compras online em 2020 (novo inquérito) e estrutura empresarial em 2021 (novo regulamento SBS).
- **Categorias online:** os bens são inquiridos até 2024; alguns serviços só em anos alternados.
- **Totais por dimensão de empresa:** podem ficar abaixo do total oficial por confidencialidade estatística (ver `validacao_totais.csv`).
