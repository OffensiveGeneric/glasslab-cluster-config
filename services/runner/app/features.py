from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


BASIC_NUMERIC_FEATURES = ['Pclass', 'Age', 'SibSp', 'Parch', 'Fare']
BASIC_CATEGORICAL_FEATURES = ['Sex', 'Embarked']
EXTENDED_NUMERIC_FEATURES = BASIC_NUMERIC_FEATURES + ['FamilySize', 'IsAlone', 'NameLength']
EXTENDED_CATEGORICAL_FEATURES = BASIC_CATEGORICAL_FEATURES + ['Title', 'Deck']


REQUIRED_SOURCE_COLUMNS = ['Pclass', 'Sex', 'Age', 'SibSp', 'Parch', 'Fare', 'Embarked', 'Name', 'Cabin']


def engineer_features(frame: pd.DataFrame, profile: str) -> pd.DataFrame:
    prepared = frame.copy()
    for column in REQUIRED_SOURCE_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = pd.NA

    if profile == 'extended':
        prepared['FamilySize'] = prepared['SibSp'].fillna(0) + prepared['Parch'].fillna(0) + 1
        prepared['IsAlone'] = (prepared['FamilySize'] == 1).astype(int)
        prepared['NameLength'] = prepared['Name'].fillna('').astype(str).str.len()
        prepared['Title'] = (
            prepared['Name']
            .fillna('')
            .astype(str)
            .str.extract(r',\s*([^\.]+)\.', expand=False)
            .fillna('Unknown')
        )
        prepared['Deck'] = prepared['Cabin'].fillna('U').astype(str).str[0].replace('', 'U')
    return prepared


def build_preprocessor(profile: str) -> tuple[ColumnTransformer, dict]:
    if profile == 'extended':
        numeric_features = EXTENDED_NUMERIC_FEATURES
        categorical_features = EXTENDED_CATEGORICAL_FEATURES
        engineered_features = ['FamilySize', 'IsAlone', 'NameLength', 'Title', 'Deck']
    else:
        numeric_features = BASIC_NUMERIC_FEATURES
        categorical_features = BASIC_CATEGORICAL_FEATURES
        engineered_features = []

    numeric_pipeline = Pipeline(
        steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ('numeric', numeric_pipeline, numeric_features),
            ('categorical', categorical_pipeline, categorical_features),
        ]
    )
    feature_summary = {
        'profile': profile,
        'numeric_features': numeric_features,
        'categorical_features': categorical_features,
        'engineered_features': engineered_features,
    }
    return preprocessor, feature_summary
