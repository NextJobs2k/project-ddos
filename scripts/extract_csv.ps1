param(
    # raiz do projeto; por padrão é uma pasta acima de scripts/
    [string]$Root = (Split-Path $PSScriptRoot -Parent)
)

# Caminhos básicos
$rawDir = Join-Path $Root "data\raw"
$csvDir = Join-Path $Root "data\csv"

# Garante que data/csv existe
New-Item -ItemType Directory -Path $csvDir -Force | Out-Null

# Caminho do tshark (se não estiver no PATH, coloca o caminho completo aqui)
$tshark = "tshark"  # exemplo: "C:\Program Files\Wireshark\tshark.exe"

function Extract-Http {
    param(
        [string]$PcapIn,
        [string]$TsvOut
    )

    & $tshark -n -r $PcapIn `
      -Y "tcp.port==80 or tcp.port==8080" `
      -T fields -E header=y -E separator=`t -E quote=d `
      -e frame.time_epoch -e ip.src -e ip.dst -e _ws.col.Protocol `
      -e tcp.srcport -e tcp.dstport -e udp.srcport -e udp.dstport `
      -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset -e tcp.flags.fin `
      -e frame.len |
      Out-File -FilePath $TsvOut -Encoding utf8

    Write-Host "HTTP -> $TsvOut"
}

function Extract-Udp {
    param(
        [string]$PcapIn,
        [string]$TsvOut
    )

    & $tshark -n -r $PcapIn `
      -Y "udp" `
      -T fields -E header=y -E separator=`t -E quote=d `
      -e frame.time_epoch -e ip.src -e ip.dst -e _ws.col.Protocol `
      -e tcp.srcport -e tcp.dstport -e udp.srcport -e udp.dstport `
      -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset -e tcp.flags.fin `
      -e frame.len |
      Out-File -FilePath $TsvOut -Encoding utf8

    Write-Host "UDP -> $TsvOut"
}

function Extract-Mawi {
    param(
        [string]$PcapIn,
        [string]$TsvOut
    )

    & $tshark -n -r $PcapIn `
      -T fields -E header=y -E separator=`t -E quote=d `
      -e frame.time_epoch -e ip.src -e ip.dst -e _ws.col.Protocol `
      -e tcp.srcport -e tcp.dstport -e udp.srcport -e udp.dstport `
      -e tcp.flags.syn -e tcp.flags.ack -e tcp.flags.reset -e tcp.flags.fin `
      -e frame.len |
      Out-File -FilePath $TsvOut -Encoding utf8

    Write-Host "MAWI -> $TsvOut"
}

# ==== chama as funções com os arquivos do seu projeto ====

$httpPcap = Join-Path $rawDir "https_ddos_120s.pcap"
$udpPcap  = Join-Path $rawDir "udp_ddos_120s.pcap"
$mawiPcap = Join-Path $rawDir "mawi_120s_0000.pcap"   # ajuste o nome se precisar

$httpTsv = Join-Path $csvDir "http_packets.tsv"
$udpTsv  = Join-Path $csvDir "udp_packets.tsv"
$mawiTsv = Join-Path $csvDir "mawi_packets.tsv"

if (Test-Path $httpPcap) { Extract-Http -PcapIn $httpPcap -TsvOut $httpTsv }
if (Test-Path $udpPcap)  { Extract-Udp  -PcapIn $udpPcap  -TsvOut $udpTsv  }
if (Test-Path $mawiPcap) { Extract-Mawi -PcapIn $mawiPcap -TsvOut $mawiTsv }
