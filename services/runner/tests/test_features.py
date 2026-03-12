import pandas as pd

from app.features import build_preprocessor, engineer_features


def test_extended_feature_profile_adds_engineered_columns() -> None:
    frame = pd.DataFrame(
        [
            {
                'PassengerId': 1,
                'Name': 'Doe, Mr. John',
                'Cabin': 'C85',
                'Pclass': 1,
                'Sex': 'male',
                'Age': 34,
                'SibSp': 1,
                'Parch': 0,
                'Fare': 71.2833,
                'Embarked': 'C',
            }
        ]
    )

    engineered = engineer_features(frame, 'extended')
    _, summary = build_preprocessor('extended')

    assert {'FamilySize', 'IsAlone', 'NameLength', 'Title', 'Deck'}.issubset(engineered.columns)
    assert 'Title' in summary['categorical_features']
