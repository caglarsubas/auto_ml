import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.preprocessing import LabelEncoder
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_recall_curve, auc, average_precision_score
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import label_binarize

def preprocess_data(file_path):
    # Load data
    data = pd.read_csv(file_path)
    
    # Variable demystifying
    numerical_cols = data.select_dtypes(include=['int64', 'float64']).columns
    categorical_cols = data.select_dtypes(include=['object']).columns
    
    # Zero variance cleaning
    zero_variance_boolean_list = (data.loc[:,numerical_cols].var()==0).tolist()
    zero_variance_list = [col for col, flag in zip(numerical_cols, zero_variance_boolean_list) if flag]
    data = data.drop(zero_variance_list, axis=1)
    
    # Duplicated columns dropping
    data = data.loc[:, ~data.columns.duplicated()]
    
    # Train-test split
    X = data.drop('target', axis=1)
    y = data['target']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # Outlier cleaning
    for col in numerical_cols:
        lower_quantile = X_train[col].quantile(0.01)
        upper_quantile = X_train[col].quantile(0.99)
        X_train = X_train[(X_train[col] >= lower_quantile) & (X_train[col] <= upper_quantile)]
        y_train = y_train[X_train.index]
    
    for col in [col for col in categorical_cols if col!='target']:
        rare_categories = X_train[col].value_counts()[X_train[col].value_counts() < len(X_train) * 0.005].index
        X_train.loc[X_train[col].isin(rare_categories), col] = 'Other'
    
    # Missing value imputation
    for col in numerical_cols:
        X_train[col].fillna(X_train[col].median(), inplace=True)
        X_test[col].fillna(X_train[col].median(), inplace=True)
    
    for col in [col for col in categorical_cols if col!='target']:
        X_train[col].fillna(X_train[col].mode()[0], inplace=True)
        X_test[col].fillna(X_train[col].mode()[0], inplace=True)
    
    # Scaling
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train[numerical_cols])
    X_test_scaled = scaler.transform(X_test[numerical_cols])
    
    # Encoding
    X_train_encoded = pd.get_dummies(X_train, columns=[col for col in categorical_cols if col!='target'])
    X_test_encoded = pd.get_dummies(X_test, columns=[col for col in categorical_cols if col!='target'])
    le = LabelEncoder()
    y_train = le.fit_transform(y_train)
    y_test = le.transform(y_test)
    
    return X_train_encoded, X_test_encoded, y_train, y_test

def train_model(data, algorithm, hyperparameters):
    X_train, X_test, y_train, y_test = data
    
    if algorithm == 'logistic_regression':
        model = LogisticRegression(**hyperparameters)
    elif algorithm == 'xgboost':
        model = XGBClassifier(**hyperparameters)
    
    model.fit(X_train, y_train)
    return model

def evaluate_model(model, data):
    X_train, X_test, y_train, y_test = data
    y_pred = model.predict(X_test)
    if len(model.classes_)==2:
        y_pred_proba = model.predict_proba(X_test)[:, 1]
    elif len(model.classes_)>2:
        y_pred_proba = model.predict_proba(X_test)
    
    accuracy = accuracy_score(y_test, y_pred)
    if len(model.classes_)==2:
        precision, recall, _ = precision_recall_curve(y_test, y_pred_proba)
        pr_auc = auc(recall, precision)
    elif len(model.classes_)>2:
        y_test_binarized = label_binarize(y_test, classes=model.classes_)
        precision, recall, _ = precision_recall_curve(y_test_binarized.ravel(), y_pred_proba.ravel())
        pr_auc = auc(recall, precision)
        average_precision = average_precision_score(y_test_binarized, y_pred_proba, average="micro")

    # Generate plots
    plt.figure(figsize=(10, 5))
    plt.subplot(1, 2, 1)
    sns.countplot(x=y_test)
    plt.title('Distribution of Target Variable')
    
    plt.subplot(1, 2, 2)
    if len(model.classes_)==2:
        plt.plot(recall, precision, label=f'PR-AUC: {pr_auc:.2f}')
    elif len(model.classes_)>2:
        plt.plot(recall, precision, lw=2, label='Micro-average PR curve (area = {0:0.2f})'.format(average_precision))
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curve')
    plt.legend()
    
    plt.tight_layout()
    plt.savefig('model_evaluation_plots.png')
    
    return {
        'accuracy': accuracy,
        'pr_auc': pr_auc,
        'plots': 'model_evaluation_plots.png'
    }