# 💰 AI-Based Family Budget Planner for Savings

A machine-learning budgeting system that helps families track income, expenses and savings. It
automatically categorizes expenses, analyses monthly spending, identifies unnecessary or excessive
expenses, predicts next month's outcome, and builds a personalised savings plan.

All AI runs **locally**, using six classical ML algorithms **implemented from scratch with NumPy**.
There is no API key, no internet connection and no scikit-learn.

**UN Sustainable Development Goals**
- **SDG 8 – Decent Work and Economic Growth:** household financial security, savings habits and
  financial literacy.
- **SDG 12 – Responsible Consumption and Production:** surfaces impulse buying, unused subscriptions and
  over-consumption, and nudges families towards mindful spending.

## Algorithms and what they do

| # | Algorithm | File | Job in the project |
|---|---|---|---|
| 1 | **k-Nearest Neighbor** | `budget/ml/knn.py` (+ TF-IDF in `text.py`) | Auto-categorizes each expense from its description ("UPI/ZOMATO/8812" → Dining Out). It learns instantly from every category the family corrects. |
| 2 | **Locally Weighted Regression** | `budget/ml/lwr.py` | Predicts next month's spending per category, income and savings rate, and the **probability of meeting the savings goal**. The bandwidth τ is chosen by back-testing. |
| 3 | **ID3 Decision Tree** | `budget/ml/id3.py` | Classifies each expense as **Reasonable / Unnecessary** using entropy and information gain, and explains why with the decision path. It retrains on the family's own labels. |
| 4 | **k-Means** | `budget/ml/kmeans.py` | Discovers spending patterns: fixed bills, frequent small spends, large one-off purchases. Uses k-means++ initialisation and the elbow method. |
| 5 | **Expectation-Maximization** | `budget/ml/gmm_em.py` | Fits a Gaussian Mixture Model of "normal" expenses. Very unlikely, unusually large expenses are flagged as excessive. |
| 6 | **Genetic Algorithm** | `budget/ml/genetic.py` | Searches for the best savings plan: how much to cut each category to hit a savings target with the least disruption. |

### How they work together

```
 bank statement / manual entry
          │
          ▼
   [1] k-NN categorizes ───────────────► category of every expense
          │
          ├──► [4] k-Means ──► spending patterns ──► one-off purchases ─┐
          │                                                             ▼
          ├──► [2] LWR forecasts next month (one-offs removed) ──► predicted spending,
          │                                                       P(meet savings goal)
          │                                                             │
          │                                                             ▼
          │                                         [6] Genetic Algorithm → savings plan
          │                                                             │  (→ budgets)
          ├──► [3] ID3 Decision Tree ──► unnecessary expenses + reasons
          └──► [5] EM / GMM ──► unusual or excessive expenses
```

k-Means finds one-off purchases (a laptop, a holiday) and removes them before LWR forecasts. On the
demo data this makes the LWR forecast beat both the "same as last month" and "3-month average"
baselines in back-testing.

## Results on the demo family (6 months)

| Model | Result |
|---|---|
| k-NN categorizer | ~97% accuracy on new phrasings of known merchants; ~25% on completely unseen brand names (why corrections matter) |
| LWR forecast | Sept → Oct spending predicted within ~5% of actual; back-test MAE lower than both baselines |
| k-Means | Isolates all 8 one-off purchases into their own cluster |
| EM anomalies | Flags the ₹42,000 laptop (16× usual) and the Diwali shopping spree |
| ID3 | Flags the month's frequent food-delivery and café orders as unnecessary ("want → purchases are frequent") |
| Genetic Algorithm | Reaches the savings target without touching rent, EMIs, insurance, school fees or healthcare |

The 🧠 Models tab in the app shows these numbers live: accuracy against *k*, back-test error against τ,
the learned tree rules, the elbow curve, EM convergence and GA convergence.

## App tabs

- **📊 Dashboard:** income, spending, savings rate, category donut, 50/30/20 check, monthly trend.
- **🔍 Insights:** unnecessary expenses (ID3) with reasons, unusual expenses (EM), alerts and tips.
- **🔮 Predictions:** next month's forecast (LWR), chance of meeting the goal, and the GA savings plan,
  which you can apply as budgets in one click. If the predicted month has already happened, the app
  compares the prediction with reality.
- **🧩 Patterns:** k-Means clusters with a scatter plot and adjustable *k*.
- **🎯 Budgets:** per-category limits, suggestions and progress bars.
- **➕ Add / Import:** add expenses or import a CSV, auto-categorized by k-NN with confidence scores.
  "See how k-NN decides" shows the nearest neighbours.
- **📋 Transactions:** correct categories (k-NN learns) and label expenses Reasonable/Unnecessary
  (the decision tree learns).
- **🧠 Models:** how each algorithm works, with evaluation charts.

## Project structure

```
family_budget/
├── app.py                  Streamlit UI
├── budget/
│   ├── ml/                 The six algorithms, from scratch (NumPy only)
│   │   ├── knn.py  text.py  lwr.py  id3.py  kmeans.py  gmm_em.py  genetic.py
│   ├── categorizer.py      k-NN categorizer + evaluation
│   ├── forecaster.py       LWR forecasting, τ selection, back-test, goal probability
│   ├── necessity.py        Expense features + ID3 classification
│   ├── patterns.py         k-Means spending patterns
│   ├── anomalies.py        EM anomaly detection
│   ├── planner.py          Genetic-algorithm savings plan
│   ├── analyzer.py         Plain statistics: summaries, trends, alerts
│   ├── training_data.py    Built-in labelled data (k-NN phrases, ID3 expert examples)
│   ├── storage.py          SQLite storage
│   └── sample_data.py      6-month demo family
├── tests/test_budget.py    26 tests (algorithms + features)
├── sample_statement.csv    Example bank statement for the importer
└── requirements.txt
```

## Setup and run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. In the sidebar, open **🗂️ Data → Load 6-month demo family**.

Run the tests:

```bash
python -m pytest -q
```

## Demo script (for a presentation or viva)

1. **Dashboard:** the demo family's savings are falling month by month.
2. **Insights:** ID3 flags food-delivery orders as unnecessary and shows the decision path. EM flags
   the ₹42,000 laptop.
3. **Patterns:** k-Means separates fixed bills, frequent small spends and one-off purchases.
4. **Predictions:** pick **September** in the sidebar. LWR predicts October, and the app shows how
   close it got to what actually happened. Then pick **October**, set a 30% target, and the GA builds
   a plan. Click *Use this plan as my budgets*.
5. **Add / Import:** import `sample_statement.csv` and watch k-NN categorize it. Open *See how k-NN
   decides* to show the neighbours.
6. **Transactions:** correct a category or label an expense, and show that the models learn from it.
7. **Models:** walk through each algorithm's evaluation chart.
