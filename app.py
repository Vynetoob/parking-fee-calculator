# app.py
from datetime import datetime
import math
import json
from flask import Flask, request, render_template

app = Flask(__name__)

# 1. Carregar arquivo JSON com as regras dos pátios
try:
    with open('patios_config.json', 'r', encoding='utf-8') as f:
        PATIOS_CONFIG = json.load(f)
except FileNotFoundError:
    PATIOS_CONFIG = {}
    print("Erro: patios_config.json não encontrado. Verifique o caminho do arquivo.")
except json.JSONDecodeError:
    PATIOS_CONFIG = {}
    print("Erro: patios_config.json inválido. Verifique a sintaxe JSON.")


# 2. Função para calcular o valor
def calcular_valor_estacionamento(patio_config, entrada_str, saida_str):
    """
    Calcula o valor do estacionamento com base nas regras do pátio.
    Entrada/saída devem estar no formato 'AAAA-MM-DDTHH:MM' (datetime-local).
    """
    try:
        entrada = datetime.strptime(entrada_str, "%Y-%m-%dT%H:%M")
        saida = datetime.strptime(saida_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        return {"erro": "Formato inválido. Use AAAA-MM-DDTHH:MM."}

    if saida < entrada:
        return {"erro": "Saída não pode ser antes da entrada."}

    total_minutos = (saida - entrada).total_seconds() / 60
    regras_minutos = patio_config.get("regras_minutos", [])
    inc = patio_config.get("incremental_pricing")
    diaria = patio_config.get("diaria")

    # --- Step 1: verificar regras por faixas ---
    valor_inicial = 0.0
    for regra in regras_minutos:
        if total_minutos <= regra["limite"]:
            valor_inicial = regra["valor"]
            break
    else:
        if regras_minutos:
            valor_inicial = regras_minutos[-1]["valor"]

    preco_atual = valor_inicial

    # --- Step 2: incremental pricing ---
    if inc and total_minutos > inc["applies_after_minutes"]:
        excesso = total_minutos - inc["applies_after_minutes"]
        blocos = math.ceil(excesso / inc["interval_minutes"])
        preco_atual = valor_inicial + blocos * inc["price_per_interval"]

    # --- Step 3: diária ---
    if diaria and diaria.get("valor") is not None:
        diaria_valor = diaria["valor"]
        ativa_apos = diaria.get("ativa_apos_minutos")
        cap_interval = diaria.get("capping_interval_minutes", 1440)

        if ativa_apos is not None and total_minutos > ativa_apos:
            # diária substitui cálculo
            dias = math.ceil(total_minutos / cap_interval)
            preco_atual = dias * diaria_valor
        elif ativa_apos is None:
            # diária como teto (cap)
            dias = math.ceil(total_minutos / cap_interval)
            teto = dias * diaria_valor
            preco_atual = min(preco_atual, teto)

    return {"valor": round(preco_atual, 2), "total_minutos": total_minutos}


# 3. Rotas
@app.route('/')
def index():
    patios = sorted(list(PATIOS_CONFIG.keys()))
    return render_template('index.html', patios=patios)


@app.route('/calcular', methods=['POST'])
def calcular():
    patio_nome = request.form['patio']
    entrada_str = request.form['hora_entrada']
    saida_str = request.form['hora_saida']

    patio_config = PATIOS_CONFIG.get(patio_nome)
    if not patio_config:
        return render_template(
            'index.html',
            patios=sorted(PATIOS_CONFIG.keys()),
            resultado_tempo="Erro: pátio inválido.",
            resultado_valor="0,00",
            selected_patio=patio_nome
        )

    resultado = calcular_valor_estacionamento(patio_config, entrada_str, saida_str)

    if "erro" in resultado:
        return render_template(
            'index.html',
            patios=sorted(PATIOS_CONFIG.keys()),
            resultado_tempo=resultado["erro"],
            resultado_valor="0,00",
            selected_patio=patio_nome
        )

    # formatar duração
    total_minutos = resultado["total_minutos"]
    total_segundos = total_minutos * 60
    dias = int(total_segundos // (24 * 3600))
    resto = total_segundos % (24 * 3600)
    horas = int(resto // 3600)
    minutos = int((resto % 3600) // 60)

    tempo_fmt = ""
    if dias > 0:
        tempo_fmt += f"{dias} dia(s), "
    tempo_fmt += f"{horas} hora(s) e {minutos} minuto(s)"

    # formatar valor
    valor_fmt = f"{resultado['valor']:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')

    return render_template(
        'index.html',
        patios=sorted(PATIOS_CONFIG.keys()),
        resultado_tempo=tempo_fmt,
        resultado_valor=valor_fmt,
        selected_patio=patio_nome
    )


if __name__ == '__main__':
    app.run(debug=True)
