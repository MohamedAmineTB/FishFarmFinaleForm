# Oxygen-drop model

**Question it answers:** "Will dissolved oxygen in this basin fall below the warning level for its species before 06:00?"
The answer is a probability, shown everywhere as an **estimate** (basin cards, basin page, Today pages, assistant).
Alerts never come from this model: they come from the SQL alert engine.

## Why this question

Oxygen in a pond follows the sun: algae produce it during the day and use it at night, so the lowest value comes just
before dawn. A warning the evening before gives the farmer time to act cheaply (skip the evening feed, run the aerator
overnight) instead of reacting at 4 a.m.

## Data

- 30 days of history per basin from the database (the demo farm's backfill and the live simulator), averaged every 15 minutes.
- One training sample per basin per hour (about 2,800 samples).
- **Label:** 1 if the lowest oxygen between that hour and the next 06:00 (farm time) is below the species warning level
  (e.g. 7.0 mg/L for rainbow trout, 5.0 mg/L for tilapia and carp).

## Features (`backend/app/ml/features.py`)

| Feature | Meaning |
|---|---|
| `do_now`, `do_gap` | current oxygen, and its distance to the warning level |
| `do_decline_3h` | evening oxygen decline: mg/L lost per hour over the last 3 h |
| `do_mean_6h`, `do_std_6h` | rolling mean and spread over 6 h |
| `do_min_24h_gap` | how far last night's low was from the warning level |
| `temp_now` | warm water holds less oxygen |
| `ph_now` | high afternoon pH means strong algae activity |
| `hour_sin`, `hour_cos` | time of day (circular encoding) |
| `feed_kg_per_m3` | feeding load: uneaten feed and fish respiration use oxygen |

Every rolling window only looks at the past, so no information from the future leaks into a sample.

## Model and evaluation (`backend/app/ml/train.py`)

- Random forest (scikit-learn, 300 trees, depth 8, `class_weight="balanced"`).
- **Split by time:** the first 75 % of the period trains the model, the last 25 % tests it. Shuffling would let the
  model see neighbouring hours of the same night and overstate its quality.
- After evaluation the model is refitted on all the data and saved to `ml/artifacts/model.joblib`.
- The scores are written to [`artifacts/metrics.json`](artifacts/metrics.json).

Results on the held-out week (demo farm):

| | Precision | Recall | F1 | Confusion matrix (tn / fp / fn / tp) |
|---|---|---|---|---|
| Random forest | 0.89 | 1.00 | 0.94 | 501 / 21 / 0 / 174 |
| Baseline: "it dipped in the last 24 h, so it will again" | 0.98 | 1.00 | 0.99 | 518 / 4 / 0 / 174 |

ROC AUC of the model: 1.00. Most important features: last night's low relative to the warning level (0.33), water
temperature (0.32), feeding load (0.17).

## Honest reading of these numbers

- **The simple baseline is slightly better.** The data is simulated, and each basin's nights look very much alike: the trout
  basin dips under its 7.0 mg/L warning level almost every night, the others almost never. Persistence ("same as last night")
  is therefore a very strong rule, and the model mostly learns it plus which basin it is looking at (temperature and feeding
  load act as basin identifiers).
- `class_weight="balanced"` favours recall: it is better to warn on a calm night (false positive: skip a feed) than to miss
  a real dip (false negative: dead fish).
- On a real farm, weather (cloud cover, wind), algae blooms and feeding changes make nights differ much more. That is where a
  model can beat persistence, and the features above are the ones the literature points to. The pipeline, features and
  evaluation are ready for that data; the numbers above should not be read as real-world performance.

## Run it

```bash
python ml/train.py            # or, from backend/: python -m app.ml.train
```

The API trains a model automatically on first use if `model.joblib` is missing. The pipeline service refreshes the
predictions of every basin every 5 minutes; `GET /api/basins/{id}/prediction` computes one on demand.
