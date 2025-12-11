Detecção de DDoS com PDS em séries temporais (HTTP/UDP + MAWI)

Este projeto implementa um pipeline leve de Processamento Digital de Sinais (PDS) para analisar ataques DDoS a partir de cabeçalhos L3/L4, usando traços públicos em formato pcap.

O fluxo completo é:



1. Ativar venv e instalar libs: pip install -r environment.txt
Colocar *.pcap em data/raw/.

2. Rodar scripts/extract_csv.ps1 para cada pcap → data/csv/*.tsv.

3. Rodar aggregate.py → data/agg/*_agg_1s.csv + data/multivar_agg_1s.csv.

4. Rodar make_figs_ddos.py → figuras em plot/.

5. (Opcional) gerar/verificar hashes.sha256 para integridade dos CSVs.


  1. Estrutura de pastas

Depois de organizar os arquivos, a árvore do projeto fica assim:
project-ddos/
  README.md
  
  environment.txt            # lista de dependências Python
  
  data/
  
    raw/                     # pcaps originais
      https_ddos_120s.pcap   # ataque HTTPS (Bot-IoT)
      udp_ddos_120s.pcap     # ataque UDP (Bot-IoT)
      mawi_120s.pcap         # (opcional) trecho MAWI para análise isolada
    csv/
      http_packets.tsv       # metadados extraídos (HTTPS)
      udp_packets.tsv        # metadados extraídos (UDP)
      mawi_packets.tsv       # (opcional) metadados MAWI
    agg/
      http_agg_1s.csv        # agregação de 1 s (HTTPS)
      udp_agg_1s.csv         # agregação de 1 s (UDP)
      mawi_agg_1s.csv        # (opcional) agregação MAWI
    multivar_agg_1s.csv      # junção multivariada (HTTP+UDP)
    hashes.sha256            # hashes SHA-256 dos CSVs agregados
  scripts/
  
    extract_csv.ps1          # extração via tshark (Windows/PowerShell)
    aggregate.py             # CSV → séries agregadas
    make_figs_ddos.py        # z-score, PSD, ACF, STFT e figuras


  2. Requisitos

Sistema operacional :Testado em Windows 10/11 (PowerShell)

Scripts Python funcionam também em Linux/macOS (ajustando os caminhos/comandos)

Ferramentas
Wireshark/tshark
instalados e no PATH
Python 3.10+
pip (ou pip3)

Bibliotecas Python (instaladas via environment.txt)
numpy, pandas, scipy, matplotlib, pyyaml (e outras que estiverem listadas)

3. Instalação do ambiente Python
4. Coloque os PCAPs na pasta data/raw
5. Extração de cabeçalhos com extract_csv.ps1
   O script scripts/extract_csv.ps1 chama o tshark e exporta um TSV com: frame.time_epoch, ip.src, ip.dst, _ws.col.Protocol tcp.srcport, tcp.dstport, udp.srcport, udp.dstport tcp.flags.* (SYN, ACK, RST/RESET, FIN), frame.len
   5.1. Extrair HTTPS (HTTP/HTTPS DDoS)
   pwsh scripts/extract_csv.ps1 `
  -InputPcap "data/raw/https_ddos_120s.pcap" `
  -OutputTsv "data/csv/http_packets.tsv"

   5.2. Extrair UDP DDoS
  pwsh scripts/extract_csv.ps1 `
  -InputPcap "data/raw/udp_ddos_120s.pcap" `
  -OutputTsv "data/csv/udp_packets.tsv"
(para extrair o arquvio mawi e a mesma coisa, so muda o nome do arquivo)

   6. Agregação em janelas de 1 s (aggregate.py)
    # HTTPS + UDP → séries agregadas + multivariada/
   
   
   python scripts/aggregate.py \
  --http data/csv/http_packets.tsv \
  --udp  data/csv/udp_packets.tsv \
  --delta 1.0 \
  --outdir data/agg
7. Gerar figuras (z-score, PSD, ACF, STFT)

O script scripts/make_figs_ddos.py lê os CSVs agregados, aplica: detrend, z-score móvel, Welch/PSD, ACF, STFT / espectrograma, e salva as figuras em plot/.

  7.2. Exemplo  (HTTP + UDP)
python scripts/make_figs_ddos.py \
  --csv data/multivar_agg_1s.csv \
  --outdir plot \
  --fs 1.0

Ao final, você deve ter algo como:
plot/
  fig_series.png
  fig_zscore_http.png
  fig_zscore_udp.png
  fig_psd.png
  fig_acf.png
  fig_stft.png
Essas figuras são exatamente as usadas no relatório:

fig_zscore_http/udp – z-score (com limiar ±3) para ataques HTTPS/UDP e para MAWI;

fig_psd – Welch/PSD evidenciando energia extra em baixas frequências no ataque;

fig_acf – autocorrelação, mostrando platôs/repetição (modo ON/OFF coordenado);

fig_stft – espectrograma com blocos de energia quando o ataque está ON.

8. Gerar/verificar hashes.sha256 (opcional, mas recomendado)

8.1. Windows (PowerShell)

cd data
Get-FileHash agg\http_agg_1s.csv, agg\udp_agg_1s.csv, multivar_agg_1s.csv -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash)  $($_.Path | Split-Path -Leaf)" } |
  Out-File hashes.sha256 -Encoding ASCII
cd ..


