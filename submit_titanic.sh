#!/bin/bash
# Submit Titanic submission to Kaggle

export KAGGLE_API_TOKEN="KGAT_bc49a5d0e8803de3d69b0a722712c48d"

echo "Submitting to Kaggle..."
kaggle competitions submit -c titanic \
    -f /tmp/titanic-kaggle/submission.csv \
    -m "Glasslab Titanic Submission (Random Forest)"

echo ""
echo "Checking submission status..."
kaggle competitions submissions -c titanic
