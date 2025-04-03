from flask import Flask, render_template, request, jsonify, send_file
from database import conectar_bd, criar_tabelas
from datetime import datetime
import pandas as pd
import io

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'

# Criar tabelas ao iniciar
criar_tabelas()

# Adicionando filtros de template
@app.template_filter('format_month')
def format_month(value):
    if isinstance(value, datetime):
        meses = {
            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
        }
        return f"{meses[value.month]}/{value.year}"
    return value

@app.template_filter('format_currency')
def format_currency(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

# Adicionando variáveis globais ao contexto do template
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Rotas existentes (mantenha todas as rotas que você já tinha)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ultima-leitura/<tipo>/<id_unidade>')
def ultima_leitura(tipo, id_unidade):
    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        if tipo == 'salao':
            cursor.execute("""
                SELECT consumo_atual as ultimaLeitura 
                FROM consumos 
                WHERE unidade_id = (SELECT id FROM unidades WHERE nome = 'Salão de Festas') 
                ORDER BY ano DESC, mes DESC 
                LIMIT 1
            """)
        else:  # apartamento
            cursor.execute("""
                SELECT consumo_atual as ultimaLeitura 
                FROM consumos 
                WHERE unidade_id = (SELECT id FROM unidades WHERE nome = ?) 
                ORDER BY ano DESC, mes DESC 
                LIMIT 1
            """, (f"Apartamento {id_unidade}",))
        
        resultado = cursor.fetchone()
        return jsonify({
            'ultimaLeitura': resultado['ultimaLeitura'] if resultado else 0
        })

@app.route('/api/verificar-mes/<ano>/<mes>')
def verificar_mes(ano, mes):
    with conectar_bd() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total 
            FROM consumos 
            WHERE ano = ? AND mes = ?
        """, (int(ano), int(mes)))
        
        resultado = cursor.fetchone()
        return jsonify({
            'existe': resultado['total'] > 0
        })
    
@app.route('/api/ultimas-leituras')
def obter_ultimas_leituras():
    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        # Obter mês/ano atual
        hoje = datetime.now()
        mes_atual = hoje.month
        ano_atual = hoje.year
        
        # Buscar última leitura de cada unidade
        cursor.execute("""
            SELECT u.nome, c.consumo_atual
            FROM consumos c
            JOIN unidades u ON c.unidade_id = u.id
            WHERE (c.mes < ? AND c.ano = ?) OR (c.ano < ?)
            ORDER BY c.ano DESC, c.mes DESC
        """, (mes_atual, ano_atual, ano_atual))
        
        leituras = {}
        for row in cursor.fetchall():
            nome = row['nome']
            if nome not in leituras:  # Pega apenas a última leitura de cada unidade
                leituras[nome] = row['consumo_atual']
        
        return jsonify(leituras)

# Modified function to return total_consumo
def calcular_rateio(dados):
    valor_total = dados['valor_total']
    total_consumo = 0
    consumo_salao = 0
    consumo_casas = 0
    unidades_com_consumo = []

    # Calcular consumo de cada unidade e totais
    for unidade in dados['unidades']:
        consumo = unidade['atual'] - unidade['anterior']
        if consumo > 0:
            if 'Salão' in unidade['nome']:
                consumo_salao = consumo
            else:
                consumo_casas += consumo
            unidades_com_consumo.append({
                'nome': unidade['nome'],
                'consumo': consumo,
                'valor_rateado': 0,
                'participacao': 0  # Novo campo para participação
            })
    
    total_consumo = consumo_salao + consumo_casas

    # Calcular valores proporcionais e participação
    if total_consumo > 0:
        # Valor do salão é proporcional ao seu consumo
        valor_salao = (consumo_salao / total_consumo) * valor_total
        
        # Valor disponível para as casas
        valor_casas = valor_total - valor_salao
        
        # Distribuir o valor das casas proporcionalmente ao consumo de cada uma
        for unidade in unidades_com_consumo:
            if 'Salão' in unidade['nome']:
                unidade['valor_rateado'] = valor_salao
                unidade['participacao'] = (valor_salao / valor_total) * 100
            elif consumo_casas > 0:
                unidade['valor_rateado'] = (unidade['consumo'] / consumo_casas) * valor_casas
                unidade['participacao'] = (unidade['valor_rateado'] / valor_total) * 100
    else:
        # Caso não haja consumo (situação especial)
        valor_salao = 0
        for unidade in unidades_com_consumo:
            unidade['valor_rateado'] = 0
            unidade['participacao'] = 0

    # Return total_consumo as well
    return unidades_com_consumo, valor_salao, total_consumo

# Then modify the route to use the returned total_consumo
@app.route('/api/salvar-registros', methods=['POST'])
def salvar_registros():
    dados = request.json
    
    try:
        with conectar_bd() as conn:
            cursor = conn.cursor()
            
            # Pegar o valor total da fatura dos dados recebidos
            valor_total = dados.get('valor_total', 0)  
            
            # Calcular consumos e rateios - now also getting total_consumo
            unidades_com_consumo, valor_salao, total_consumo = calcular_rateio(dados)
            
            # Rest of the function remains the same
            # ...

            # Now total_consumo is available for the JSON response
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Registros salvos com cálculo proporcional!',
                'detalhes': {
                    'valor_total': valor_total,
                    'total_consumo': total_consumo,
                    'unidades': unidades_com_consumo
                }
            })
    # ...

    except Exception as e:
        return jsonify({
            'status': 'erro',
            'mensagem': f'Erro ao salvar registros: {str(e)}'
        }), 500

@app.route('/historico')
def historico():
    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        # Buscar todos os meses/anos com registros
        cursor.execute("""
            SELECT DISTINCT ano, mes 
            FROM consumos 
            ORDER BY ano DESC, mes DESC
        """)
        periodos = cursor.fetchall()
        
        # Formatar os períodos para exibição
        periodos_formatados = []
        for periodo in periodos:
            data = datetime(periodo['ano'], periodo['mes'], 1)
            periodos_formatados.append({
                'ano': periodo['ano'],
                'mes': periodo['mes'],
                'descricao': data.strftime("%B/%Y").capitalize(),
                'valor': f"{periodo['ano']}-{periodo['mes']:02d}"
            })
    
    return render_template('historico.html', periodos=periodos_formatados)

@app.route('/historico/<ano>-<mes>')
def detalhes_historico(ano, mes):
    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        # Buscar resumo do período (usando os NOVOS campos)
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT unidade_id) as total_unidades,
                SUM(consumo_atual - consumo_anterior) as total_consumo,
                SUM(valor_total) as total_valor,
                SUM(CASE WHEN u.tipo = 'salao' THEN valor_total ELSE 0 END) as total_salao,
                SUM(CASE WHEN u.tipo = 'casa' THEN valor_total ELSE 0 END) as total_aptos
            FROM consumos c
            JOIN unidades u ON c.unidade_id = u.id
            WHERE c.ano = ? AND c.mes = ?
        """, (int(ano), int(mes)))
        
        resumo = dict(cursor.fetchone())
        
        # Buscar detalhes com os NOVOS campos
        cursor.execute("""
            SELECT 
                u.nome,
                c.consumo_anterior,
                c.consumo_atual,
                c.consumo_atual - c.consumo_anterior as consumo,
                c.diferenca,
                c.porcentagem,
                c.valor_unitario,
                c.rateio_salao,
                c.valor_total as valor
            FROM consumos c
            JOIN unidades u ON c.unidade_id = u.id
            WHERE c.ano = ? AND c.mes = ?
            ORDER BY 
                CASE 
                    WHEN u.tipo = 'salao' THEN 999
                    ELSE CAST(SUBSTR(u.nome, 12) AS INTEGER)
                END
        """, (int(ano), int(mes)))
        
        detalhes = [dict(row) for row in cursor.fetchall()]
        
        salao = next((item for item in detalhes if 'Salão' in item['nome']), None)
        apartamentos = [item for item in detalhes if 'Salão' not in item['nome']]
        
        data = datetime(int(ano), int(mes), 1)
        resumo_template = {
            'mes_atual': data,
            'total_apartamentos': len(apartamentos),
            'total_condominio': resumo['total_consumo'],
            'total_valor_aptos': resumo['total_aptos'],
            'total_salao': resumo['total_salao'],
            'numero_registro': resumo['total_consumo']
        }
        
        detalhes_template = []
        for apto in apartamentos:
            detalhes_template.append({
                'apartamento': apto['nome'],
                'consumo': apto['consumo'],
                'valor': apto['valor_unitario'],
                'rateio_salao': apto['rateio_salao'],
                'valor_total': apto['valor']
            })
    
    return render_template(
    'detalhes_historico.html',
    resumo=resumo_template,
    detalhes=detalhes_template,
    medicao_id=f"{ano}-{mes}",
    detalhes_debug={
        'valor_total': resumo['total_valor'],
        'total_salao': resumo['total_salao'],
        'total_aptos': resumo['total_valor_aptos']
    }
)

# Na rota /exportar/<medicao_id> - MODIFICADA
@app.route('/exportar/<medicao_id>')
def exportar_medicao(medicao_id):
    ano, mes = medicao_id.split('-')
    
    with conectar_bd() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                u.nome as Unidade,
                c.consumo_anterior as 'Leitura Anterior',
                c.consumo_atual as 'Leitura Atual',
                c.consumo_atual - c.consumo_anterior as 'Consumo (kWh)',
                c.porcentagem as 'Participação (%)',  -- Alterado de 'Variação' para 'Participação'
                c.valor_unitario as 'Valor Unitário (R$)',
                c.rateio_salao as 'Rateio Salão (R$)',
                c.valor_total as 'Total a Pagar (R$)'
            FROM consumos c
            JOIN unidades u ON c.unidade_id = u.id
            WHERE c.ano = ? AND c.mes = ?
            ORDER BY 
                CASE 
                    WHEN u.tipo = 'salao' THEN 999
                    ELSE CAST(SUBSTR(u.nome, 12) AS INTEGER)
                END
        """, (int(ano), int(mes)))
        
        dados = cursor.fetchall()
        df = pd.DataFrame(dados)
        
        # Calcular totais
        totais = {
            'Unidade': 'TOTAL',
            'Leitura Anterior': '',
            'Leitura Atual': '',
            'Consumo (kWh)': df['Consumo (kWh)'].sum(),
            'Variação (%)': '',
            'Valor Unitário (R$)': df['Valor Unitário (R$)'].sum(),
            'Rateio Salão (R$)': df['Rateio Salão (R$)'].sum(),
            'Total a Pagar (R$)': df['Total a Pagar (R$)'].sum()
        }
        df = pd.concat([df, pd.DataFrame([totais])], ignore_index=True)
        
        # Criar arquivo Excel em memória
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(writer, sheet_name='Consumo', index=False)
        
        # Formatar a planilha
        workbook = writer.book
        worksheet = writer.sheets['Consumo']
        
        # Formatar cabeçalho
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Formatar moeda
        money_format = workbook.add_format({'num_format': 'R$ #,##0.00'})
        worksheet.set_column(4, 4, None, money_format)  # Coluna Valor (R$)
        
        # Formatar total
        total_format = workbook.add_format({
            'bold': True,
            'fg_color': '#FFCC99',
            'border': 1
        })
        worksheet.set_row(len(df)-1, None, total_format)
        
        writer.save()
        output.seek(0)
        
        # Nome do arquivo
        data = datetime(int(ano), int(mes), 1)
        nome_arquivo = f"consumo_{data.strftime('%m_%Y')}.xlsx"
        
        return send_file(
            output,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

if __name__ == '__main__':
    app.run(debug=True)