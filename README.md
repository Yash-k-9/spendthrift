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
| 2 | **Locally Weighted Regression** | `budget/ml/lwr.py` | Predicts next month's spending per category, income and savings rate, and the **probability of meeting the savings goal**. Uses a shrunken trend (local level + ¼ of the local slope, τ = 2) so month-to-month noise isn't extended as a trend. |
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

k-Means finds one-off purchases (a laptop, a holiday) and removes them before LWR forecasts, so a
one-time purchase isn't treated as a trend.

## Training data

- **k-NN:** 633 labelled merchant names and phrases across 23 categories (Indian supermarkets, food apps,
  fuel, billers, insurers, lenders, OTT, travel, salons, brokers...), each written the ways transactions
  really arrive: typed, bank SMS / statement narration (`UPI/ZOMATO/8812`, `POS AMAZON BANGALORE`,
  `ZOMATO PVT LTD`) and UPI-app style (`Paid to Zomato`). That's 3,654 training examples, plus every
  category the family corrects.
- **ID3:** all 96 combinations of its five attributes, labelled by personal-finance rules, plus the family's
  own Reasonable/Unnecessary labels (weighted 3×).
- **LWR, k-Means, EM, Genetic Algorithm:** learn from the family's own history. The demo family has 12
  months (about 690 transactions) with 15 planted one-off purchases and spending that creeps up over the
  last 6 months.

## Results (`python scripts/evaluate_models.py`)

| Model | Result |
|---|---|
| k-NN categorizer | **100%** on 120 real-world descriptions of known merchants (84% before the data was expanded); **82%** on 22 merchants never in the training data; 50% when whole merchants are held out of training |
| ID3 | 85% 5-fold cross-validated accuracy on combinations it didn't see; flags frequent food-delivery orders as unnecessary |
| LWR forecast | On 10 demo families never used for tuning (12 months each), average back-test error ₹410 per category-month vs ₹447 for "same as last month", ₹416 for the 3-month average and ₹488 for plain LWR. Best on average at 6, 9 and 12 months, 9–16% better than plain LWR. Sept → Oct predicted within ~2% for the demo family |
| k-Means | Isolates all 15 one-off purchases into their own cluster, with no false members |
| EM anomalies | Catches 5 of the 7 big one-offs (laptop, phone, flights, school admission...) with no false alarms |
| Genetic Algorithm | Reaches the savings target without touching rent, EMIs, insurance, school fees or healthcare |

The 🧠 Models tab in the web app shows these numbers live: accuracy against *k*, back-test error by method and τ,
the learned tree rules, the elbow curve, EM convergence and GA convergence.

## App tabs

- **📊 Dashboard:** income, spending, savings rate, category donut, 50/30/20 check, monthly trend.
- **🔍 Insights:** unnecessary expenses (ID3) with reasons, unusual expenses (EM), alerts and tips.
- **🔮 Predictions:** next month's forecast (LWR), chance of meeting the goal, and the GA savings plan,
  which you can apply as budgets in one click. If the predicted month has already happened, the app
  compares the prediction with reality.
- **🧩 Patterns:** k-Means clusters with a scatter plot and adjustable *k*.
- **🎯 Budgets:** per-category limits, suggestions and progress bars.
- **➕ Add / Import:** add expenses, or import a bank statement **PDF** (net-banking statement or UPI-app
  history, password-protected files supported) or CSV, auto-categorized by k-NN with confidence scores.
  Rows already recorded (same date, amount and type, e.g. captured from SMS) are flagged and skipped.
  "See how k-NN decides" shows the nearest neighbours.
- **📋 Transactions:** correct categories (k-NN learns) and label expenses Reasonable/Unnecessary
  (the decision tree learns).
- **🧠 Models:** how each algorithm works, with evaluation charts.

## 🏆 Goals & Rewards

- **Spending plans:** decide what you'll spend in any period (this week, next month, a trip). Set a total target
  plus planned amounts per category, or click *Fill from my recent spending* to start from your averages.
  Each plan shows spent vs planned, unplanned spending, and where you'll end up at the current pace.
- **Reminders:** at 80% and 100% of a plan or a planned category, when a monthly budget is exceeded, or when the
  pace means you'll overspend. They appear as in-app toasts and, once you click *Turn on notifications*, as
  desktop/phone notifications while the app is open. Each alert is shown once.
- **Reward points (a game):**

  | Points | For |
  |---|---|
  | +10 | each clean day: no unnecessary expense (no-spend days count too) |
  | +30 | every 7-day clean streak |
  | −1 per 250 spent | each unnecessary expense (min −1, max −10) |
  | +100 / −50 | a finished plan kept within / over its total |
  | +10 | each planned category kept within its amount |
  | +75 | a month that meets the savings goal |

  "Unnecessary" comes from the ID3 tree, or your own label in 📋 Transactions, which always wins. Points build
  up through levels (🌱 Seedling → 👑 Budget Master), unlock badges, and feed a family leaderboard ranked by
  each member's share of unnecessary spending. Points are recalculated from your data, so they always match it.

## 🔒 Encrypted transaction ledger

Every transaction (manual, CSV, demo or SMS) is stored encrypted and tamper-evident:

| Layer | What it does |
|---|---|
| **AES-256-GCM** | All transaction details are one encrypted column; a fresh random nonce per record. Changing any byte makes decryption fail. |
| **SHA-256 hash chain** | `record_hash = SHA-256(prev_hash, content_hash, key_version)`, so editing, deleting or reordering a past row breaks every later hash. |
| **Ed25519 signature** | Each `record_hash` is signed, so the chain can't be rebuilt without the private key. |
| **HMAC-SHA256** | Detects duplicate SMS without storing anything readable. |

Category and Reasonable/Unnecessary labels are encrypted separately and bound to their row, so they can be
edited without breaking the chain. Deleting a transaction erases its details but keeps its hashes, so the chain
still verifies. The **📱 SMS & Security** tab has a *Verify integrity* button.

**Keys** (`LEDGER_KEY`, `LEDGER_SIGNING_KEY`) are generated into `.env` on first start and never stored in the
database. **Back up `.env`**: without it the transactions can't be decrypted.

Upgrading from the unencrypted version? Run `python scripts/encrypt_legacy.py` to move the old `transactions`
table into the ledger and drop the plaintext copy.

## 📱 Bank SMS capture

`POST /api/sms` takes `{"sender": "VM-HDFCBK", "body": "<sms text>"}` with header `X-SMS-Token: <SMS_TOKEN from .env>`.
The SMS is parsed (HDFC, SBI, ICICI, Axis, Kotak and similar formats), categorized by k-NN, encrypted and stored.
OTP and promotional messages are rejected, and duplicates are ignored.

- **Demo mode:** in the **📱 SMS & Security** tab, *Simulate bank SMS* runs realistic messages through the same pipeline.
- **Real phone (same Wi-Fi):** start the server with `uvicorn api.main:app --host 0.0.0.0 --port 8000`. The tab
  shows your Network URL (e.g. `http://192.168.1.6:8000/api/sms`). Point an SMS forwarder app (SMS to URL
  Forwarder, MacroDroid or Tasker) at it, filtered to bank senders.
- **Away from home:** use a tunnel (Cloudflare Tunnel / ngrok) or host the backend.

## Architecture

```
Browser (HTML / CSS / JS)  ──fetch JSON──►  FastAPI (api/main.py)  ──►  budget/ (ML)  ──►  PostgreSQL
frontend/                                   /api/*  +  serves frontend/              budget/storage.py
```

## Project structure

```
family_budget/
├── api/main.py             FastAPI backend: JSON API under /api, serves the frontend at /
├── frontend/               Plain HTML, CSS and JavaScript (no build step)
│   ├── index.html
│   ├── css/style.css
│   └── js/                 main.js (shell), api.js, ui.js, tabs/*.js (one file per tab)
├── budget/
│   ├── ml/                 The six algorithms, from scratch (NumPy only)
│   │   ├── knn.py  text.py  lwr.py  id3.py  kmeans.py  gmm_em.py  genetic.py
│   ├── categorizer.py      k-NN categorizer + evaluation
│   ├── forecaster.py       Shrunken-trend LWR forecast, back-test, goal probability
│   ├── necessity.py        Expense features + ID3 classification
│   ├── patterns.py         k-Means spending patterns
│   ├── anomalies.py        EM anomaly detection
│   ├── planner.py          Genetic-algorithm savings plan
│   ├── analyzer.py         Plain statistics: summaries, trends, alerts
│   ├── training_data.py    Built-in labelled data (k-NN phrases, ID3 expert examples)
│   ├── storage.py          PostgreSQL storage: encrypted, hash-chained, signed ledger
│   ├── crypto.py           AES-256-GCM, SHA-256 chain, Ed25519, HMAC
│   ├── sms.py              Bank SMS parser
│   ├── sms_demo.py         Realistic fake bank SMS for demo mode
│   ├── goals.py            Spending plans, alerts and reward points
│   ├── statement_pdf.py    Bank / UPI-app statement PDF parser
│   ├── evaluation.py       Realistic test sets and metrics for all six models
│   └── sample_data.py      12-month demo family
├── scripts/migrate_sqlite.py  Copy the old SQLite data/budget.db into PostgreSQL
├── scripts/encrypt_legacy.py  Encrypt transactions left in the old plaintext table
├── scripts/make_sample_statements.py  Sample statement PDFs for trying the PDF import
├── scripts/evaluate_models.py  Train all six models and print an evaluation report
├── tests/                  algorithms, API, security/SMS, and goals tests
├── docker-compose.yml      Optional PostgreSQL in Docker
├── .env.example            DATABASE_URL template
├── sample_statement.csv    Example bank statement for the importer
└── requirements.txt
```

## Setup and run

1. Install the Python packages:

   ```bash
   pip install -r requirements.txt
   ```

2. Point the app at PostgreSQL. Copy `.env.example` to `.env` and set your password:

   ```
   DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/family_budget
   ```

   The `family_budget` database and its tables are created automatically on first start.
   No local PostgreSQL? Run `docker compose up -d` and use
   `postgresql+psycopg://postgres:postgres@localhost:5433/family_budget`.

3. Start the server:

   ```bash
   uvicorn api.main:app --reload
   ```

   Open http://localhost:8000. In the sidebar, open **🗂️ Data → Load demo family (12 months)**.
   Interactive API docs are at http://localhost:8000/docs.

To bring over data from the old SQLite version: `python scripts/migrate_sqlite.py`.

Charts use Plotly.js, loaded from jsDelivr. All the machine learning still runs locally.

Run the tests (they use a temporary SQLite file, so no PostgreSQL is needed):

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
5. **Add / Import:** import `sample_statement.csv`, or a PDF from `samples/` (create them with
   `python scripts/make_sample_statements.py`; the SBI-style one's password is `demo1234`), and watch k-NN categorize it. Open *See how k-NN
   decides* to show the neighbours.
6. **Transactions:** correct a category or label an expense, and show that the models learn from it.
7. **Models:** walk through each algorithm's evaluation chart.
