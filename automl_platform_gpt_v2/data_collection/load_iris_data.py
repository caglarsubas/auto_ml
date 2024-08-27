# data_collection/load_iris_data.py
import pandas as pd
from sklearn.datasets import load_iris
from django.db import connection

def load_data():
    iris = load_iris()
    df = pd.DataFrame(data=iris.data, columns=iris.feature_names)
    df['target'] = iris.target

    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE IF NOT EXISTS iris_data (sepal_length float, sepal_width float, petal_length float, petal_width float, target integer);")
        for row in df.itertuples(index=False):
            cursor.execute("INSERT INTO iris_data (sepal_length, sepal_width, petal_length, petal_width, target) VALUES (%s, %s, %s, %s, %s);", row)
