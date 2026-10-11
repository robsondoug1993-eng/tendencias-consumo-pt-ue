"""
ETL - Tendências de consumo em Portugal e na UE: comércio local, grandes redes e online (Eurostat)

Entrada (pasta RAW): ficheiros TSV do Eurostat (formato largo, uma coluna por período)
    isoc_ec_ibuy.tsv, isoc_ec_ib20.tsv, isoc_ec_ibgs.tsv  - compras online pelos indivíduos
    sts_trtu_m.tsv                                       - vendas do comércio a retalho (mensal)
    sbs_sc_dt_r2.tsv, sbs_sc_ovw.tsv                     - estrutura do retalho por dimensão de empresa
    prc_hicp_aind.tsv                                    - inflação (IHPC) por categoria
    nama_10_co3_p3.tsv                                   - despesa de consumo das famílias por categoria

Saída (pasta OUT): modelo estrela em CSV (UTF-8, separador ;) pronto para o Power BI
    fato_vendas_retalho.csv     - mês, país, atividade -> índices de volume e de valor (2021 = 100)
    fato_compras_online.csv     - ano, país, perfil -> % que comprou online (3 e 12 meses)
    fato_categorias_online.csv  - ano, país, perfil, categoria -> % que comprou cada produto online
    fato_estrutura_retalho.csv  - ano, país, atividade, dimensão -> empresas, pessoas, vol. negócios
    fato_inflacao.csv           - ano, país, categoria COICOP -> taxa de inflação e índice
    fato_consumo_familias.csv   - ano, país, categoria COICOP -> despesa, peso e variação real
    dim_tempo.csv, dim_ano.csv, dim_pais.csv, dim_atividade.csv, dim_dimensao_empresa.csv,
    dim_perfil.csv, dim_categoria_online.csv, dim_coicop.csv
    validacao_totais.csv        - homologação (contagens e somas brutos vs. fatos)

Uso: python etl_consumo.py <pasta_raw> <pasta_saida>
"""
import sys
import os
import re
import pandas as pd

RAW = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "./saida"
os.makedirs(OUT, exist_ok=True)

ANO_INICIO = 2010

# ---------------------------------------------------------------- PARÂMETROS / DE-PARA
# Estados-membros da UE (27) + agregado UE27. Código Eurostat -> (nome PT, ISO3, zona euro)
PAISES = {
    "AT": ("Áustria", "AUT", 1), "BE": ("Bélgica", "BEL", 1), "BG": ("Bulgária", "BGR", 0),
    "HR": ("Croácia", "HRV", 1), "CY": ("Chipre", "CYP", 1), "CZ": ("Chéquia", "CZE", 0),
    "DK": ("Dinamarca", "DNK", 0), "EE": ("Estónia", "EST", 1), "FI": ("Finlândia", "FIN", 1),
    "FR": ("França", "FRA", 1), "DE": ("Alemanha", "DEU", 1), "EL": ("Grécia", "GRC", 1),
    "HU": ("Hungria", "HUN", 0), "IE": ("Irlanda", "IRL", 1), "IT": ("Itália", "ITA", 1),
    "LV": ("Letónia", "LVA", 1), "LT": ("Lituânia", "LTU", 1), "LU": ("Luxemburgo", "LUX", 1),
    "MT": ("Malta", "MLT", 1), "NL": ("Países Baixos", "NLD", 1), "PL": ("Polónia", "POL", 0),
    "PT": ("Portugal", "PRT", 1), "RO": ("Roménia", "ROU", 0), "SK": ("Eslováquia", "SVK", 1),
    "SI": ("Eslovénia", "SVN", 1), "ES": ("Espanha", "ESP", 1), "SE": ("Suécia", "SWE", 0),
    "EU27_2020": ("União Europeia (27)", "EU27", 0),
}
GEO = set(PAISES)

# Atividades do comércio a retalho (NACE Rev. 2) -> (nome, canal de venda, nível, ordem)
ATIVIDADES = {
    "G47": ("Comércio a retalho (total)", "Total", 1, 1),
    "G47_X_G473": ("Retalho exceto combustíveis", "Total", 1, 2),
    "G47_FOOD": ("Retalho alimentar", "Agregado por produto", 2, 3),
    "G47_NFOOD": ("Retalho não alimentar", "Agregado por produto", 2, 4),
    "G47_NF_CLTH": ("Vestuário e calçado", "Agregado por produto", 3, 5),
    "G47_NF_HLTH": ("Saúde e cosmética", "Agregado por produto", 3, 6),
    "G471": ("Lojas não especializadas", "Grandes superfícies", 2, 10),
    "G4711": ("Super e hipermercados", "Grandes superfícies", 3, 11),
    "G4719": ("Lojas de departamento", "Grandes superfícies", 3, 12),
    "G472": ("Comércio alimentar especializado", "Comércio especializado", 2, 20),
    "G473": ("Combustíveis", "Combustíveis", 2, 21),
    "G474": ("Informática e telecomunicações", "Comércio especializado", 2, 22),
    "G475": ("Equipamento para o lar", "Comércio especializado", 2, 23),
    "G476": ("Bens culturais e recreativos", "Comércio especializado", 2, 24),
    "G477": ("Outras lojas especializadas", "Comércio especializado", 2, 25),
    "G478": ("Bancas e mercados", "Mercados e feiras", 2, 30),
    "G479": ("Fora de loja (total)", "Fora de loja", 2, 40),
    "G4791": ("Online (internet e correspondência)", "Online", 3, 41),
}

# Perfis de indivíduos (ind_type) -> (nome, grupo, ordem)
PERFIS = {
    "IND_TOTAL": ("Todos (16-74 anos)", "Total", 1),
    "Y16_24": ("16-24 anos", "Idade", 11), "Y25_34": ("25-34 anos", "Idade", 12),
    "Y35_44": ("35-44 anos", "Idade", 13), "Y45_54": ("45-54 anos", "Idade", 14),
    "Y55_64": ("55-64 anos", "Idade", 15), "Y65_74": ("65-74 anos", "Idade", 16),
    "M_Y16_74": ("Homens", "Sexo", 21), "F_Y16_74": ("Mulheres", "Sexo", 22),
    "I0_2": ("Escolaridade baixa (até 9º ano)", "Escolaridade", 31),
    "I3_4": ("Escolaridade média (secundário)", "Escolaridade", 32),
    "I5_8": ("Ensino superior", "Escolaridade", 33),
    "IND_DEG1": ("Cidades", "Urbanização", 41), "IND_DEG2": ("Vilas e subúrbios", "Urbanização", 42),
    "IND_DEG3": ("Zonas rurais", "Urbanização", 43),
    "HHI_Q1": ("Rendimento 1º quartil (mais baixo)", "Rendimento do agregado", 51),
    "HHI_Q2": ("Rendimento 2º quartil", "Rendimento do agregado", 52),
    "HHI_Q3": ("Rendimento 3º quartil", "Rendimento do agregado", 53),
    "HHI_Q4": ("Rendimento 4º quartil (mais alto)", "Rendimento do agregado", 54),
    "SAL_SELF_FAM": ("Empregados", "Situação profissional", 61),
    "UNE": ("Desempregados", "Situação profissional", 62),
    "STUD": ("Estudantes", "Situação profissional", 63),
    "RETIR_OTHER": ("Reformados e outros inativos", "Situação profissional", 64),
}

# Categorias compradas online (isoc_ec_ibgs, 2020+) -> (nome, tipo, ordem)
CATEGORIAS = {
    "I_BPG_ANY": ("Qualquer bem físico", "Total bens", 1),
    "I_BCLOT1": ("Roupa, calçado e acessórios", "Bens", 10),
    "I_BSPG": ("Artigos de desporto", "Bens", 11),
    "I_BCG": ("Brinquedos e artigos para crianças", "Bens", 12),
    "I_BFURN1": ("Mobiliário, decoração e jardim", "Bens", 13),
    "I_BMUSG": ("Música em CD/vinil", "Bens", 14),
    "I_BFLMG": ("Filmes e séries em DVD/Blu-ray", "Bens", 15),
    "I_BBOOKNLG": ("Livros, revistas e jornais impressos", "Bens", 16),
    "I_BHARD1": ("Computadores, telemóveis e acessórios", "Bens", 17),
    "I_BEEQU1": ("Eletrónica e eletrodomésticos", "Bens", 18),
    "I_BMED1": ("Medicamentos e suplementos", "Bens", 19),
    "I_BFDR": ("Entregas de restaurantes e fast-food", "Bens", 20),
    "I_BFDS": ("Alimentação e bebidas de lojas", "Bens", 21),
    "I_BCBW": ("Cosmética, beleza e bem-estar", "Bens", 22),
    "I_BCPH": ("Limpeza e higiene pessoal", "Bens", 23),
    "I_BBMC": ("Veículos e peças", "Bens", 24),
    "I_BOPG": ("Outros bens físicos", "Bens", 25),
    "I_BRA": ("Alojamento", "Serviços", 30),
    "I_BTPS": ("Serviços de transporte", "Serviços", 31),
    "I_BCTICK": ("Bilhetes para eventos culturais", "Serviços", 32),
    "I_BSTICK": ("Bilhetes para eventos desportivos", "Serviços", 33),
    "I_BHHS": ("Serviços domésticos (limpeza, reparações...)", "Serviços", 34),
    "I_BSIMC": ("Internet e telemóvel (assinaturas)", "Serviços", 35),
    "I_BSUTIL": ("Eletricidade, água e gás (contratos)", "Serviços", 36),
}

# Dimensão de empresa (pessoas ao serviço) -> classes de origem
DIMENSOES = {
    "MICRO": ("Micro (0-9)", 1, {"0-9"}, {"0_1", "2-9"}),
    "PEQUENA": ("Pequena (10-49)", 2, set(), {"10-19", "20-49"}),
    "MEDIA": ("Média (50-249)", 3, {"50-249"}, set()),
    "GRANDE": ("Grande (250+)", 4, {"GE250"}, set()),
}

COICOP = {
    "CP00": "Total", "CP01": "Alimentação e bebidas não alcoólicas",
    "CP02": "Bebidas alcoólicas e tabaco", "CP03": "Vestuário e calçado",
    "CP04": "Habitação, água, eletricidade e gás", "CP05": "Mobiliário e equipamento doméstico",
    "CP06": "Saúde", "CP07": "Transportes", "CP08": "Comunicações",
    "CP09": "Lazer e cultura", "CP10": "Educação", "CP11": "Restaurantes e hotéis",
    "CP12": "Bens e serviços diversos",
}

validacao = []


# ---------------------------------------------------------------- EXTRAÇÃO
def ler_tsv(nome):
    """Lê o TSV largo do Eurostat e devolve formato longo: chaves + PERIODO + VALOR + FLAG."""
    df = pd.read_csv(os.path.join(RAW, nome), sep="\t", dtype=str)
    col_chave = df.columns[0]
    chaves = col_chave.split("\\")[0].split(",")
    k = df[col_chave].str.split(",", expand=True)
    k.columns = chaves
    df = pd.concat([k, df.drop(columns=col_chave)], axis=1)
    df.columns = [c.strip() for c in df.columns]
    longo = df.melt(id_vars=chaves, var_name="PERIODO", value_name="BRUTO")
    # "12.3 e" -> valor 12.3, flag "e";  ":" -> sem dado
    partes = longo.BRUTO.str.strip().str.extract(r"^([-0-9.]+|:)\s*([a-z]*)$")
    longo["VALOR"] = pd.to_numeric(partes[0].where(partes[0] != ":"), errors="coerce")
    longo["FLAG"] = partes[1].fillna("")
    longo = longo.dropna(subset=["VALOR"]).drop(columns="BRUTO")
    print(f"lido {nome}: {len(df):,} séries, {len(longo):,} valores")
    return longo


def ano(s):
    return s.str[:4].astype(int)


def registar(fonte, filtro, df_fonte, df_fato, col_fonte="VALOR", col_fato=None):
    validacao.append({"FONTE": fonte, "FILTRO": filtro, "LINHAS_FONTE": len(df_fonte),
                      "SOMA_FONTE": round(df_fonte[col_fonte].sum(), 2),
                      "SOMA_FATO": round(df_fato[col_fato].sum(), 2) if col_fato else None})


# ---------------------------------------------------------------- 1. VENDAS DO RETALHO (mensal)
v = ler_tsv("sts_trtu_m.tsv")
v = v[v.geo.isin(GEO) & v.nace_r2.isin(ATIVIDADES) & v.s_adj.eq("SCA") & v.unit.eq("I21")
      & (ano(v.PERIODO) >= ANO_INICIO)]
v["DATA"] = pd.to_datetime(v.PERIODO + "-01").dt.date
fato_vendas = (v.pivot_table(index=["DATA", "geo", "nace_r2"], columns="indic_bt",
                             values="VALOR", aggfunc="first")
               .rename(columns={"VOL_SLS": "IDX_VOLUME", "NETTUR": "IDX_VALOR"}).reset_index()
               .rename(columns={"geo": "CO_GEO", "nace_r2": "CO_NACE"}))
fato_vendas.columns.name = None
fato_vendas = fato_vendas[["DATA", "CO_GEO", "CO_NACE", "IDX_VOLUME", "IDX_VALOR"]]
for ind, col in (("VOL_SLS", "IDX_VOLUME"), ("NETTUR", "IDX_VALOR")):
    registar("sts_trtu_m", f"{ind}, SCA, I21", v[v.indic_bt == ind], fato_vendas, col_fato=col)

# ---------------------------------------------------------------- 2. COMPRAS ONLINE (anual)
partes = []
for arq, serie in (("isoc_ec_ibuy.tsv", "2010-2019"), ("isoc_ec_ib20.tsv", "2020+")):
    o = ler_tsv(arq)
    o = o[o.geo.isin(GEO) & o.ind_type.isin(PERFIS) & o.unit.eq("PC_IND")
          & o.indic_is.isin(["I_BUY3", "I_BLT12"]) & (ano(o.PERIODO) >= ANO_INICIO)]
    if serie == "2010-2019":
        o = o[ano(o.PERIODO) <= 2019]  # a série nova substitui a antiga a partir de 2020
    o["SERIE"] = serie
    partes.append(o)
o = pd.concat(partes)
o["ANO"] = ano(o.PERIODO)
fato_online = (o.pivot_table(index=["ANO", "geo", "ind_type", "SERIE"], columns="indic_is",
                             values="VALOR", aggfunc="first")
               .rename(columns={"I_BUY3": "PCT_COMPROU_3M", "I_BLT12": "PCT_COMPROU_12M"}).reset_index()
               .rename(columns={"geo": "CO_GEO", "ind_type": "CO_PERFIL"}))
fato_online.columns.name = None
fato_online = fato_online[["ANO", "CO_GEO", "CO_PERFIL", "PCT_COMPROU_3M", "PCT_COMPROU_12M", "SERIE"]]
registar("isoc_ec_ibuy+ib20", "I_BUY3, PC_IND", o[o.indic_is == "I_BUY3"], fato_online,
         col_fato="PCT_COMPROU_3M")

# ---------------------------------------------------------------- 3. CATEGORIAS ONLINE (anual, 2020+)
c = ler_tsv("isoc_ec_ibgs.tsv")
c = c[c.geo.isin(GEO) & c.ind_type.isin(PERFIS) & c.indic_is.isin(CATEGORIAS)
      & c.unit.isin(["PC_IND", "PC_IND_BUY3"])]
c["ANO"] = ano(c.PERIODO)
fato_cat = (c.pivot_table(index=["ANO", "geo", "ind_type", "indic_is"], columns="unit",
                          values="VALOR", aggfunc="first")
            .rename(columns={"PC_IND": "PCT_INDIVIDUOS", "PC_IND_BUY3": "PCT_COMPRADORES"}).reset_index()
            .rename(columns={"geo": "CO_GEO", "ind_type": "CO_PERFIL", "indic_is": "CO_CATEGORIA"}))
fato_cat.columns.name = None
fato_cat = fato_cat[["ANO", "CO_GEO", "CO_PERFIL", "CO_CATEGORIA", "PCT_INDIVIDUOS", "PCT_COMPRADORES"]]
registar("isoc_ec_ibgs", "PC_IND", c[c.unit == "PC_IND"], fato_cat, col_fato="PCT_INDIVIDUOS")

# ---------------------------------------------------------------- 4. ESTRUTURA DO RETALHO (anual)
NACE_SBS = [n for n in ATIVIDADES if re.fullmatch(r"G47\d?", n)]
antigo = ler_tsv("sbs_sc_dt_r2.tsv").rename(columns={"indic_sb": "IND"})
antigo["IND"] = antigo.IND.map({"V11110": "N_EMPRESAS", "V16110": "N_PESSOAS",
                                "V12110": "VOLUME_NEGOCIOS_MEUR"})
antigo = antigo[ano(antigo.PERIODO) <= 2020].assign(SERIE="2010-2020")
novo = ler_tsv("sbs_sc_ovw.tsv").rename(columns={"indic_sbs": "IND"})
novo["IND"] = novo.IND.map({"ENT_NR": "N_EMPRESAS", "EMP_NR": "N_PESSOAS",
                            "NETTUR_MEUR": "VOLUME_NEGOCIOS_MEUR"})
novo = novo.assign(SERIE="2021+")
s = pd.concat([antigo, novo])
s = s[s.geo.isin(GEO) & s.nace_r2.isin(NACE_SBS) & s.IND.notna() & (ano(s.PERIODO) >= ANO_INICIO)]
s["ANO"] = ano(s.PERIODO)
chave = ["ANO", "geo", "nace_r2", "IND", "SERIE"]

# Agrupa as classes de dimensão: usa a classe direta (ex.: 0-9) e, se não existir, soma as
# subclasses (0_1 + 2-9) — só quando TODAS as subclasses têm valor (evita totais incompletos).
grupos = []
for cod, (_, _, direta, subclasses) in DIMENSOES.items():
    d = s[s.size_emp.isin(direta)].groupby(chave)["VALOR"].sum()
    if subclasses:
        sub = s[s.size_emp.isin(subclasses)].groupby(chave)["VALOR"].agg(["sum", "count"])
        sub = sub.loc[sub["count"] == len(subclasses), "sum"]
        d = d.combine_first(sub)
    grupos.append(d.rename(cod))
g = pd.concat(grupos, axis=1).reset_index().melt(id_vars=chave, var_name="CO_DIMENSAO",
                                                  value_name="VALOR").dropna(subset=["VALOR"])
fato_estrutura = (g.pivot_table(index=["ANO", "geo", "nace_r2", "CO_DIMENSAO", "SERIE"], columns="IND",
                                values="VALOR", aggfunc="first").reset_index()
                  .rename(columns={"geo": "CO_GEO", "nace_r2": "CO_NACE"}))
fato_estrutura.columns.name = None
fato_estrutura = fato_estrutura[["ANO", "CO_GEO", "CO_NACE", "CO_DIMENSAO", "N_EMPRESAS", "N_PESSOAS",
                                 "VOLUME_NEGOCIOS_MEUR", "SERIE"]]
fato_estrutura[["N_EMPRESAS", "N_PESSOAS"]] = fato_estrutura[["N_EMPRESAS", "N_PESSOAS"]].round().astype("Int64")

# Validação: soma das dimensões vs. TOTAL publicado (diferenças = dados confidenciais)
tot = s[s.size_emp == "TOTAL"].groupby(["ANO", "geo", "nace_r2", "IND"])["VALOR"].sum()
som = g.groupby(["ANO", "geo", "nace_r2", "IND"])["VALOR"].sum()
cob = pd.concat([tot.rename("TOTAL"), som.rename("SOMA")], axis=1).dropna()
cob = cob[cob.TOTAL > 0]
for ind in ("N_EMPRESAS", "N_PESSOAS", "VOLUME_NEGOCIOS_MEUR"):
    x = cob.xs(ind, level="IND")
    exato = ((x.SOMA - x.TOTAL).abs() / x.TOTAL < 0.001).mean()
    validacao.append({"FONTE": "sbs (dimensões vs. TOTAL)", "FILTRO": ind, "LINHAS_FONTE": len(x),
                      "SOMA_FONTE": round(x.TOTAL.sum(), 2), "SOMA_FATO": round(x.SOMA.sum(), 2),
                      "PCT_SERIES_IGUAIS_AO_TOTAL": round(100 * exato, 1)})

# ---------------------------------------------------------------- 5. INFLAÇÃO (anual)
h = ler_tsv("prc_hicp_aind.tsv")
h = h[h.geo.isin(GEO) & h.coicop.isin(COICOP) & h.unit.isin(["RCH_A_AVG", "INX_A_AVG"])
      & (ano(h.PERIODO) >= ANO_INICIO)]
h["ANO"] = ano(h.PERIODO)
fato_inflacao = (h.pivot_table(index=["ANO", "geo", "coicop"], columns="unit", values="VALOR",
                               aggfunc="first")
                 .rename(columns={"RCH_A_AVG": "TAXA_INFLACAO_PCT", "INX_A_AVG": "INDICE_2015"})
                 .reset_index().rename(columns={"geo": "CO_GEO", "coicop": "CO_COICOP"}))
fato_inflacao.columns.name = None
fato_inflacao = fato_inflacao[["ANO", "CO_GEO", "CO_COICOP", "TAXA_INFLACAO_PCT", "INDICE_2015"]]
registar("prc_hicp_aind", "RCH_A_AVG", h[h.unit == "RCH_A_AVG"], fato_inflacao,
         col_fato="TAXA_INFLACAO_PCT")

# ---------------------------------------------------------------- 6. CONSUMO DAS FAMÍLIAS (anual)
n = ler_tsv("nama_10_co3_p3.tsv")
n["coicop"] = n.coicop.replace({"TOTAL": "CP00"})
n = n[n.geo.isin(GEO) & n.coicop.isin(COICOP)
      & n.unit.isin(["CP_MEUR", "PC_TOT", "CLV_PCH_PRE", "CP_EUR_HAB"]) & (ano(n.PERIODO) >= ANO_INICIO)]
n["ANO"] = ano(n.PERIODO)
fato_consumo = (n.pivot_table(index=["ANO", "geo", "coicop"], columns="unit", values="VALOR",
                              aggfunc="first")
                .rename(columns={"CP_MEUR": "DESPESA_MEUR", "PC_TOT": "PESO_PCT",
                                 "CLV_PCH_PRE": "VAR_REAL_PCT", "CP_EUR_HAB": "DESPESA_EUR_HAB"})
                .reset_index().rename(columns={"geo": "CO_GEO", "coicop": "CO_COICOP"}))
fato_consumo.columns.name = None
fato_consumo = fato_consumo[["ANO", "CO_GEO", "CO_COICOP", "DESPESA_MEUR", "PESO_PCT",
                             "VAR_REAL_PCT", "DESPESA_EUR_HAB"]]
registar("nama_10_co3_p3", "CP_MEUR", n[n.unit == "CP_MEUR"], fato_consumo, col_fato="DESPESA_MEUR")

# ---------------------------------------------------------------- DIMENSÕES
datas = pd.to_datetime(sorted(fato_vendas.DATA.unique()))
dim_tempo = pd.DataFrame({"DATA": datas.date, "ANO": datas.year, "MES": datas.month,
                          "NOME_MES": datas.month.map({1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai",
                                                       6: "Jun", 7: "Jul", 8: "Ago", 9: "Set",
                                                       10: "Out", 11: "Nov", 12: "Dez"}),
                          "TRIMESTRE": "T" + datas.quarter.astype(str),
                          "SEMESTRE": "S" + ((datas.month - 1) // 6 + 1).astype(str)})


def fase(a):
    if a <= 2019:
        return "1. Pré-pandemia (≤2019)"
    if a <= 2021:
        return "2. Pandemia (20-21)"
    if a <= 2023:
        return "3. Inflação (22-23)"
    return "4. Pós-inflação (24+)"


anos = sorted(set(dim_tempo.ANO) | set(fato_online.ANO) | set(fato_estrutura.ANO)
              | set(fato_inflacao.ANO) | set(fato_consumo.ANO))
dim_ano = pd.DataFrame({"ANO": anos, "FASE": [fase(a) for a in anos]})

dim_pais = pd.DataFrame([{"CO_GEO": k, "NO_PAIS": v[0], "ISO3": v[1],
                          "ZONA_EURO": "Sim" if v[2] else "Não",
                          "TIPO": "Agregado" if k == "EU27_2020" else "País",
                          "DESTAQUE": "Portugal" if k == "PT" else ("UE27" if k == "EU27_2020" else "Outros")}
                         for k, v in PAISES.items()])
dim_atividade = pd.DataFrame([{"CO_NACE": k, "NO_ATIVIDADE": v[0], "CANAL": v[1], "NIVEL": v[2],
                               "ORDEM": v[3]} for k, v in ATIVIDADES.items()])
dim_perfil = pd.DataFrame([{"CO_PERFIL": k, "NO_PERFIL": v[0], "GRUPO": v[1], "ORDEM": v[2]}
                           for k, v in PERFIS.items()])
dim_categoria = pd.DataFrame([{"CO_CATEGORIA": k, "NO_CATEGORIA": v[0], "TIPO": v[1], "ORDEM": v[2]}
                              for k, v in CATEGORIAS.items()])
dim_dimensao = pd.DataFrame([{"CO_DIMENSAO": k, "NO_DIMENSAO": v[0], "ORDEM": v[1]}
                             for k, v in DIMENSOES.items()])
dim_coicop = pd.DataFrame([{"CO_COICOP": k, "NO_COICOP": v, "ORDEM": i}
                           for i, (k, v) in enumerate(COICOP.items())])

# ---------------------------------------------------------------- VALIDAÇÃO DE INTEGRIDADE
checks = [(fato_vendas, ["DATA", "CO_GEO", "CO_NACE"]), (fato_online, ["ANO", "CO_GEO", "CO_PERFIL"]),
          (fato_cat, ["ANO", "CO_GEO", "CO_PERFIL", "CO_CATEGORIA"]),
          (fato_estrutura, ["ANO", "CO_GEO", "CO_NACE", "CO_DIMENSAO"]),
          (fato_inflacao, ["ANO", "CO_GEO", "CO_COICOP"]), (fato_consumo, ["ANO", "CO_GEO", "CO_COICOP"])]
for df, k in checks:
    assert not df.duplicated(k).any(), f"Chave duplicada em {k}"
    assert df.CO_GEO.isin(dim_pais.CO_GEO).all()
assert fato_vendas.CO_NACE.isin(dim_atividade.CO_NACE).all()
assert fato_estrutura.CO_NACE.isin(dim_atividade.CO_NACE).all()
assert fato_cat.CO_CATEGORIA.isin(dim_categoria.CO_CATEGORIA).all()
for linha in validacao[:]:
    if linha.get("SOMA_FATO") is not None and "dimensões" not in linha["FONTE"]:
        assert abs(linha["SOMA_FONTE"] - linha["SOMA_FATO"]) < 0.01, f"Divergência em {linha}"
val = pd.DataFrame(validacao)

# ---------------------------------------------------------------- CARGA
saidas = {"fato_vendas_retalho": fato_vendas, "fato_compras_online": fato_online,
          "fato_categorias_online": fato_cat, "fato_estrutura_retalho": fato_estrutura,
          "fato_inflacao": fato_inflacao, "fato_consumo_familias": fato_consumo,
          "dim_tempo": dim_tempo, "dim_ano": dim_ano, "dim_pais": dim_pais,
          "dim_atividade": dim_atividade, "dim_perfil": dim_perfil,
          "dim_categoria_online": dim_categoria, "dim_dimensao_empresa": dim_dimensao,
          "dim_coicop": dim_coicop, "validacao_totais": val}
for nome, df in saidas.items():
    df.to_csv(os.path.join(OUT, f"{nome}.csv"), sep=";", index=False, encoding="utf-8-sig",
              decimal=",")
    print(f"gravado {nome}.csv: {len(df):,} linhas")
print(val.to_string(index=False))
