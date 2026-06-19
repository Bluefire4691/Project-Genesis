#!/usr/bin/env bash
set -e

echo ""
echo " Project Genesis — Install"
echo " ========================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo " ERROR: Python 3 not found."
    echo " Install Python 3.11+ from https://python.org then re-run."
    exit 1
fi

echo " [1/4] Installing Python packages..."
pip3 install -r requirements.txt

echo ""
echo " [2/4] Installing Playwright browser (Chromium ~120 MB)..."
python3 -m playwright install chromium || echo " WARNING: Playwright install failed — will use requests fallback."

echo ""
echo " [3/4] Downloading WordNet dictionary (~10 MB)..."
python3 -c "import nltk; nltk.download('wordnet', quiet=True); nltk.download('omw-1.4', quiet=True); print('  WordNet ready.')"

echo ""
echo " [4/4] Done."
echo ""
echo " To run Genesis:"
echo ""
echo "   cd src"
echo "   python3 ui.py                          # first run (builds foundation, ~1 min)"
echo "   python3 ui.py --resume --self-directed"
echo ""
echo " Once it's running, type to talk. Live resource controls:"
echo "   speed N (1-10)   memory N   fetch N   explore"
echo ""
echo " Optional — LLM voice:"
echo "   curl -fsSL https://ollama.ai/install.sh | sh"
echo "   ollama pull llama3.2:3b"
echo ""
