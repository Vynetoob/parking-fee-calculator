# app.py
from flask import Flask, render_template, request
from datetime import datetime, timedelta
import json
import math # Para arredondamento de minutos/intervalos

app = Flask(__name__)

# --- Carrega as configurações dos pátios do arquivo JSON ---
PATIOS_DATA = {}
try:
    with open('patios_config.json', 'r', encoding='utf-8') as f:
        patios_list = json.load(f)
        for patio in patios_list:
            PATIOS_DATA[patio['name']] = patio # Armazena por nome para fácil acesso
except FileNotFoundError:
    print("ERRO: O arquivo 'patios_config.json' não foi encontrado.")
    # Um dicionário vazio ou default pode ser usado para evitar erros maiores
    PATIOS_DATA = {}
except json.JSONDecodeError:
    print("ERRO: O arquivo 'patios_config.json' está mal formatado.")
    PATIOS_DATA = {}

# --- Função para calcular o preço com base nas regras do pátio ---
def calculate_parking_fee(duration_minutes, pricing_rules):
    """
    Calcula o valor do estacionamento com base na duração e nas regras de precificação.
    """
    if duration_minutes < 0:
        return 0.0 # Duração negativa não deve ser cobrada

    calculated_price = 0.0

    # 1. Aplica o preço baseado nas faixas de tempo (tiers)
    found_tier_price = False
    for tier in pricing_rules['tiers']:
        if duration_minutes <= tier['duration_minutes']:
            calculated_price = tier['price']
            found_tier_price = True
            break
    
    # Se a duração excedeu todas as faixas (tiers), a base é o preço da última faixa
    if not found_tier_price and pricing_rules['tiers']:
        calculated_price = pricing_rules['tiers'][-1]['price']
        
        # 2. Aplica cobrança incremental, se existir e for aplicável
        if pricing_rules.get('incremental_after_minutes') is not None and \
           pricing_rules.get('incremental_price') is not None and \
           pricing_rules.get('incremental_interval_minutes') is not None:
            
            if duration_minutes > pricing_rules['incremental_after_minutes']:
                excess_minutes = duration_minutes - pricing_rules['incremental_after_minutes']
                
                # Arredonda para cima o número de intervalos para cobrança
                num_intervals = math.ceil(excess_minutes / pricing_rules['incremental_interval_minutes'])
                calculated_price += num_intervals * pricing_rules['incremental_price']
    
    # 3. Aplica o limite da diária (por bloco de 24 horas)
    daily_rate = pricing_rules['daily_rate']
    
    # Calcula o número de diárias para o teto (arredonda para cima se houver fração de dia)
    num_days_for_cap = math.ceil(duration_minutes / (24 * 60))
    
    # Se a duração for 0, mas o preço já foi calculado (ex: preço mínimo),
    # considere 1 dia para o limite da diária.
    if num_days_for_cap == 0 and calculated_price > 0:
        num_days_for_cap = 1

    capped_price_by_daily_rate = num_days_for_cap * daily_rate
    
    # O valor final é o menor entre o preço calculado (tiers + incrementais) e o teto da diária
    return min(calculated_price, capped_price_by_daily_rate)

# --- Rota da Página Inicial (Exibe o Formulário com seleção de pátio) ---
@app.route('/')
def index():
    """
    Renderiza a página principal com o formulário da calculadora e a lista de pátios.
    """
    # Passa os nomes dos pátios para o template para popular a caixa de seleção
    patio_names = sorted(list(PATIOS_DATA.keys())) # Lista ordenada dos nomes dos pátios
    return render_template('index.html', patios=patio_names)

# --- Rota para Processar o Cálculo ---
@app.route('/calcular', methods=['POST'])
def calcular():
    """
    Recebe os dados do formulário (pátio e hora de entrada), calcula o tempo de permanência
    e o valor com base na tabela de preços do pátio selecionado.
    Retorna a página com os resultados.
    """
    patio_selecionado_nome = request.form['patio'] # Pega o nome do pátio selecionado
    hora_entrada_str = request.form['hora_entrada'] # Pega o valor do input 'hora_entrada'

    # Busca as regras de precificação para o pátio selecionado
    pricing_rules = PATIOS_DATA.get(patio_selecionado_nome)

    resultado_tempo_formatado = ""
    resultado_valor_formatado = ""
    
    # Se o pátio não for encontrado ou as regras estiverem ausentes
    if not pricing_rules:
        resultado_tempo_formatado = "Erro: Pátio selecionado inválido ou sem regras."
        resultado_valor_formatado = "0,00"
    else:
        try:
            hora_entrada = datetime.strptime(hora_entrada_str, '%Y-%m-%dT%H:%M')
            hora_saida = datetime.now() # Hora atual do servidor
            tempo_total: timedelta = hora_saida - hora_entrada

            total_segundos = tempo_total.total_seconds()
            
            if total_segundos < 0:
                resultado_tempo_formatado = "Hora de entrada no futuro. Por favor, ajuste."
                resultado_valor_formatado = "0,00"
            else:
                total_minutos = total_segundos / 60
                
                # Chama a função de cálculo com a duração e as regras do pátio
                valor_final = calculate_parking_fee(total_minutos, pricing_rules)

                # Formata o tempo de permanência real (não o tempo para cobrança)
                dias = int(total_segundos // (24 * 3600))
                segundos_restantes = total_segundos % (24 * 3600)
                horas = int(segundos_restantes // 3600)
                minutos = int((segundos_restantes % 3600) // 60)
                
                resultado_tempo_formatado = ""
                if dias > 0:
                    resultado_tempo_formatado += f"{dias} dia(s), "
                resultado_tempo_formatado += f"{horas} hora(s) e {minutos} minuto(s)"

                # Formata o valor para exibição no padrão brasileiro
                resultado_valor_formatado = f"{valor_final:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
                
        except ValueError:
            resultado_tempo_formatado = "Erro no formato da data/hora. Verifique."
            resultado_valor_formatado = "0,00"
        except Exception as e:
            resultado_tempo_formatado = f"Ocorreu um erro: {e}"
            resultado_valor_formatado = "0,00"


    # Renderiza o template index.html, passando os resultados e a lista de pátios
    patio_names = sorted(list(PATIOS_DATA.keys()))
    return render_template('index.html', 
                           patios=patio_names,
                           resultado_tempo=resultado_tempo_formatado, 
                           resultado_valor=resultado_valor_formatado,
                           selected_patio=patio_selecionado_nome) # Para manter o pátio selecionado após o cálculo

# --- Inicia o Servidor Flask ---
if __name__ == '__main__':
    app.run(debug=True)
