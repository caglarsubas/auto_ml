from sklearn import datasets
from .models import Dataset, DataPoint
import logging
logger = logging.getLogger(__name__)

def collect_dataset(dataset_name):
    print(f"Collecting dataset: {dataset_name}")
    dataset_name = dataset_name.lower()  # Convert to lowercase for case-insensitive comparison
    dataset_loaders = {
        'iris': datasets.load_iris,
        'breast_cancer': datasets.load_breast_cancer,
        'wine': datasets.load_wine
    }
    
    if dataset_name not in dataset_loaders:
        raise ValueError(f"Dataset {dataset_name} not supported")
    
    data = dataset_loaders[dataset_name]()
    
    dataset, created = Dataset.objects.get_or_create(
        name=dataset_name,
        defaults={'description': data.DESCR}
    )
    
    if not created:
        dataset.datapoints.all().delete()
    
    datapoints = []
    for features, target in zip(data.data, data.target):
        datapoint = DataPoint(
            dataset=dataset,
            feature_values=dict(zip(data.feature_names, features)),
            target_value=target
        )
        datapoints.append(datapoint)
    
    DataPoint.objects.bulk_create(datapoints)
    
    logger.info(f"Collected {len(datapoints)} datapoints for dataset {dataset_name}")
    
    return dataset