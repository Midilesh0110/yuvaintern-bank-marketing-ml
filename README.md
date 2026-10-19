# Bank Marketing Subscription Prediction

A reproducible, leakage-aware machine-learning case study built around the UCI Bank Marketing dataset for the YuvaIntern Virtual Junior Machine Learning Analyst tasks. The objective is to rank potential term-deposit subscribers before an outbound call, using a historical public benchmark. The project is instructional and retrospective; it is not an operational banking system or evidence of deployment.

## Data and provenance

The source is the UCI Machine Learning Repository **Bank Marketing** collection: <https://archive.ics.uci.edu/dataset/222/bank+marketing>, DOI [10.24432/C5K306](https://doi.org/10.24432/C5K306). The analysis uses `bank-additional-full.csv`, described by UCI as 41,188 observations and 20 input variables, ordered by date. UCI lists the data as CC BY 4.0; retain attribution and the source citation in any redistribution. The dataset reflects a Portuguese bank’s 2008–2010 telemarketing campaigns and is not representative of current customers or current marketing practices.

The script downloads the dataset archive into `data/` when first run. The data archive is excluded from Git by `.gitignore` to avoid redistributing third-party data unnecessarily; UCI’s license and attribution still apply if it is shared.

## Prediction timing and leakage controls

The task is framed as a pre-call ranking problem. The target is `y` (term-deposit subscription). The call `duration` is deliberately excluded because it is only known after a call and can reveal the outcome. `campaign` (contact count including the current contact) is excluded because its final value is not available before the call. The model derives a `previously_contacted` flag from UCI’s `pdays` field, where 999 denotes no prior campaign contact, then drops the raw sentinel-valued column. The feature decision avoids treating 999 as a meaningful elapsed time and avoids using a training-period feature with no observed prior contacts.

## Validation and outputs

The ordered observations are split once: first 80% for training and the final 20% as a future-like holdout. Four expanding-window `TimeSeriesSplit` folds are used on the training portion for model comparison. All imputers, scaling and one-hot encoding live inside scikit-learn pipelines to avoid validation leakage. A majority-class dummy is the baseline; balanced logistic regression and a class-weighted random forest are compared. Holdout metrics include average precision, ROC-AUC, precision, recall, F1 and balanced accuracy at a stated 0.50 threshold. The threshold is a fixed illustrative default, not an optimized operating point.

The script writes `outputs/metrics.json`, `outputs/holdout_metrics.csv`, `outputs/eda_summary.json`, and PNG figures in `figures/`. Do not interpret these historical benchmark scores as expected current deployment performance. Before any real use, establish a current, consented, representative dataset, test fairness and calibration, choose an operating threshold with stakeholders, and evaluate against a genuinely future period.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python src/run_analysis.py
```

## Citation

Moro, S., Rita, P., & Cortez, P. (2014). *Bank Marketing* [Dataset]. UCI Machine Learning Repository. <https://doi.org/10.24432/C5K306>.

## License

Project code: MIT License (see `LICENSE`). Dataset: CC BY 4.0, held and attributed by UCI; see the dataset record for details.
