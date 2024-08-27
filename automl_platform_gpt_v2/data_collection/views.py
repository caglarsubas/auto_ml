from django.http import JsonResponse
from django.db import connection

def iris_data(request):
    column = request.GET.get('column', 'sepal_length')
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column}, COUNT(*) FROM iris_data GROUP BY {column} ORDER BY {column};")
        data = cursor.fetchall()

    response = {
        'labels': [str(row[0]) for row in data],
        'values': [row[1] for row in data],
    }
    return JsonResponse(response)
