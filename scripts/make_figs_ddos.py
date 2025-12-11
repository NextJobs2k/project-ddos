# scripts/make_figs_ddos.py
# Gera figuras de séries, ACF, PSD (Welch) e STFT a partir do CSV agregado (Δt=1s).
# Uso típico:
#   python scripts\make_figs_ddos.py --csv data\multivar_agg_1s.csv --col pps_udp
#   (troque --col para pps_http, bps_udp, etc.)

import argparse
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    from scipy import signal as sig
except Exception as e:
    raise RuntimeError(
        "Este script requer SciPy (scipy.signal). Instale com: pip install scipy"
    ) from e


# ----------------------------
# utilitários de PDS
# ----------------------------
def moving_zscore(x: np.ndarray, win: int = 21, eps: float = 1e-9) -> np.ndarray:
    """z-score móvel (média e desvio rolantes). win deve ser ímpar."""
    s = pd.Series(x.astype(float))
    minp = max(3, win // 3)
    mu = s.rolling(win, min_periods=minp, center=False).mean()
    sd = s.rolling(win, min_periods=minp, center=False).std(ddof=0)
    z = (s - mu) / (sd + eps)
    # fallback para o início da série
    head = min(win, len(s))
    if head > 1:
        z.iloc[:head] = (s.iloc[:head] - s.iloc[:head].mean()) / (
            s.iloc[:head].std(ddof=0) + eps
        )
    return z.fillna(0.0).to_numpy()

def plot_zscore(z, out_path):
   
    t = np.arange(len(z))  # 0,1,2,... (como Δt = 1s, isso já é o tempo em segundos)

    plt.figure(figsize=(12, 5))
    plt.plot(t, z, marker="o", linestyle="-")
    plt.axhline(0, linestyle=":", linewidth=1)
    plt.axhline(3, linestyle="--", linewidth=1)
    plt.axhline(-3, linestyle="--", linewidth=1)
    plt.xlabel("tempo (s)")
    plt.ylabel("z-score")
    plt.title("Série após detrend / z-score")
    plt.grid(True, linestyle=":", linewidth=0.5)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()



def welch_psd(x, fs=1.0, nperseg=128, noverlap=96, detrend="constant"):
    """PSD por Welch .
    Ajusta nperseg/noverlap automaticamente para respeitar:
      - nperseg <= len(x)
      - noverlap < nperseg
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        raise ValueError("Série muito curta para PSD (len(x) < 2).")

    # clamp nperseg ao tamanho da série
    nperseg = min(int(nperseg), n)

    # garantir noverlap < nperseg
    noverlap = int(noverlap)
    if noverlap >= nperseg:
        # usa algo como 75% de sobreposição, mas sempre < nperseg
        noverlap = max(0, nperseg - nperseg // 4)
        if noverlap >= nperseg:
            noverlap = nperseg - 1

    f, Pxx = sig.welch(
        x,
        fs=fs,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=detrend,
        scaling="density",
        average="mean",
    )
    return f, Pxx


def stft_power(x, fs=1.0, nperseg=32, noverlap=24, detrend="constant"):
    """STFT -> potência |Zxx|^2, ajustando nperseg/noverlap se preciso."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        raise ValueError("Série muito curta para STFT (len(x) < 2).")

    nperseg = min(int(nperseg), n)
    noverlap = int(noverlap)
    if noverlap >= nperseg:
        noverlap = max(0, nperseg - nperseg // 4)
        if noverlap >= nperseg:
            noverlap = nperseg - 1

    f, t, Zxx = sig.stft(
        x,
        fs=fs,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        detrend=detrend,
        boundary=None,
        padded=False,
    )
    Sxx = np.abs(Zxx) ** 2
    return f, t, Sxx




def acf_normalized(x: np.ndarray, max_lag: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Autocorrelação normalizada (lag 0..max_lag)."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    n = len(x)
    if max_lag is None or max_lag >= n:
        max_lag = n - 1
    # correlação completa
    corr = sig.correlate(x, x, mode="full")
    lags = np.arange(-n + 1, n)
    # pega apenas lags >= 0
    mask = lags >= 0
    corr = corr[mask]
    lags = lags[mask]
    # normalizar por valor em lag 0
    if corr[0] != 0:
        corr = corr / corr[0]
    # cortar em max_lag
    lags = lags[: max_lag + 1]
    corr = corr[: max_lag + 1]
    return lags, corr


# ----------------------------
# I/O e plots
# ----------------------------
def load_series(csv_path: str, col: str) -> np.ndarray:
    df = pd.read_csv(csv_path)
    if col not in df.columns:
        raise ValueError(
            f"Coluna '{col}' não encontrada em {csv_path}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )
    return df[col].to_numpy(dtype=float)


def plot_series(t, x, x_proc, out_path: str, use_z: bool):
    plt.figure(figsize=(12, 4))
    plt.plot(t, x, label="série original")
    if use_z:
        plt.plot(t, x_proc, linestyle="--", label="pós detrend/z-score")
    plt.xlabel("tempo (s)")
    plt.ylabel("amplitude")
    plt.title("Série temporal")
    plt.grid(True, linestyle=":")
    if use_z:
        plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def plot_acf(lags, corr, out_path: str):
    plt.figure(figsize=(12, 4))
    # compatível com versões antigas e novas do matplotlib
    try:
        plt.stem(lags, corr, use_line_collection=True)
    except TypeError:
        # versões antigas não aceitam use_line_collection
        plt.stem(lags, corr)
    plt.xlabel("lag (s)")
    plt.ylabel("ACF normalizada")
    plt.title("Autocorrelação (ACF)")
    plt.grid(True, linestyle=":")
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()



def plot_psd(f, Pxx, out_path: str):
    plt.figure(figsize=(12, 4))
    plt.semilogy(f, Pxx)
    plt.xlabel("frequência (Hz)")
    plt.ylabel("PSD")
    plt.title("Welch/PSD")
    plt.grid(True, which="both", linestyle=":")
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def plot_stft(f, t, Sxx, out_path: str):
    # normalização robusta da cor (evita saturar por outliers)
    vmin = np.percentile(Sxx, 5)
    vmax = np.percentile(Sxx, 95)
    if vmin == vmax:
        vmin = None
        vmax = None
    plt.figure(figsize=(12, 4))
    extent = [
        t[0] if len(t) else 0,
        t[-1] if len(t) else 0,
        f[0] if len(f) else 0,
        f[-1] if len(f) else 0,
    ]
    plt.imshow(
        Sxx,
        origin="lower",
        aspect="auto",
        extent=extent,
        vmin=vmin,
        vmax=vmax,
    )
    plt.colorbar(label="potência")
    plt.xlabel("tempo (s)")
    plt.ylabel("frequência (Hz)")
    plt.title("Espectrograma (STFT)")
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


def main():
    ap = argparse.ArgumentParser(
        description="Figuras de séries, ACF, PSD e STFT a partir do CSV agregado (Δt=1s)."
    )
    ap.add_argument(
        "--csv",
        default="data/multivar_agg_1s.csv",
        help="Caminho do CSV agregado.",
    )
    ap.add_argument(
        "--col",
        default="pps_udp",
        help="Coluna a analisar (ex.: pps_udp, pps_http, bps_udp, bps_http...).",
    )
    ap.add_argument("--outdir", default="figs", help="Pasta de saída das figuras.")

    # parâmetros PSD
    ap.add_argument("--fs", type=float, default=1.0, help="Frequência de amostragem (Hz).")
    ap.add_argument("--nperseg_psd", type=int, default=128)
    ap.add_argument("--noverlap_psd", type=int, default=96)

    # parâmetros STFT
    ap.add_argument("--nperseg_stft", type=int, default=32)
    ap.add_argument("--noverlap_stft", type=int, default=24)

    # pré-processamento
    ap.add_argument("--zwin", type=int, default=21, help="Janela do z-score móvel (ímpar).")
    ap.add_argument("--no_zscore", action="store_true", help="Desativa o z-score móvel.")

    # ACF
    ap.add_argument(
        "--max_lag",
        type=int,
        default=100,
        help="Lag máximo (em amostras) para a ACF (default: 100).",
    )
    ap.add_argument("--no_series", action="store_true", help="Não gera fig_series.png.")
    ap.add_argument("--no_acf", action="store_true", help="Não gera fig_acf.png.")

    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    safe_col = args.col.replace("/", "_").replace("\\", "_").replace(" ", "_")
            
    # carrega série
    x = load_series(args.csv, args.col)
    n = len(x)
    t = np.arange(n) / args.fs

    # detrend (remove offset lento) + z-score móvel
    x_dt = sig.detrend(x, type="constant")
    if args.no_zscore:
        x_proc = x_dt
    else:
        x_proc = moving_zscore(x_dt, win=args.zwin)
        plot_zscore(x_proc, os.path.join(args.outdir, "fig_zscore.png"))




    # Série temporal
    if not args.no_series:
        plot_series(
            t,
            x,
            x_proc,
            os.path.join(args.outdir, "fig_series.png"),
            use_z=not args.no_zscore,
        )

    # ACF
    if not args.no_acf:
        lags, corr = acf_normalized(x_proc, max_lag=args.max_lag)
        plot_acf(lags, corr, os.path.join(args.outdir, "fig_acf.png"))

    # PSD (Welch)
    f, Pxx = welch_psd(
        x_proc, fs=args.fs, nperseg=args.nperseg_psd, noverlap=args.noverlap_psd
    )
    plot_psd(f, Pxx, os.path.join(args.outdir, "fig_psd.png"))

    # STFT (potência)
    f2, t2, Sxx = stft_power(
        x_proc, fs=args.fs, nperseg=args.nperseg_stft, noverlap=args.noverlap_stft
    )
    plot_stft(f2, t2, Sxx, os.path.join(args.outdir, "fig_stft.png"))

    print("OK: figs/fig_series.png, figs/fig_acf.png, figs/fig_psd.png e figs/fig_stft.png gerados.")


if __name__ == "__main__":
    main()
