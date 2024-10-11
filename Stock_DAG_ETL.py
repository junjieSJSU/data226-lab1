from airflow import DAG
from airflow.models import Variable
from airflow.decorators import task
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

from datetime import timedelta
from datetime import datetime
import requests


def return_snowflake_conn(con_id):

    # Initialize the SnowflakeHook
    hook = SnowflakeHook(snowflake_conn_id=con_id, warehouse='compute_wh', database='LAB1', schema='raw_data')
    
    # Execute the query and fetch results
    conn = hook.get_conn()
    return conn.cursor()

@task
def extract(symbols, alpha_vantage_key):
  try:
    result = {}
    
    for symbol in symbols:
      url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={alpha_vantage_key}&datatype=json'
      
      response = requests.get(url)

      if response.status_code != 200:
        raise Exception(f'Request failed with status code {response.status_code}')

      data = response.json()

      if 'Error Message' in data:
          raise Exception(f"API Error: {data['Error Message']}")
        
      result[symbol] = data
    
    return result

  except requests.exceptions.RequestException as e:
    raise Exception(f"Request failed: {e}")


@task
def transform(raw_data):
  results = {}
  
  for data in raw_data.values():
    if 'Time Series (Daily)' not in data:
      raise KeyError(f"Unexpected data format: 'Time Series (Daily)' key missing")
    
  for symbol, data in raw_data.items():
    stock_data = [
          {
              'date': key,
              'open': value['1. open'],
              'high': value['2. high'],
              'low': value['3. low'],
              'close': value['4. close'],
              'volume': value['5. volume'],
              'symbol': symbol
          }
          for key, value in data['Time Series (Daily)'].items()
      ]
    # Get only the last 90 days worth of data
    stock_data = stock_data[:90] if len(stock_data) >= 90 else stock_data
    
    results[symbol] = stock_data
    
  return results


@task
def load(stock_data, con, target_table):
  try:
        con.execute("BEGIN;")

        con.execute(f"DROP TABLE IF EXISTS {target_table};")

        con.execute(f'''CREATE OR REPLACE TABLE {target_table} (
                          date DATE,
                          open FLOAT,
                          high FLOAT,
                          low FLOAT,
                          close FLOAT,
                          volume INTEGER,
                          symbol VARCHAR,

                          PRIMARY KEY(date, symbol)
                          );''')

        # Start loading the data into the table
        insert_query = f'''INSERT INTO {target_table}
                           (date, open, high, low, close, volume, symbol)
                           VALUES (%s, %s, %s, %s, %s, %s, %s);'''

        for symbol, records in stock_data.items():
          for record in records:
            con.execute(insert_query, (
              record['date'],
              record['open'],
              record['high'],
              record['low'],
              record['close'],
              record['volume'],
              record['symbol']
              ))
          print(f"Data loaded successfully for stock symbol: {symbol}")

        con.execute("COMMIT;")
        print("All data loaded successfully.")
  except Exception as e:
    con.execute("ROLLBACK;")
    print(f"An error occurred: {e}")
    raise e


with DAG(
    dag_id = 'Stock_DAG_ETL',
    start_date = datetime(2024,10,9),
    catchup=False,
    tags=['ETL'],
    schedule = '30 2 * * *'
) as dag:
    alpha_vantage_key = Variable.get("alpha_vantage_key")
    target_table = "LAB1.raw_data.stock_data"
    symbols = ["MSFT", "AAPL"]
    cur = return_snowflake_conn("snowflake-conn")

    raw_data = extract(symbols, alpha_vantage_key)
    data = transform(raw_data)
    load(data, cur, target_table)