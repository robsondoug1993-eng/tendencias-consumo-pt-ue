"""
Previsão - Vendas do comércio a retalho por canal (Portugal e UE27), set/2026 a dez/2027
            + projeção da adoção de compras online (cenário até 2030)

Entrada:
    <pasta_raw>/sts_trtu_m.tsv            (Eurostat, vendas do retalho mensais)
    <pasta_saida>/fato_compras_online.csv  (gerado pelo etl_consumo.py)
Saída (pasta_saida, CSV ; decimal ,):
    fato_previsao.csv          - série mensal real + prevista, com intervalos de 80% e 95%
    previsao_metricas.csv      - backtest (erro MAPE de cada modelo em cada série)
    previsao_resumo_anual.csv  - crescimento anual 2025, 2026 e 2027 por canal (com intervalo de 80%)
    fato_projecao_online.csv   - % de compradores online: real e curva logística até 2030
    grafico_previsao.png, grafico_online.png

Método
    Modelos comparados em cada série (escolhe-se o de menor MAPE no backtest):
      1. ETS  - Holt-Winters aditivo com tendência amortecida (sazonal só nas séries sem ajuste)
      2. AR   - regressão autorregressiva (12 desfasamentos + tendência + mês), previsão recursiva
      3. Ingénuo - último valor (séries ajustadas) ou mesmo mês do ano anterior (séries brutas)
    Backtest: treino até ago/2025, teste nos 12 meses seguintes (set/2025 a ago/2026).
    Pandemia: meses de confinamento (mar-jun/2020, jan-mar/2021) substituídos por interpolação no treino.
    Intervalos: 2000 trajetórias simuladas por bootstrap dos resíduos.

Uso: python previsao.py <pasta_raw> <pasta_saida>
"""
import sys
import os
import numpy as np
import pandas as pd
from scipy.optimize import minimize, curve_fit

RAW = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "./saida"
RNG = np.random.default_rng(42)
N_SIM = 2000
FIM_TREINO_BT = "2025-08-01"
FIM_PREVISAO = "2027-12-01"
COVID = ["2020-03-01", "2020-04-01", "2020-05-01", "2020-06-01",
         "2021-01-01", "2021-02-01", "2021-03-01"]

CANAIS = {"G47": "Retalho (total)", "G4711": "Super e hipermercados",
          "G472": "Comércio alimentar especializado", "G4791": "Online (internet e correspondência)"}
GEOS = {"PT": "Portugal", "EU27_2020": "UE27"}
ORDEM = {c: i + 1 for i, c in enumerate(CANAIS)}
# (país, atividade, indicador, ajuste)
SERIES = ([("PT", c, "VOL_SLS", "SCA") for c in CANAIS] + [("PT", c, "VOL_SLS", "NSA") for c in CANAIS]
          + [("PT", "G47", "NETTUR", "SCA")] + [("EU27_2020", c, "VOL_SLS", "SCA") for c in CANAIS])


# ---------------------------------------------------------------- DADOS
def ler_sts():
    df = pd.read_csv(os.path.join(RAW, "sts_trtu_m.tsv"), sep="\t", dtype=str)
    col = df.columns[0]
    k = df[col].str.split(",", expand=True)
    k.columns = col.split("\\")[0].split(",")
    df = pd.concat([k, df.drop(columns=col)], axis=1)
    df.columns = [c.strip() for c in df.columns]
    df = df[df.unit.eq("I21") & df.geo.isin(["PT", "EU27_2020"]) & df.nace_r2.isin(CANAIS)]
    longo = df.melt(id_vars=["freq", "indic_bt", "nace_r2", "s_adj", "unit", "geo"], var_name="P", value_name="B")
    longo["VALOR"] = pd.to_numeric(longo.B.str.strip().str.extract(r"^([-0-9.]+)")[0], errors="coerce")
    longo["DATA"] = pd.to_datetime(longo.P + "-01")
    return longo.dropna(subset=["VALOR"])


def serie(d, geo, nace, ind, adj):
    s = d[(d.geo == geo) & (d.nace_r2 == nace) & (d.indic_bt == ind) & (d.s_adj == adj)]
    s = s.set_index("DATA").VALOR.sort_index()
    return s[s.index >= "2010-01-01"].asfreq("MS")


def limpar_covid(s, sazonal):
    """Substitui os meses de confinamento: interpolação (ajustadas) ou perfil sazonal de 2019 (brutas)."""
    s = s.copy()
    idx = [pd.Timestamp(c) for c in COVID if pd.Timestamp(c) in s.index]
    if sazonal:
        # mesmo mês de 2019 x (nível recente / nível de 2019 num mês sem confinamento)
        ancora = {2020: ("2020-02-01", "2019-02-01"), 2021: ("2021-06-01", "2019-06-01")}
        orig = s.copy()
        for t in idx:
            a, a19 = ancora[t.year]
            s[t] = orig[t.replace(year=2019)] * orig[pd.Timestamp(a)] / orig[pd.Timestamp(a19)]
    else:
        s[idx] = np.nan
        s = s.interpolate()
    return s


# ---------------------------------------------------------------- MODELOS
def ets_fit(y, m):
    """Holt-Winters aditivo, tendência amortecida; devolve parâmetros, estados e resíduos."""
    y = np.asarray(y, float)
    saz = m > 1

    def corre(p, guardar=False):
        a, b, g, phi = p
        l, t = y[:12].mean() if saz else y[0], (y[12:24].mean() - y[:12].mean()) / 12 if saz else y[1] - y[0]
        s = list(y[:12] - y[:12].mean()) if saz else [0.0] * 12
        res = []
        for i in range(len(y)):
            si = s[i % 12] if saz else 0.0
            prev = l + phi * t + si
            e = y[i] - prev
            res.append(e)
            l_novo = l + phi * t + a * e
            t = phi * t + b * e
            if saz:
                s[i % 12] = si + g * e
            l = l_novo
        if guardar:
            return np.array(res), (l, t, s)
        return np.sum(np.array(res[12:]) ** 2)

    x0, lim = [0.3, 0.05, 0.1, 0.95], [(0.01, 0.99), (0.0, 0.5), (0.0, 0.9 if saz else 0.0), (0.8, 0.99)]
    p = minimize(corre, x0, bounds=lim, method="L-BFGS-B").x
    res, est = corre(p, guardar=True)
    r = res[12:]
    return {"p": p, "est": est, "res": r - r.mean(), "saz": saz, "n": len(y)}  # resíduos centrados


def ets_sim(f, h, nsim):
    a, b, g, phi = f["p"]
    caminhos = np.zeros((nsim, h))
    for k in range(nsim):
        l, t, s = f["est"][0], f["est"][1], list(f["est"][2])
        erros = RNG.choice(f["res"], h)
        for j in range(h):
            si = s[(f["n"] + j) % 12] if f["saz"] else 0.0
            y = l + phi * t + si + erros[j]
            caminhos[k, j] = y
            e = erros[j]
            l, t = l + phi * t + a * e, phi * t + b * e
            if f["saz"]:
                s[(f["n"] + j) % 12] = si + g * e
    return caminhos


def ets_pontual(f, h):
    a, b, g, phi = f["p"]
    l, t, s = f["est"][0], f["est"][1], f["est"][2]
    out, damp = [], 0.0
    for j in range(h):
        damp += phi ** (j + 1)
        out.append(l + damp * t + (s[(f["n"] + j) % 12] if f["saz"] else 0.0))
    return np.array(out)


def ar_desenho(y, datas, i, lags=12):
    return np.r_[1.0, i / 120.0, y[i - lags:i][::-1], np.eye(12)[datas[i].month - 1][1:]]


def ar_fit(y, datas, lags=12):
    y = np.asarray(y, float)
    X = np.array([ar_desenho(y, datas, i, lags) for i in range(lags, len(y))])
    beta, *_ = np.linalg.lstsq(X, y[lags:], rcond=None)
    return {"beta": beta, "res": y[lags:] - X @ beta, "y": y, "datas": list(datas)}


def ar_sim(f, h, nsim, pontual=False):
    caminhos = np.zeros((1 if pontual else nsim, h))
    fut = pd.date_range(f["datas"][-1] + pd.DateOffset(months=1), periods=h, freq="MS")
    for k in range(caminhos.shape[0]):
        y, datas = list(f["y"]), f["datas"] + list(fut)
        erros = np.zeros(h) if pontual else RNG.choice(f["res"], h)
        for j in range(h):
            i = len(y)
            v = float(ar_desenho(np.array(y), datas, i) @ f["beta"]) + erros[j]
            y.append(v)
            caminhos[k, j] = v
    return caminhos[0] if pontual else caminhos


def ingenuo(y, h, sazonal):
    y = np.asarray(y, float)
    return np.array([y[len(y) - 12 + (j % 12)] for j in range(h)]) if sazonal else np.repeat(y[-1], h)


def ingenuo_sim(y, h, nsim, sazonal):
    y = np.asarray(y, float)
    base = ingenuo(y, h, sazonal)
    if sazonal:  # ruído das diferenças sazonais
        d = y[12:] - y[:-12]
        return base + RNG.choice(d - d.mean(), (nsim, h))
    d = np.diff(y)  # passeio aleatório
    return base + np.cumsum(RNG.choice(d - d.mean(), (nsim, h)), axis=1)


def mape(real, prev):
    return float(np.mean(np.abs((real - prev) / real)) * 100)


# ---------------------------------------------------------------- EXECUÇÃO
d = ler_sts()
linhas, metricas, sims_guardadas = [], [], {}
fim_real = None
for geo, nace, ind, adj in SERIES:
    s = serie(d, geo, nace, ind, adj)
    fim_real = s.index.max()
    saz = adj == "NSA"
    treino_total = limpar_covid(s, saz)

    # Backtest
    tr, te = treino_total[:FIM_TREINO_BT], s[s.index > FIM_TREINO_BT][:12]
    h_bt = len(te)
    prev_bt = {"ETS": ets_pontual(ets_fit(tr.values, 12 if saz else 1), h_bt),
               "AR": ar_sim(ar_fit(tr.values, tr.index), h_bt, 1, pontual=True),
               "Ingénuo": ingenuo(tr.values, h_bt, saz)}
    erros = {m: mape(te.values, p) for m, p in prev_bt.items()}
    melhor = min(erros, key=erros.get)
    for m, e in erros.items():
        metricas.append({"CO_GEO": geo, "NO_GEO": GEOS[geo], "CO_NACE": nace, "NO_CANAL": CANAIS[nace], "INDICADOR": ind, "AJUSTE": adj, "MODELO": m,
                         "MAPE_PCT": round(e, 2), "ESCOLHIDO": "Sim" if m == melhor else "Não"})

    # Previsão final (treino com toda a série)
    fut = pd.date_range(fim_real + pd.DateOffset(months=1), FIM_PREVISAO, freq="MS")
    h = len(fut)
    if melhor == "ETS":
        f = ets_fit(treino_total.values, 12 if saz else 1)
        pont, sims = ets_pontual(f, h), ets_sim(f, h, N_SIM)
    elif melhor == "AR":
        f = ar_fit(treino_total.values, treino_total.index)
        pont, sims = ar_sim(f, h, 1, pontual=True), ar_sim(f, h, N_SIM)
    else:
        pont, sims = ingenuo(treino_total.values, h, saz), ingenuo_sim(treino_total.values, h, N_SIM, saz)
    sims_guardadas[(geo, nace, ind, adj)] = (s, fut, sims)
    q = np.percentile(sims, [2.5, 10, 90, 97.5], axis=0)

    base = {"CO_GEO": geo, "NO_GEO": GEOS[geo], "CO_NACE": nace, "NO_CANAL": CANAIS[nace], "ORDEM_CANAL": ORDEM[nace], "INDICADOR": "Volume" if ind == "VOL_SLS" else "Valor",
            "AJUSTE": "Ajustado (SCA)" if adj == "SCA" else "Sem ajuste (NSA)", "MODELO": melhor}
    for t, v in s.items():
        linhas.append({**base, "DATA": t.date(), "TIPO": "Real", "VALOR": v})
    for j, t in enumerate(fut):
        linhas.append({**base, "DATA": t.date(), "TIPO": "Previsão", "VALOR": round(pont[j], 2),
                       "LIM95_INF": round(q[0, j], 2), "LIM80_INF": round(q[1, j], 2),
                       "LIM80_SUP": round(q[2, j], 2), "LIM95_SUP": round(q[3, j], 2)})
    print(f"{geo:9s} {nace:6s} {ind:7s} {adj}: melhor={melhor:8s} MAPE={erros[melhor]:.1f}% "
          f"(ETS {erros['ETS']:.1f} | AR {erros['AR']:.1f} | Ing {erros['Ingénuo']:.1f})")

prev = pd.DataFrame(linhas)
prev["DATA"] = pd.to_datetime(prev.DATA).dt.date
met = pd.DataFrame(metricas)

# ---------------------------------------------------------------- RESUMO ANUAL (séries ajustadas)
resumo = []
for (geo, nace, ind, adj), (s, fut, sims) in sims_guardadas.items():
    if adj != "SCA":
        continue
    real = s.groupby(s.index.year).mean()
    meses_fut = pd.Series(range(len(fut)), index=fut)
    medias = {}
    for ano in (2026, 2027):
        reais_ano = s[s.index.year == ano].values
        cols = meses_fut[meses_fut.index.year == ano].values
        medias[ano] = (reais_ano.sum() + sims[:, cols].sum(axis=1)) / (len(reais_ano) + len(cols))
    g26 = (medias[2026] / real[2025] - 1) * 100
    g27 = (medias[2027] / medias[2026] - 1) * 100
    resumo.append({"CO_GEO": geo, "NO_GEO": GEOS[geo], "CO_NACE": nace, "NO_CANAL": CANAIS[nace], "ORDEM_CANAL": ORDEM[nace],
                   "INDICADOR": "Volume" if ind == "VOL_SLS" else "Valor",
                   "CRESC_2025_PCT": round((real[2025] / real[2024] - 1) * 100, 1),
                   "CRESC_2026_PCT": round(np.median(g26), 1),
                   "CRESC_2026_P10": round(np.percentile(g26, 10), 1), "CRESC_2026_P90": round(np.percentile(g26, 90), 1),
                   "CRESC_2027_PCT": round(np.median(g27), 1),
                   "CRESC_2027_P10": round(np.percentile(g27, 10), 1), "CRESC_2027_P90": round(np.percentile(g27, 90), 1)})
res = pd.DataFrame(resumo)

# Q4 2026 vs Q4 2025 (série sem ajuste, Portugal) - para planeamento de compras/stock
q4 = []
for nace in CANAIS:
    s, fut, sims = sims_guardadas[("PT", nace, "VOL_SLS", "NSA")]
    real_q4 = s[(s.index >= "2025-10-01") & (s.index <= "2025-12-01")].sum()
    cols = [i for i, t in enumerate(fut) if t.year == 2026 and t.month >= 10]
    g = (sims[:, cols].sum(axis=1) / real_q4 - 1) * 100
    q4.append({"CO_NACE": nace, "NO_CANAL": CANAIS[nace], "Q4_2026_VS_Q4_2025_PCT": round(np.median(g), 1),
               "P10": round(np.percentile(g, 10), 1), "P90": round(np.percentile(g, 90), 1)})
q4 = pd.DataFrame(q4)

# ---------------------------------------------------------------- ADOÇÃO ONLINE (logística)
o = pd.read_csv(os.path.join(OUT, "fato_compras_online.csv"), sep=";", decimal=",")
o = o[o.CO_PERFIL.eq("IND_TOTAL") & o.CO_GEO.isin(["PT", "EU27_2020"])]


def logistica(t, L, k, t0):
    return L / (1 + np.exp(-k * (t - t0)))


proj = []
for geo in ["PT", "EU27_2020"]:
    x = o[o.CO_GEO == geo].sort_values("ANO")
    p, _ = curve_fit(logistica, x.ANO, x.PCT_COMPROU_12M, p0=[85, 0.2, 2018], bounds=([60, 0.01, 2000], [98, 1, 2040]))
    for _, r in x.iterrows():
        proj.append({"ANO": int(r.ANO), "CO_GEO": geo, "NO_GEO": GEOS[geo], "TIPO": "Real", "PCT_COMPROU_12M": r.PCT_COMPROU_12M,
                     "CURVA": round(logistica(r.ANO, *p), 2)})
    for ano in range(2026, 2031):
        proj.append({"ANO": ano, "CO_GEO": geo, "NO_GEO": GEOS[geo], "TIPO": "Cenário", "PCT_COMPROU_12M": None,
                     "CURVA": round(logistica(ano, *p), 2)})
    print(f"online {geo}: teto L={p[0]:.1f}%  velocidade k={p[1]:.3f}  ponto médio={p[2]:.1f}")
proj = pd.DataFrame(proj)
ue25 = o[(o.CO_GEO == "EU27_2020") & (o.ANO == 2025)].PCT_COMPROU_12M.iloc[0]
pt_curva = proj[(proj.CO_GEO == "PT")].set_index("ANO").CURVA
alcanca = next((a for a in range(2026, 2031) if pt_curva.get(a, 0) >= ue25), None)

# ---------------------------------------------------------------- GRÁFICOS
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

cores = {"G47": "#4A4A4A", "G4711": "#2F6DB5", "G472": "#D9822B", "G4791": "#0E7C66"}
fig, ax = plt.subplots(figsize=(12, 5.5))
for nace, cor in cores.items():
    x = prev[(prev.CO_GEO == "PT") & (prev.CO_NACE == nace) & (prev.INDICADOR == "Volume") & (prev.AJUSTE == "Ajustado (SCA)")]
    xr, xp = x[(x.TIPO == "Real") & (pd.to_datetime(x.DATA) >= "2019-01-01")], x[x.TIPO == "Previsão"]
    ax.plot(pd.to_datetime(xr.DATA), xr.VALOR, color=cor, lw=1.8, label=CANAIS[nace])
    ax.plot(pd.to_datetime(xp.DATA), xp.VALOR, color=cor, lw=1.8, ls="--")
    ax.fill_between(pd.to_datetime(xp.DATA), xp.LIM80_INF, xp.LIM80_SUP, color=cor, alpha=0.15, lw=0)
ax.axvline(fim_real, color="#999", lw=1)
ax.text(fim_real, ax.get_ylim()[1] * 0.98, "  previsão", color="#666", va="top")
ax.set_title("Portugal - volume de vendas do retalho por canal (2021 = 100): real e previsão até dez/2027",
             loc="left", fontsize=12)
ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
ax.grid(axis="y", color="#eee")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "grafico_previsao.png"), dpi=150)

fig, ax = plt.subplots(figsize=(10, 5))
for geo, cor, nome in [("PT", "#0E7C66", "Portugal"), ("EU27_2020", "#4A4A4A", "UE27")]:
    x = proj[proj.CO_GEO == geo]
    xr = x[x.TIPO == "Real"]
    ax.plot(xr.ANO, xr.PCT_COMPROU_12M, "o", color=cor, ms=4, label=f"{nome} (real)")
    ax.plot(x.ANO, x.CURVA, color=cor, lw=1.8, ls="-", alpha=0.8, label=f"{nome} (curva / cenário)")
ax.axvspan(2025.5, 2030.5, color="#f3f3f3", zorder=0)
ax.set_title("% de pessoas que compraram online nos últimos 12 meses: real e cenário até 2030", loc="left", fontsize=12)
ax.legend(frameon=False, fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "grafico_online.png"), dpi=150)

# ---------------------------------------------------------------- CARGA
for nome, df in {"fato_previsao": prev, "previsao_metricas": met, "previsao_resumo_anual": res,
                 "previsao_q4_2026": q4, "fato_projecao_online": proj}.items():
    df.to_csv(os.path.join(OUT, f"{nome}.csv"), sep=";", index=False, encoding="utf-8-sig", decimal=",")
    print(f"gravado {nome}.csv: {len(df):,} linhas")
print("\nResumo anual (mediana e intervalo de 80%):")
print(res.to_string(index=False))
print("\nQ4 2026 vs Q4 2025 (Portugal, volume sem ajuste):")
print(q4.to_string(index=False))
print(f"\nUE27 em 2025: {ue25:.1f}% | Portugal atinge esse nível em: {alcanca or 'depois de 2030'}")
print(proj[proj.TIPO == "Cenário"].pivot(index="ANO", columns="CO_GEO", values="CURVA"))
