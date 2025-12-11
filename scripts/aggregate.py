import argparse
import os
import pandas as pd
import numpy as np


def guess_sep(path: str) -> str:
    """Chuta o separador a partir da extensão."""
    return "\t" if path.lower().endswith(".tsv") else ","


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return 0


def shannon_entropy(series: pd.Series) -> float:
    vc = series.value_counts(normalize=True, dropna=True)
    return float((-vc * np.log2(vc)).sum()) if len(vc) else 0.0


def load_packets(path: str, sep: str | None = None) -> pd.DataFrame:
    """Carrega CSV/TSV de pacotes e normaliza colunas usadas na agregação."""

    # permite override do separador
    if sep is None:
        sep = guess_sep(path)

    try:
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-16")

    df.columns = [c.strip() for c in df.columns]

    # Campos mínimos obrigatórios
    need = ["frame.time_epoch", "ip.src", "ip.dst", "frame.len"]
    for c in need:
        if c not in df.columns:
            raise RuntimeError(f"Coluna ausente em {path}: {c}")

    # Flags TCP — aceitar diferentes nomes
    syn = "tcp.flags.syn" if "tcp.flags.syn" in df.columns else None
    ack = "tcp.flags.ack" if "tcp.flags.ack" in df.columns else None
    rst = (
        "tcp.flags.reset"
        if "tcp.flags.reset" in df.columns
        else ("tcp.flags.rst" if "tcp.flags.rst" in df.columns else None)
    )
    fin = "tcp.flags.fin" if "tcp.flags.fin" in df.columns else None

    for col in [syn, ack, rst, fin]:
        if col and col in df.columns:
            df[col] = df[col].fillna(0).map(safe_int)

    # Criar colunas de flags ausentes como 0 (para facilitar agregação)
    for cname in [
        "tcp.flags.syn",
        "tcp.flags.ack",
        "tcp.flags.reset",
        "tcp.flags.rst",
        "tcp.flags.fin",
    ]:
        if cname not in df.columns:
            df[cname] = 0

    # Portas: garantir colunas existem
    for pcol in ["tcp.srcport", "tcp.dstport", "udp.srcport", "udp.dstport"]:
        if pcol not in df.columns:
            df[pcol] = np.nan

    # Tipos numéricos
    df["frame.time_epoch"] = pd.to_numeric(df["frame.time_epoch"], errors="coerce")
    df["frame.len"] = pd.to_numeric(df["frame.len"], errors="coerce")

    # descartar linhas sem tempo ou tamanho
    df = df.dropna(subset=["frame.time_epoch", "frame.len"]).reset_index(drop=True)
    if df.empty:
        raise RuntimeError(f"DataFrame vazio após limpeza em {path}")

    # Descobrir melhor coluna de protocolo disponível
    proto_col = None
    for c in ["_ws.col.Protocol", "frame.protocols", "ip.proto"]:
        if c in df.columns:
            proto_col = c
            break

    def infer_proto(row):
        # 1) Se temos ip.proto (numérico)
        if proto_col == "ip.proto":
            try:
                v = int(row[proto_col])
            except Exception:
                v = None
            if v == 6:
                return "TCP"
            if v == 17:
                return "UDP"
            if v == 1:
                return "ICMP"

        # 2) Se temos string de protocolos (_ws.col.Protocol ou frame.protocols)
        if proto_col in ["_ws.col.Protocol", "frame.protocols"] and isinstance(
            row.get(proto_col, None), str
        ):
            up = row[proto_col].upper()
            if "UDP" in up:
                return "UDP"
            if "TCP" in up:
                return "TCP"
            if "ICMP" in up:
                return "ICMP"

        # 3) Inferir pelas colunas de porta
        if pd.notna(row.get("tcp.srcport")) or pd.notna(row.get("tcp.dstport")):
            return "TCP"
        if pd.notna(row.get("udp.srcport")) or pd.notna(row.get("udp.dstport")):
            return "UDP"
        return "OTHER"

    df["proto"] = df.apply(infer_proto, axis=1)
    return df


def aggregate_1s(df: pd.DataFrame, label: str, delta: float = 1.0) -> pd.DataFrame:
    """Agrega em janelas de tamanho delta (s) e gera features L3/L4 básicas."""

    if df.empty:
        return pd.DataFrame(columns=["t_start", f"pps_{label}", f"bps_{label}"])

    t0 = np.floor(df["frame.time_epoch"].min())
    df = df.copy()
    df["t_start"] = np.floor((df["frame.time_epoch"] - t0) / delta) * delta

    grp = df.groupby("t_start", observed=True)

    out = pd.DataFrame(
        {
            "t_start": grp.size().index.values,
            f"pps_{label}": grp.size().values,
            f"bps_{label}": grp["frame.len"].sum().values * 8.0,
        }
    )

    # Somar flags TCP se existirem
    flag_map = {
        "tcp.flags.syn": "syn",
        "tcp.flags.ack": "ack",
        "tcp.flags.reset": "reset",
        "tcp.flags.rst": "rst",
        "tcp.flags.fin": "fin",
    }
    for col, short in flag_map.items():
        if col in df.columns:
            out[f"{short}_{label}"] = grp[col].sum().values

    # Diversidade e entropias
    out[f"n_ip_src_{label}"] = grp["ip.src"].nunique().values
    out[f"n_ip_dst_{label}"] = grp["ip.dst"].nunique().values
    out[f"H_ip_src_{label}"] = grp["ip.src"].apply(shannon_entropy).values
    out[f"H_ip_dst_{label}"] = grp["ip.dst"].apply(shannon_entropy).values

    # Razões úteis (SYN%)
    if f"pps_{label}" in out and f"syn_{label}" in out:
        syn = out[f"syn_{label}"].astype(float)
        ack = out.get(f"ack_{label}", pd.Series(0, index=out.index)).astype(float)
        out[f"syn_percent_{label}"] = syn / (out[f"pps_{label}"] + 1e-9)
        out[f"syn_ack_ratio_{label}"] = syn / (ack + 1e-9)

    return out.sort_values("t_start").reset_index(drop=True)


def outer_join_on_time(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """Outer-join em t_start para construir série multivariada."""
    from functools import reduce

    multivar = reduce(lambda l, r: pd.merge(l, r, on="t_start", how="outer"), dfs)
    return multivar.sort_values("t_start").reset_index(drop=True).fillna(0)


def parse_sep_arg(sep_arg: str) -> str | None:
    """Converte argumento --sep em separador real."""
    if sep_arg == "auto":
        return None
    if sep_arg == "tab":
        return "\t"
    if sep_arg == "comma":
        return ","
    # fallback (não deve acontecer por causa do choices)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", required=False, help="data/csv/http_packets.csv|tsv")
    ap.add_argument("--udp", required=False, help="data/csv/udp_packets.csv|tsv")
    ap.add_argument("--delta", type=float, default=1.0, help="janela (s)")
    ap.add_argument(
        "--outdir", default="data/agg", help="diretório de saída dos CSVs agregados"
    )
    ap.add_argument(
        "--sep",
        choices=["auto", "tab", "comma"],
        default="auto",
        help="separador global (auto=pelas extensões, tab='\\t', comma=',')",
    )
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    parts: list[pd.DataFrame] = []

    sep = parse_sep_arg(args.sep)

    if args.http and os.path.isfile(args.http):
        df_http = load_packets(args.http, sep=sep)
        agg_http = aggregate_1s(df_http, "http", args.delta)
        agg_http.to_csv(os.path.join(args.outdir, "http_agg_1s.csv"), index=False)
        parts.append(agg_http)

    if args.udp and os.path.isfile(args.udp):
        df_udp = load_packets(args.udp, sep=sep)
        agg_udp = aggregate_1s(df_udp, "udp", args.delta)
        agg_udp.to_csv(os.path.join(args.outdir, "udp_agg_1s.csv"), index=False)
        parts.append(agg_udp)

    if not parts:
        raise SystemExit("Nenhuma fonte fornecida (--http/--udp).")

    multivar = outer_join_on_time(parts)
    os.makedirs("data", exist_ok=True)
    multivar.to_csv(os.path.join("data", "multivar_agg_1s.csv"), index=False)
    print("OK: data/multivar_agg_1s.csv, data/agg/* gerados.")


if __name__ == "__main__":
    main()
