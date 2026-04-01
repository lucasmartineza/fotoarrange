#!/bin/bash
echo ""
echo "Instalando FotoArrange..."
echo ""
if ! command -v python3 &> /dev/null; then
    echo "Python3 no encontrado. Instalalo desde https://python.org/downloads"
    exit 1
fi
mkdir -p ~/fotoarrange && cd ~/fotoarrange
curl -sL https://raw.githubusercontent.com/lucasmartineza/fotoarrange/main/app.py -o app.py
curl -sL https://raw.githubusercontent.com/lucasmartineza/fotoarrange/main/requirements.txt -o requirements.txt
mkdir -p static
curl -sL https://raw.githubusercontent.com/lucasmartineza/fotoarrange/main/static/index.html -o static/index.html
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --quiet
echo ""
echo "Listo! Para usar FotoArrange ejecuta:"
echo "cd ~/fotoarrange && source venv/bin/activate && python3 app.py"
echo ""
