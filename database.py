import sqlite3
from datetime import datetime, timedelta

def conectar_bd():
    conn = sqlite3.connect('condominio.db')
    conn.row_factory = sqlite3.Row
    return conn

def criar_tabelas():
    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        # Tabela de unidades
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS unidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL CHECK(tipo IN ('casa', 'salao'))
        )""")
        
        # Tabela de medições mensais
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            valor_total REAL NOT NULL,
            data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mes, ano)
        )""")
        
        # Tabela de consumos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS consumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unidade_id INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            consumo_anterior INTEGER NOT NULL DEFAULT 0,
            consumo_atual INTEGER NOT NULL,
            diferenca INTEGER NOT NULL,
            porcentagem TEXT NOT NULL,
            valor_unitario REAL NOT NULL,
            rateio_salao REAL NOT NULL,
            valor_total REAL NOT NULL,
            medicoes_id INTEGER,
            FOREIGN KEY (unidade_id) REFERENCES unidades(id),
            FOREIGN KEY (medicoes_id) REFERENCES medicoes(id),
            UNIQUE(unidade_id, mes, ano)
        )""")

        # Inserir unidades padrão
        unidades = [
            ('Casa 01', 'casa'), ('Casa 02', 'casa'), ('Casa 03', 'casa'),
            ('Casa 04', 'casa'), ('Casa 05', 'casa'), ('Casa 06', 'casa'),
            ('Casa 07', 'casa'), ('Casa 08', 'casa'), ('Casa 09', 'casa'),
            ('Casa 10', 'casa'), ('Salão de festas', 'salao')
        ]
        
        cursor.executemany("INSERT OR IGNORE INTO unidades (nome, tipo) VALUES (?, ?)", unidades)
        conn.commit()

def inserir_dados_iniciais():
    valores_anteriores = {
        'Casa 01': 7060,
        'Casa 02': 196,
        'Casa 03': 2295,
        'Casa 04': 2633,
        'Casa 05': 18148,
        'Casa 06': 2392,
        'Casa 07': 2096,
        'Casa 08': 10732,
        'Casa 09': 1067,
        'Casa 10': 1898,
        'Salão de festas': 7394
    }

    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        # Verifica se já existem dados
        cursor.execute("SELECT COUNT(*) FROM consumos")
        if cursor.fetchone()[0] > 0:
            print("O banco já contém dados. Use atualizar_consumos_anteriores()")
            return

        # Cria uma medição inicial
        data_base = datetime.now().replace(day=1) - timedelta(days=1)  # Mês anterior
        cursor.execute("""
            INSERT INTO medicoes (mes, ano, valor_total)
            VALUES (?, ?, ?)
        """, (data_base.month, data_base.year, 0))
        medicao_id = cursor.lastrowid

        # Insere os consumos iniciais
        for nome, consumo in valores_anteriores.items():
            cursor.execute("SELECT id FROM unidades WHERE nome = ?", (nome,))
            unidade_id = cursor.fetchone()[0]
            
            cursor.execute("""
                INSERT INTO consumos (
                    unidade_id, mes, ano, consumo_anterior, consumo_atual,
                    diferenca, porcentagem, valor_unitario, rateio_salao,
                    valor_total, medicoes_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                unidade_id, data_base.month, data_base.year,
                consumo, consumo,  # consumo_anterior e atual iguais
                0, "0%", 0, 0, 0, medicao_id
            ))
        
        conn.commit()
        print("Dados iniciais inseridos com sucesso!")

def atualizar_consumos_anteriores():
    valores_anteriores = {
        'Casa 01': 7060,
        'Casa 02': 196,
        'Casa 03': 2295,
        'Casa 04': 2633,
        'Casa 05': 18148,
        'Casa 06': 2392,
        'Casa 07': 2096,
        'Casa 08': 10732,
        'Casa 09': 1067,
        'Casa 10': 1898,
        'Salão de festas': 7394
    }

    with conectar_bd() as conn:
        cursor = conn.cursor()
        
        for nome, consumo in valores_anteriores.items():
            cursor.execute("SELECT id FROM unidades WHERE nome = ?", (nome,))
            unidade_id = cursor.fetchone()[0]
            
            # Atualiza o último registro de cada unidade
            cursor.execute("""
                UPDATE consumos 
                SET consumo_anterior = ?
                WHERE id = (
                    SELECT id FROM consumos 
                    WHERE unidade_id = ? 
                    ORDER BY ano DESC, mes DESC 
                    LIMIT 1
                )
            """, (consumo, unidade_id))
        
        conn.commit()
        print("Consumos anteriores atualizados com sucesso!")

# Execução inicial
criar_tabelas()
inserir_dados_iniciais()  # Executar apenas uma vez para inicialização