#!/usr/bin/env python3
"""
Script de Coleta de Preços de Banana Prata - CONAB
Versão melhorada com melhor tratamento de erros
"""

import os
import sys
from datetime import datetime

# Verificar se as dependências estão instaladas
try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    print("✗ Erro: mysql-connector-python não está instalado")
    print("Instale com: pip install mysql-connector-python")
    sys.exit(1)

# ============================================================================
# CONFIGURAÇÕES - LER DAS VARIÁVEIS DE AMBIENTE (GitHub Secrets)
# ============================================================================

DB_HOST = os.getenv("DB_HOST", "").strip()
DB_USER = os.getenv("DB_USER", "").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "").strip()
DB_NAME = os.getenv("DB_NAME", "").strip()

# ============================================================================
# VALIDAÇÃO DE CREDENCIAIS
# ============================================================================

print("=" * 70)
print("COLETA DE PREÇOS DE BANANA PRATA - CONAB")
print("=" * 70)
print()

# Verificar se as credenciais foram fornecidas
if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    print("✗ ERRO: Credenciais do banco de dados não foram fornecidas!")
    print()
    print("Credenciais recebidas:")
    print(f"  DB_HOST: {'✓' if DB_HOST else '✗ VAZIO'}")
    print(f"  DB_USER: {'✓' if DB_USER else '✗ VAZIO'}")
    print(f"  DB_PASSWORD: {'✓' if DB_PASSWORD else '✗ VAZIO'}")
    print(f"  DB_NAME: {'✓' if DB_NAME else '✗ VAZIO'}")
    print()
    print("Verifique se os secrets foram adicionados no GitHub:")
    print("  Settings → Secrets and variables → Actions")
    sys.exit(1)

print("✓ Credenciais recebidas:")
print(f"  Host: {DB_HOST}")
print(f"  Usuário: {DB_USER}")
print(f"  Banco: {DB_NAME}")
print()

# ============================================================================
# DADOS DE PREÇOS
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

def conectar_banco():
    """Conecta ao banco de dados com tratamento de erro detalhado"""
    try:
        print("Conectando ao banco de dados...")
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            autocommit=True
        )
        
        if connection.is_connected():
            print(f"✓ Conectado com sucesso ao banco: {DB_NAME}")
            return connection
        
    except Error as e:
        print(f"✗ ERRO ao conectar ao banco de dados:")
        print(f"  Código de erro: {e.errno}")
        print(f"  Mensagem: {e.msg}")
        print()
        print("Possíveis causas:")
        print("  1. Host incorreto ou offline")
        print("  2. Usuário ou senha incorretos")
        print("  3. Banco de dados não existe")
        print("  4. Sem permissão de acesso")
        return None

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
        print("✓ Tabela 'banana_prices' criada/verificada com sucesso!")
        cursor.close()
        return True
        
    except Error as e:
        print(f"✗ Erro ao criar tabela:")
        print(f"  {e}")
        return False

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
        
        cursor.close()
        print("\n✓ Todos os preços foram inseridos com sucesso!")
        return True
        
    except Error as e:
        print(f"✗ Erro ao inserir preços:")
        print(f"  {e}")
        return False

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    # Conectar ao banco
    connection = conectar_banco()
    if not connection:
        print("\n✗ Não foi possível conectar ao banco de dados!")
        print("=" * 70)
        return False
    
    print()
    
    # Criar tabela
    if not criar_tabela(connection):
        connection.close()
        print("\n✗ Erro ao criar tabela!")
        print("=" * 70)
        return False
    
    print()
    
    # Inserir preços
    if not inserir_precos(connection, PRECOS_CEASAS):
        connection.close()
        print("\n✗ Erro ao inserir preços!")
        print("=" * 70)
        return False
    
    # Fechar conexão
    connection.close()
    print("\n✓ Processo concluído com sucesso!")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    sucesso = main()
    exit(0 if sucesso else 1)
