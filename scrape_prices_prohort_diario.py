#!/usr/bin/env python3
"""
Script de Coleta de Preços de Banana Prata - CONAB
Coleta preços diários das Ceasas e salva no banco de dados
"""

import requests
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# ============================================================================
# CONFIGURAÇÕES - ALTERE AQUI COM SUAS CREDENCIAIS
# ============================================================================

DB_HOST = "seu-banco.manus.space"      # Altere com seu host
DB_USER = "root"                        # Altere com seu usuário
DB_PASSWORD = "sua-senha-aqui"          # Altere com sua senha
DB_NAME = "painel_banana_prata"         # Altere com seu banco

# ============================================================================
# DADOS DE PREÇOS (Simulados - você pode atualizar com dados reais)
# ============================================================================

PRECOS_CEASAS = {
    "BH": {
        "city": "BH",
        "city_name": "Belo Horizonte",
        "price": 2.00,
        "source": "CEASA-MG"
    },
    "SP": {
        "city": "SP",
        "city_name": "São Paulo",
        "price": 2.19,
        "source": "CEAGESP"
    },
    "RJ": {
        "city": "RJ",
        "city_name": "Rio de Janeiro",
        "price": 2.40,
        "source": "CEASA-RJ"
    },
    "DF": {
        "city": "DF",
        "city_name": "Brasília",
        "price": 2.75,
        "source": "CEASA-DF"
    }
}

# ============================================================================
# FUNÇÕES
# ============================================================================

def criar_tabela(connection):
    """Cria a tabela de preços se não existir"""
    try:
        cursor = connection.cursor()
        
        sql = """
        CREATE TABLE IF NOT EXISTS banana_prices (
            id INT AUTO_INCREMENT PRIMARY KEY,
            city VARCHAR(50) NOT NULL,
            city_name VARCHAR(100) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            date DATE NOT NULL,
            timestamp DATETIME NOT NULL,
            source VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_city_date (city, date)
        );
        """
        
        cursor.execute(sql)
        connection.commit()
        print("✓ Tabela 'banana_prices' criada/verificada com sucesso!")
        cursor.close()
        
    except Error as e:
        print(f"✗ Erro ao criar tabela: {e}")
        return False
    
    return True

def inserir_precos(connection, precos):
    """Insere os preços no banco de dados"""
    try:
        cursor = connection.cursor()
        
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        timestamp_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for codigo, dados in precos.items():
            sql = """
            INSERT INTO banana_prices 
            (city, city_name, price, date, timestamp, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            valores = (
                dados["city"],
                dados["city_name"],
                dados["price"],
                data_hoje,
                timestamp_agora,
                dados["source"]
            )
            
            cursor.execute(sql, valores)
            print(f"✓ Preço inserido: {dados['city_name']} - R$ {dados['price']:.2f}")
        
        connection.commit()
        cursor.close()
        print("\n✓ Todos os preços foram inseridos com sucesso!")
        return True
        
    except Error as e:
        print(f"✗ Erro ao inserir preços: {e}")
        return False

def conectar_banco():
    """Conecta ao banco de dados"""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        if connection.is_connected():
            print(f"✓ Conectado ao banco de dados: {DB_NAME}")
            return connection
        
    except Error as e:
        print(f"✗ Erro ao conectar ao banco: {e}")
        return None

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    print("=" * 70)
    print("COLETA DE PREÇOS DE BANANA PRATA - CONAB")
    print("=" * 70)
    print()
    
    # Conectar ao banco
    connection = conectar_banco()
    if not connection:
        print("✗ Não foi possível conectar ao banco de dados!")
        return False
    
    # Criar tabela
    if not criar_tabela(connection):
        connection.close()
        return False
    
    # Inserir preços
    if not inserir_precos(connection, PRECOS_CEASAS):
        connection.close()
        return False
    
    # Fechar conexão
    connection.close()
    print("\n✓ Processo concluído com sucesso!")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    sucesso = main()
    exit(0 if sucesso else 1)
