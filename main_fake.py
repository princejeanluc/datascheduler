import pandas as pd
from sqlalchemy import create_engine

# 1. Define your connection string
username = ''
password = 'YOUR_PASSWORD'
host = 'YOUR_HOST'
port = '1521'
service_name = 'YOUR_SERVICE_NAME'

# Format the SQLAlchemy connection string
connection_string = f"oracle+oracledb://{username}:{password}@{host}:{port}/{service_name}"
engine = create_engine(connection_string)

# 2. Query data
query = "SELECT * FROM "
df = pd.read_sql(query, con=engine)



print(df.head())