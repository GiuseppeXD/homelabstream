#!/usr/bin/env bash
# monitor-legendas.sh
# Monitora em tempo real a geração de legendas via Whisper + Ollama
# Uso: ./monitor-legendas.sh

set -euo pipefail

MEDIA_DIR="${MEDIA_DIR:-/home/gluca/homelabs/media}"
REFRESH_SEC="${REFRESH_SEC:-10}"

clear_screen() {
    printf '\033[2J\033[H'
}

header() {
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║        MONITOR DE LEGENDAS - Whisper + Ollama                      ║"
    echo "║        Atualiza a cada ${REFRESH_SEC}s (Ctrl+C para sair)              ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
}

container_status() {
    local name="$1"
    local status
    status=$(docker ps --filter "name=$name" --format "{{.Status}}" 2>/dev/null || true)
    if [[ -n "$status" ]]; then
        echo "✅ $name: $status"
    else
        echo "❌ $name: PARADO"
    fi
}

container_cpu_mem() {
    local name="$1"
    local stats
    stats=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" "$name" 2>/dev/null | tail -1 || true)
    if [[ -n "$stats" && "$stats" != "0.00%"* ]]; then
        echo "   CPU/Mem: $stats"
    else
        echo "   CPU/Mem: --"
    fi
}

whisper_progress() {
    echo "🎙️  WHISPER-ASR"
    container_status "whisper-asr"
    
    # Whisper roda como processo único; detectamos processamento pela CPU
    local cpu_val
    cpu_val=$(docker stats --no-stream --format "{{.CPUPerc}}" whisper-asr 2>/dev/null | tr -d '%' || echo "0")
    cpu_val="${cpu_val%.*}"  # remove decimal
    
    if [[ "$cpu_val" -gt 100 ]]; then
        echo "   🔄 Status: Processando áudio... (CPU ${cpu_val}%)"
    else
        echo "   ⏳ Status: Ocioso (CPU ${cpu_val}%)"
    fi
    echo ""
}

ollama_progress() {
    echo "🧠 OLLAMA"
    container_status "ollama"
    container_cpu_mem "ollama"
    
    # Verifica se há llama runner ativo
    local runner
    runner=$(docker exec ollama ps aux 2>/dev/null | grep -c "llama" || echo "0")
    if [[ "$runner" -gt 0 ]]; then
        echo "   🔄 Status: Traduzindo (llama runner ativo)"
    else
        echo "   ⏳ Status: Ocioso"
    fi
    
    # Verifica modelos disponíveis
    local models
    models=$(docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ' || echo "N/A")
    if [[ "$models" != "N/A" && -n "$models" ]]; then
        echo "   📦 Modelos: ${models%, }"
    fi
    echo ""
}

recent_srt_files() {
    echo "📁 ARQUIVOS DE LEGENDA RECENTES (últimas 2h)"
    echo "──────────────────────────────────────────────────────────────────────"
    
    local files
    files=$(find "$MEDIA_DIR" -name "*.srt" -mmin -120 2>/dev/null | sort -k6,7 || true)
    
    if [[ -z "$files" ]]; then
        echo "   (nenhum arquivo .srt gerado recentemente)"
    else
        echo "$files" | while read -r f; do
            local size type elapsed
            size=$(du -h "$f" 2>/dev/null | cut -f1 || echo "?")
            
            if [[ "$f" == *".pt-BR.srt" ]]; then
                type="🇧🇷 PT-BR"
            elif [[ "$f" == *".en.srt" ]]; then
                type="🇺🇸 EN"
            else
                type="🌐 Outro"
            fi
            
            local mtime
            mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
            local elapsed=$(( $(date +%s) - mtime ))
            local mins=$((elapsed / 60))
            
            printf "   %-12s | %6s | %3dm atrás | %s\n" "$type" "$size" "$mins" "$(basename "$f")"
        done
    fi
    echo ""
}

bazarr_queue() {
    echo "📊 BAZARR"
    container_status "bazarr"
    container_cpu_mem "bazarr"
    
    # Tenta ver se há buscas pendentes (via logs recentes)
    local recent
    recent=$(docker logs --since 2m bazarr 2>/dev/null | grep -iE "searching subtitles|downloaded.*subtitle|no subtitles found" | tail -3 || true)
    if [[ -n "$recent" ]]; then
        echo "   📝 Atividade recente:"
        echo "$recent" | sed 's/^.*://' | sed 's/^/      /'
    else
        echo "   📝 Atividade recente: (sem atividade nos últimos 2 min)"
    fi
    echo ""
}

footer() {
    echo "──────────────────────────────────────────────────────────────────────"
    echo "💡 Dicas:"
    echo "   • CPU alta no Whisper (>400%) = transcrição em andamento"
    echo "   • CPU alta no Ollama (>200%)  = tradução em andamento"
    echo "   • .en.srt aparece primeiro (Whisper), depois .pt-BR.srt (Ollama)"
    echo "   • Legendas antigas (>2h) não aparecem aqui"
    echo ""
}

main() {
    # Verifica dependências
    if ! command -v docker &>/dev/null; then
        echo "❌ Docker não encontrado"
        exit 1
    fi
    
    while true; do
        clear_screen
        header
        whisper_progress
        ollama_progress
        bazarr_queue
        recent_srt_files
        footer
        
        sleep "$REFRESH_SEC"
    done
}

trap 'echo ""; echo "👋 Monitor encerrado."; exit 0' INT

main "$@"
