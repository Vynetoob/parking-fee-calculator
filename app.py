# app.py

# 1. IMPORTAÇÕES: (Já estão corretas, não precisa mudar)
from datetime import datetime, timedelta
import math
import json
from flask import Flask, request, render_template
import pytz

app = Flask(__name__)

# 2. CARREGAMENTO DO PATIOS_CONFIG.JSON:
# REMOVA o bloco 'PATIOS_DATA = {}' que você tinha.
# MANTENHA SOMENTE ESTE BLOCO ABAIXO, logo depois de 'app = Flask(__name__)'
try:
    with open('patios_config.json', 'r', encoding='utf-8') as f:
        PATIOS_CONFIG = json.load(f)
except FileNotFoundError:
    PATIOS_CONFIG = {}
    print("Erro: patios_config.json não encontrado. Verifique o caminho do arquivo.")
except json.JSONDecodeError:
    PATIOS_CONFIG = {}
    print("Erro: patios_config.json inválido. Verifique a sintaxe JSON.")


# 3. FUNÇÃO DE CÁLCULO:
# REMOVA COMPLETAMENTE a função 'calculate_parking_fee(...)' que você tinha.
# SUBSTITUA-A POR ESTA NOVA FUNÇÃO ABAIXO:
# --- NOVA FUNÇÃO DE CÁLCULO (SUBSTITUIR a anterior) ---
def calcular_valor_estacionamento(patio_config, entrada_str, saida_str):
    """
    Calcula o valor do estacionamento com base nas regras do pátio fornecido.
    Espera strings de data/hora no formato 'AAAA-MM-DDTHH:MM'.
    """
    try:
        entrada = datetime.strptime(entrada_str, "%Y-%m-%dT%H:%M")
        saida = datetime.strptime(saida_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        return {"erro": "Formato de data/hora inválido. Use AAAA-MM-DDTHH:MM (do campo datetime-local)."}

    if saida < entrada:
        return {"erro": "A hora de saída não pode ser anterior à hora de entrada."}

    duracao = saida - entrada
    total_minutos = duracao.total_seconds() / 60

    regras_minutos = patio_config.get("regras_minutos", [])
    incremental_pricing_config = patio_config.get("incremental_pricing")
    diaria_config = patio_config.get("diaria")

    # Step 1: Calcular preço base usando regras por faixas (tiers)
    valor_calculado_inicial = 0.0
    found_tier = False
    for regra in regras_minutos:
        if total_minutos <= regra["limite"]:
            valor_calculado_inicial = regra["valor"]
            found_tier = True
            break
    
    # Se a duração excedeu todas as faixas (tiers), o preço inicial é o da última faixa
    if not found_tier and regras_minutos:
        valor_calculado_inicial = regras_minutos[-1]["valor"]
        
    current_calculated_price = valor_calculado_inicial

    # Step 2: Aplicar cobrança incremental, se aplicável
    if incremental_pricing_config and total_minutos > incremental_pricing_config["applies_after_minutes"]:
        
        # O cálculo incremental é feito sobre o tempo que excede o limite incremental.
        # O valor inicial já contém o valor da última faixa.
        excess_minutes = total_minutos - incremental_pricing_config["applies_after_minutes"]
        
        # Calcular o número de intervalos incrementais (arredonda para cima)
        num_intervals = math.ceil(excess_minutes / incremental_pricing_config["interval_minutes"])
        
        incremental_cost = num_intervals * incremental_pricing_config["price_per_interval"]
        
        current_calculated_price = valor_calculado_inicial + incremental_cost


    # Step 3: Aplicar a regra da diária (como substituição ou como limite/cap)
    final_price_after_rules = current_calculated_price # Este é o preço calculado até agora (faixas + incremental)

    if diaria_config and diaria_config.get("valor") is not None:
        daily_rate_value = diaria_config["valor"]
        daily_activation_minutes = diaria_config.get("ativa_apos_minutos")
        daily_capping_interval_minutes = diaria_config.get("capping_interval_minutes", 1440) # Padrão 24 horas

        # Opção A: Diária como SUBSTITUIÇÃO (se 'ativa_apos_minutos' for definido e excedido)
        if daily_activation_minutes is not None and total_minutos > daily_activation_minutes:
            # Calcula o número de "dias" com base no intervalo de capping (normalmente 24h)
            num_days_override = math.ceil(total_minutos / daily_capping_interval_minutes)
            if num_days_override == 0 and total_minutos > 0: # Para garantir 1 diária mínima se ativado e não 0
                num_days_override = 1
            final_price_after_rules = num_days_override * daily_rate_value
        
        # Opção B: Diária como LIMITE (CAP) sobre o valor total (se 'ativa_apos_minutos' for nulo)
        elif daily_activation_minutes is None:
            # Calcula o número de "dias" para o cap, arredondando para cima
            num_days_for_cap = math.ceil(total_minutos / daily_capping_interval_minutes)
            if num_days_for_cap == 0 and total_minutos > 0: # Para garantir 1 diária mínima se há algum custo
                num_days_for_cap = 1 
            max_price_based_on_daily_cap = num_days_for_cap * daily_rate_value
            final_price_after_rules = min(final_price_after_rules, max_price_based_on_daily_cap)

    # Retorna o valor final arredondado e os minutos totais para formatação na rota
    return {"valor": round(final_price_after_rules, 2), "total_minutos": total_minutos}


# 4. ROTAS FLASK:
# MANTENHA as linhas '@app.route(...)', mas MODIFIQUE o código DENTRO delas.

# Rota da Página Inicial
@app.route('/')
def index():
    """
    Renderiza a página principal com o formulário da calculadora e a lista de pátios.
    """
    # AGORA USA PATIOS_CONFIG.keys()
    patio_names = sorted(list(PATIOS_CONFIG.keys())) # Lista ordenada dos nomes dos pátios
    return render_template('index.html', patios=patio_names)

# Rota para Processar o Cálculo
@app.route('/calcular', methods=['POST'])
def calcular():
    """
    Recebe os dados do formulário (pátio e hora de entrada), calcula o tempo de permanência
    e o valor com base na tabela de preços do pátio selecionado.
    Retorna a página com os resultados.
    """
    patio_selecionado_nome = request.form['patio']
    hora_entrada_str = request.form['hora_entrada']
    
    # A hora de saída será sempre o momento atual
    fuso_horario_brasilia = pytz.timezone('America/Sao_Paulo')

    # Obter a hora de saída no fuso horário de Brasília
    hora_saida_brasilia = datetime.now(fuso_horario_brasilia)
    hora_saida_str = hora_saida_brasilia.strftime("%Y-%m-%dT%H:%M") # <--- NOVA LINHA
    
    
    # Busca as regras de precificação para o pátio selecionado do PATIOS_CONFIG
    patio_config = PATIOS_CONFIG.get(patio_selecionado_nome)

    resultado_tempo_formatado = ""
    resultado_valor_formatado = ""
    
    # Se o pátio não for encontrado na nova estrutura do JSON
    if not patio_config:
        resultado_tempo_formatado = "Erro: Pátio selecionado inválido ou sem regras na configuração."
        resultado_valor_formatado = "0,00"
    else:
        try:
            # Chama a nova função de cálculo
            resultado_calculo = calcular_valor_estacionamento(patio_config, hora_entrada_str, hora_saida_str)

            if "erro" in resultado_calculo:
                resultado_tempo_formatado = resultado_calculo["erro"]
                resultado_valor_formatado = "0,00"
            else:
                valor_final = resultado_calculo["valor"]
                # Agora o total_minutos vem do resultado_calculo para ser usado no cálculo do tempo de exibição
                total_minutos_para_exibir = resultado_calculo["total_minutos"] 

                # Calcula o tempo de permanência formatado (lógica que você já tinha)
                total_segundos = total_minutos_para_exibir * 60 # Convertendo de volta para segundos para o cálculo de dias/horas/minutos
                
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
                
        except Exception as e:
            # Captura qualquer outro erro inesperado no processo de cálculo ou formatação
            resultado_tempo_formatado = f"Ocorreu um erro inesperado durante o cálculo: {e}"
            resultado_valor_formatado = "0,00"


    # Renderiza o template index.html, passando os resultados e a lista de pátios
    patio_names = sorted(list(PATIOS_CONFIG.keys())) # Garante que a lista de pátios seja atualizada
    return render_template('index.html', 
                           patios=patio_names,
                           resultado_tempo=resultado_tempo_formatado, 
                           resultado_valor=resultado_valor_formatado,
                           selected_patio=patio_selecionado_nome)


# 5. INÍCIO DO SERVIDOR FLASK: (Mantenha como está)
if __name__ == '__main__':
    app.run(debug=True)
