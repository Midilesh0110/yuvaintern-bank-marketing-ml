#!/usr/bin/env python3
"""Reproducible UCI Bank Marketing classification project.

The prediction is made before an outbound call. Post-call duration and the
current-campaign contact count are therefore excluded to prevent target leakage.
The final 20% of the UCI date-ordered dataset is reserved as a future-like holdout.
"""
from __future__ import annotations
import json, zipfile, urllib.request
from io import BytesIO
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
    precision_recall_curve)
from sklearn.model_selection import TimeSeriesSplit, cross_validate, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
FIG = ROOT / "figures"
URL = "https://archive.ics.uci.edu/static/public/222/bank+marketing.zip"
ZIP_PATH = DATA / "bank+marketing.zip"
CSV_PATH = DATA / "bank-additional-full.csv"
RANDOM_STATE = 42


def load_data() -> pd.DataFrame:
    DATA.mkdir(exist_ok=True)
    if not ZIP_PATH.exists():
        urllib.request.urlretrieve(URL, ZIP_PATH)
    if not CSV_PATH.exists():
        with zipfile.ZipFile(ZIP_PATH) as zf:
            nested = BytesIO(zf.read("bank-additional.zip"))
        with zipfile.ZipFile(nested) as data_zip:
            member = next(n for n in data_zip.namelist() if n.endswith("bank-additional-full.csv"))
            with data_zip.open(member) as src, CSV_PATH.open("wb") as dst:
                dst.write(src.read())
    return pd.read_csv(CSV_PATH, sep=";")


def make_preprocessor(X: pd.DataFrame) -> ColumnTransformer:
    nums = X.select_dtypes(include=["number"]).columns.tolist()
    cats = X.select_dtypes(exclude=["number"]).columns.tolist()
    numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    return ColumnTransformer([("num", numeric, nums), ("cat", categorical, cats)],
                             remainder="drop")


def main() -> None:
    OUT.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
    sns.set_theme(style="whitegrid", palette="deep")
    df = load_data()
    # UCI bank-additional-full is documented as ordered by date. Preserve this order.
    df["previously_contacted"] = (df["pdays"] != 999).astype(int)
    # A decision before the current outbound call cannot know its duration or
    # the current campaign's final contact count; omit both from the predictors.
    excluded = ["y", "duration", "campaign", "pdays"]
    X = df.drop(columns=excluded)
    y = (df["y"] == "yes").astype(int)
    split = int(len(df) * 0.80)
    X_train, X_test = X.iloc[:split].copy(), X.iloc[split:].copy()
    y_train, y_test = y.iloc[:split].copy(), y.iloc[split:].copy()
    pre = make_preprocessor(X_train)
    models = {
        "majority_baseline": Pipeline([("prep", pre), ("model", DummyClassifier(strategy="most_frequent"))]),
        "logistic_regression": Pipeline([("prep", make_preprocessor(X_train)), ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_STATE))]),
        "random_forest": Pipeline([("prep", make_preprocessor(X_train)), ("model", RandomForestClassifier(n_estimators=250, min_samples_leaf=3, max_features="sqrt", class_weight="balanced_subsample", n_jobs=-1, random_state=RANDOM_STATE))]),
    }
    cv = TimeSeriesSplit(n_splits=4)
    cv_summary = {}
    for name in ("logistic_regression", "random_forest"):
        scores = cross_validate(models[name], X_train, y_train, cv=cv,
                                scoring={"ap":"average_precision", "roc_auc":"roc_auc", "f1":"f1"},
                                n_jobs=1, return_train_score=False)
        cv_summary[name] = {metric: {"mean": float(np.mean(scores[f"test_{metric}"])),
                                     "std": float(np.std(scores[f"test_{metric}"]))}
                            for metric in ("ap", "roc_auc", "f1")}
    rows = []
    test_probabilities = {}
    fitted = {}
    for name, pipe in models.items():
        pipe.fit(X_train, y_train)
        fitted[name] = pipe
        if hasattr(pipe, "predict_proba"):
            p = pipe.predict_proba(X_test)[:, 1]
        else:
            p = np.zeros(len(y_test))
        test_probabilities[name] = p
        pred = (p >= 0.5).astype(int)
        rows.append({"model":name, "average_precision":float(average_precision_score(y_test,p)),
                     "roc_auc":float(roc_auc_score(y_test,p)) if name != "majority_baseline" else None,
                     "precision_at_0_5":float(precision_score(y_test,pred,zero_division=0)),
                     "recall_at_0_5":float(recall_score(y_test,pred,zero_division=0)),
                     "f1_at_0_5":float(f1_score(y_test,pred,zero_division=0)),
                     "balanced_accuracy_at_0_5":float(balanced_accuracy_score(y_test,pred))})
    metrics = {"dataset":"UCI Bank Marketing, bank-additional-full.csv",
       "dataset_url":"https://archive.ics.uci.edu/dataset/222/bank+marketing",
       "rows":int(len(df)), "features_in_raw_file":int(df.shape[1]-1),
       "positive_rate_all":float(y.mean()), "missing_cells_raw":int(df.isna().sum().sum()),
       "train_rows":int(len(X_train)), "test_rows":int(len(X_test)),
       "test_positive_rate":float(y_test.mean()), "feature_count_model":int(X.shape[1]),
       "excluded_for_pre_call_leakage":["duration","campaign"],
       "split":"chronological ordered 80/20 holdout; first 80% training; last 20% final test",
       "cv":"4-fold expanding-window TimeSeriesSplit on training period",
       "threshold":0.5, "cv_training":cv_summary, "holdout_test":rows,
       "interpretation":"Holdout scores estimate retrospective performance on this historical benchmark, not expected performance on a current bank campaign. No deployment or causal uplift claim is supported."}
    (OUT/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT/"holdout_metrics.csv", index=False)

    # EDA: class distribution.
    fig, ax = plt.subplots(figsize=(7,4.2))
    counts = df["y"].value_counts().reindex(["no","yes"])
    ax.bar(["No subscription","Subscription"], counts.values, color=["#9fb7c9","#e57c3c"])
    ax.set(title="Target distribution", ylabel="Observations")
    for i,v in enumerate(counts.values): ax.text(i, v+max(counts.values)*.012, f"{v:,} ({v/len(df):.1%})", ha="center", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG/"target_distribution.png", dpi=180); plt.close(fig)
    # Campaign-month contact outcome rate. (month is known at call time in this historical data.)
    rate = df.groupby("month", observed=False)["y"].apply(lambda s:(s=="yes").mean()).sort_values(ascending=False)
    fig, ax=plt.subplots(figsize=(8,4.2)); rate.plot(kind="bar", color="#2f7d8f", ax=ax)
    ax.set(title="Historical subscription rate by campaign month", ylabel="Share subscribing", xlabel="Month")
    ax.tick_params(axis="x", rotation=0); fig.tight_layout(); fig.savefig(FIG/"month_conversion_rate.png", dpi=180); plt.close(fig)
    # Precision-recall curves on the untouched holdout.
    fig, ax=plt.subplots(figsize=(7,4.7))
    for name in ("logistic_regression","random_forest"):
        p=test_probabilities[name]; precision,recall,_=precision_recall_curve(y_test,p)
        ax.plot(recall,precision,label=f"{name.replace('_',' ').title()} (AP={average_precision_score(y_test,p):.3f})")
    ax.axhline(y_test.mean(), ls="--", color="gray", label=f"Positive prevalence={y_test.mean():.3f}")
    ax.set(xlabel="Recall",ylabel="Precision",title="Precision–recall curves on chronological holdout")
    ax.legend(); fig.tight_layout(); fig.savefig(FIG/"precision_recall.png", dpi=180); plt.close(fig)
    # Random forest confusion matrix at the predeclared 0.5 threshold.
    pred=(test_probabilities["random_forest"]>=0.5).astype(int)
    cm=confusion_matrix(y_test,pred)
    fig,ax=plt.subplots(figsize=(5.3,4.3)); sns.heatmap(cm,annot=True,fmt=",d",cmap="Blues",cbar=False,ax=ax,
       xticklabels=["No","Yes"],yticklabels=["No","Yes"])
    ax.set(xlabel="Predicted",ylabel="Actual",title="Random forest: holdout confusion matrix (0.5 threshold)")
    fig.tight_layout(); fig.savefig(FIG/"random_forest_confusion_matrix.png",dpi=180); plt.close(fig)
    # compact EDA snapshot
    eda={"rows":len(df),"columns":int(df.shape[1]),"missing_cells":int(df.isna().sum().sum()),
         "target_counts":{str(k):int(v) for k,v in df["y"].value_counts().items()},
         "target_rates_by_month":{str(k):float(v) for k,v in rate.items()},
         "numeric_summary":df.select_dtypes(include=["number"]).describe().round(3).to_dict()}
    (OUT/"eda_summary.json").write_text(json.dumps(eda,indent=2),encoding="utf-8")
    print(json.dumps(metrics,indent=2))

if __name__ == "__main__": main()
