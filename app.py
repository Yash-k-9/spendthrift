"""AI-Based Family Budget Planner - Streamlit app.

Everything runs locally. The AI is classical machine learning implemented from
scratch in NumPy (see budget/ml/):
    k-NN                         auto-categorizes expenses
    Locally Weighted Regression  predicts next month's spending and savings
    ID3 Decision Tree            flags unnecessary expenses (with reasons)
    k-Means                      discovers spending patterns
    EM (Gaussian Mixture)        detects unusual / excessive expenses
    Genetic Algorithm            finds the best savings plan

Run with:  streamlit run app.py
"""

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from budget import analyzer, anomalies, categorizer, forecaster, necessity, patterns, planner, sample_data
from budget.categorizer import ALL_CATEGORIES, EXPENSE_CATEGORIES, INCOME_CATEGORIES, KNNCategorizer
from budget.storage import BudgetStore

st.set_page_config(page_title="Family Budget Planner", page_icon="💰", layout="wide")

store = BudgetStore()
CUR = store.get_setting("currency")
GOAL = float(store.get_setting("savings_goal_pct"))
SEVERITY_ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}
CHART = dict(margin=dict(t=10, b=10, l=10, r=10), legend=dict(orientation="h", y=1.12))


def money(x: float) -> str:
    return f"{'-' if x < 0 else ''}{CUR}{abs(x):,.0f}"


# ---------------------------------------------------------------- cached models
@st.cache_resource(show_spinner=False)
def get_categorizer(corrections: tuple) -> KNNCategorizer:
    return KNNCategorizer(list(corrections))


@st.cache_data(show_spinner=False)
def knn_evaluation() -> dict:
    return categorizer.evaluate()


@st.cache_data(show_spinner=False)
def run_patterns(df: pd.DataFrame, k: int):
    return patterns.find_patterns(df, k)


@st.cache_data(show_spinner=False)
def run_anomalies(df: pd.DataFrame, month: str):
    return anomalies.detect(df, month)


@st.cache_data(show_spinner=False)
def run_plan(spend: dict, usual: dict, income: float, target: float):
    return planner.optimise_plan(spend, usual, income, target)


knn = get_categorizer(tuple(store.category_corrections()))

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("💰 Family Budget")
    st.caption("AI-based budget planner for savings · SDG 8 & SDG 12")

    df = store.transactions()
    month_list = analyzer.months(df)
    month = st.selectbox("Month", month_list, format_func=lambda m: pd.Period(m).strftime("%B %Y")) if month_list else None

    with st.expander("⚙️ Settings"):
        new_cur = st.text_input("Currency symbol", CUR, max_chars=4)
        new_goal = st.slider("Savings goal (% of income)", 5, 60, int(GOAL))
        new_size = st.number_input("Family members", 1, 20, int(store.get_setting("family_size")))
        if st.button("Save settings", use_container_width=True):
            store.set_setting("currency", new_cur)
            store.set_setting("savings_goal_pct", new_goal)
            store.set_setting("family_size", new_size)
            st.rerun()

    with st.expander("🗂️ Data"):
        if st.button("Load 6-month demo family", use_container_width=True):
            store.clear_transactions()
            store.add_many(sample_data.generate())
            st.rerun()
        if st.button("Delete all transactions", use_container_width=True):
            st.session_state["confirm_clear"] = True
        if st.session_state.get("confirm_clear"):
            st.warning("This permanently deletes every transaction.")
            c1, c2 = st.columns(2)
            if c1.button("Yes, delete"):
                store.clear_transactions()
                st.session_state["confirm_clear"] = False
                st.rerun()
            if c2.button("Cancel"):
                st.session_state["confirm_clear"] = False
                st.rerun()

    st.info("🧠 All AI runs on this computer - six ML algorithms written from scratch. No internet or API key.",
            icon="🔒")

tabs = st.tabs(["📊 Dashboard", "🔍 Insights", "🔮 Predictions", "🧩 Patterns", "🎯 Budgets",
                "➕ Add / Import", "📋 Transactions", "🧠 Models"])

if df.empty:
    for t in tabs[:5] + tabs[7:]:
        with t:
            st.info("No transactions yet. Add some in **➕ Add / Import**, or load the demo family from the sidebar.")

if not df.empty:
    budgets = store.budgets()
    pattern_result = run_patterns(df, 4)
    one_off_ids = pattern_result["one_off_ids"] if pattern_result else set()

    # ------------------------------------------------------------ dashboard
    with tabs[0]:
        s = analyzer.monthly_summary(df, month)
        prev = [m for m in month_list if m < month]
        p = analyzer.monthly_summary(df, prev[0]) if prev else None
        c = st.columns(4)
        c[0].metric("Income", money(s["income"]), money(s["income"] - p["income"]) if p else None)
        c[1].metric("Spending", money(s["spending"]), money(s["spending"] - p["spending"]) if p else None,
                    delta_color="inverse")
        c[2].metric("Net savings", money(s["net_savings"]), money(s["net_savings"] - p["net_savings"]) if p else None)
        c[3].metric("Savings rate", f"{s['savings_rate_pct']}%", f"{s['savings_rate_pct'] - GOAL:+.1f} pts vs {GOAL:g}% goal")
        if s["invested"]:
            st.caption(f"Includes {money(s['invested'])} moved into savings & investments.")

        left, right = st.columns(2)
        with left:
            st.subheader("Where the money went")
            b = analyzer.category_breakdown(df, month)
            fig = px.pie(b, names="category", values="amount", hole=0.5)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, height=360, **CHART)
            st.plotly_chart(fig, use_container_width=True)
        with right:
            st.subheader("50 / 30 / 20 check")
            split = analyzer.needs_wants_split(df, month)
            vals = [split["need_pct"], split["want_pct"], split["saving_pct"]]
            fig = go.Figure()
            fig.add_bar(name="You", x=["Needs", "Wants", "Savings"], y=vals, text=[f"{v}%" for v in vals])
            fig.add_bar(name="Target", x=["Needs", "Wants", "Savings"], y=[50, 30, 20], opacity=0.45)
            fig.update_layout(barmode="group", yaxis_title="% of income", height=360, **CHART)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Monthly trend")
        trend = analyzer.monthly_trend(df)
        fig = go.Figure()
        fig.add_bar(x=trend["month"], y=trend["income"], name="Income")
        fig.add_bar(x=trend["month"], y=trend["spending"], name="Spending")
        fig.add_scatter(x=trend["month"], y=trend["savings_rate_pct"], name="Savings rate %", yaxis="y2",
                        mode="lines+markers")
        fig.update_layout(barmode="group", height=380, yaxis2=dict(overlaying="y", side="right", title="Savings rate %"),
                          **CHART)
        st.plotly_chart(fig, use_container_width=True)

    # ------------------------------------------------------------ insights
    with tabs[1]:
        left, right = st.columns([3, 2])
        with left:
            st.subheader("🌳 Unnecessary expenses · Decision Tree (ID3)")
            classified, tree = necessity.classify_month(df, month, budgets)
            if classified.empty:
                st.info("No expenses this month.")
            else:
                unnecessary = classified[classified["prediction"] == "Unnecessary"]
                total_exp = classified["amount"].sum()
                c = st.columns(2)
                c[0].metric("Flagged as unnecessary", money(unnecessary["amount"].sum()),
                            f"{len(unnecessary)} of {len(classified)} expenses", delta_color="off")
                c[1].metric("Share of spending", f"{unnecessary['amount'].sum() / total_exp * 100:.1f}%" if total_exp else "0%")
                st.dataframe(
                    unnecessary[["date", "description", "category", "amount", "reason"]]
                    .sort_values("amount", ascending=False),
                    hide_index=True, use_container_width=True, height=280,
                    column_config={"date": st.column_config.DateColumn(format="DD MMM"),
                                   "amount": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                                   "reason": st.column_config.TextColumn("Why (decision path)", width="large")})
                st.caption("Disagree? Label expenses yourself in **📋 Transactions** - the tree retrains on your labels.")

            st.subheader("🚨 Unusual expenses · EM (Gaussian Mixture)")
            anomaly = run_anomalies(df, month)
            if anomaly is None:
                st.info(f"Needs at least {anomalies.MIN_TRANSACTIONS} expenses to learn what is normal.")
            elif anomaly["flagged"].empty:
                st.success("Nothing unusual this month.")
            else:
                for _, r in anomaly["flagged"].iterrows():
                    st.warning(f"**{r['description']}** - {money(r['amount'])} on {r['date']:%d %b}: "
                               f"{r['ratio']:.1f}× your usual {r['category'].lower()} expense.", icon="⚠️")

        with right:
            issues = analyzer.detect_issues(df, month, budgets, GOAL)
            st.subheader(f"Spending alerts ({len(issues)})")
            if not issues:
                st.success("No problems found this month. 🎉")
            for i in issues:
                with st.container(border=True):
                    st.markdown(f"{SEVERITY_ICON[i['severity']]} **{i['title']}**")
                    st.caption(i["detail"])
            st.subheader("Recommendations")
            for tip in analyzer.recommendations(df, month, budgets, GOAL):
                st.markdown(f"- {tip}")
            st.caption("For an optimised plan, see the Genetic Algorithm in **🔮 Predictions**.")

    # ------------------------------------------------------------ predictions
    with tabs[2]:
        fc = forecaster.forecast(df, month, GOAL, one_off_ids)
        if fc is None:
            st.info("Predictions need at least 2 months of data.")
        else:
            nm = pd.Period(fc["next_month"]).strftime("%B %Y")
            st.subheader(f"🔮 Forecast for {nm} · Locally Weighted Regression")
            st.caption(f"Predicts regular spending from months up to {pd.Period(month).strftime('%B %Y')}. "
                       f"{len(fc['excluded'])} one-off purchases found by k-Means are left out, since a one-time "
                       f"laptop is not a trend. Bandwidth τ = {fc['tau']} (picked automatically by back-testing).")
            c = st.columns(4)
            c[0].metric("Predicted income", money(fc["income_pred"]))
            lo, hi = fc["spending_range"]
            c[1].metric("Predicted spending", money(fc["spending_pred"]), f"80% range {money(lo)} - {money(hi)}",
                        delta_color="off")
            c[2].metric("Predicted savings rate", f"{fc['savings_rate_pred']:.1f}%",
                        f"{fc['savings_rate_pred'] - GOAL:+.1f} pts vs goal")
            c[3].metric(f"Chance of meeting {GOAL:g}% goal", f"{fc['prob_goal'] * 100:.0f}%")

            if fc["actual"]:
                a = fc["actual"]
                err = (fc["spending_pred"] - a["spending"]) / a["spending"] * 100 if a["spending"] else 0
                st.success(f"✅ **{nm} has already happened, so the prediction can be checked:** actual regular spending "
                           f"was {money(a['spending'])} vs predicted {money(fc['spending_pred'])} ({err:+.1f}% error).")

            left, right = st.columns([3, 2])
            with left:
                hist_total = fc["spend_history"].sum(axis=1)
                fig = go.Figure()
                fig.add_scatter(x=list(hist_total.index), y=hist_total.values, name="Spending (actual)", mode="lines+markers")
                fig.add_scatter(x=list(fc["income_history"].index), y=fc["income_history"].values, name="Income (actual)",
                                mode="lines+markers")
                fig.add_scatter(x=[hist_total.index[-1], fc["next_month"]], y=[hist_total.values[-1], fc["spending_pred"]],
                                name="Predicted spending", mode="lines+markers", line=dict(dash="dash"))
                fig.add_scatter(x=[fc["next_month"]] * 2, y=[lo, hi], mode="lines", name="80% range",
                                line=dict(width=8), opacity=0.3)
                fig.update_layout(height=360, yaxis_title=CUR, **CHART)
                st.plotly_chart(fig, use_container_width=True)
            with right:
                cats = fc["categories"].copy()
                cols = ["category", "avg_3_months", "predicted", "change_pct"] + (["actual"] if "actual" in cats else [])
                st.dataframe(cats[cols], hide_index=True, use_container_width=True, height=360,
                             column_config={
                                 "avg_3_months": st.column_config.NumberColumn("3-mo avg", format=f"{CUR}%.0f"),
                                 "predicted": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                                 "change_pct": st.column_config.NumberColumn("Change", format="%+.0f%%"),
                                 "actual": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                             })
            rising = cats[(cats["change_pct"] > 15) & (cats["predicted"] > 1000)]
            for _, r in rising.iterrows():
                st.markdown(f"📈 **{r['category']}** is heading for {money(r['predicted'])} "
                            f"({r['change_pct']:+.0f}% vs the 3-month average).")

            st.divider()
            st.subheader("🧬 Best savings plan · Genetic Algorithm")
            default_target = int(min(60, max(GOAL, round(fc["savings_rate_pred"] + 5))))
            target = st.slider("Target savings rate for the plan (%)", 5, 60, default_target,
                               help="Defaults to your goal, or 5 points above the forecast if you're already on track.")
            spend_pred = dict(zip(cats["category"], cats["predicted"]))
            usual = dict(zip(cats["category"], cats["avg_3_months"]))
            plan = run_plan(spend_pred, usual, fc["income_pred"], float(target))
            st.session_state["ga_history"] = plan["history"]
            if plan["needed"] <= 0:
                st.success(f"The forecast already meets a {target}% savings rate - no cuts needed.")
            else:
                c = st.columns(3)
                c[0].metric("Extra saving needed", money(plan["needed"]))
                c[1].metric("Plan saves", money(plan["saved"]), f"{money(plan['saved'] * 12)} / year", delta_color="off")
                c[2].metric("Savings rate with plan", f"{plan['new_savings_rate']:.1f}%")
                if not plan["reached"]:
                    st.warning(f"Even the maximum sensible cuts ({money(plan['max_possible'])}) can't fully close the gap. "
                               "Consider a lower target or a look at fixed costs.")
                st.dataframe(plan["plan"], hide_index=True, use_container_width=True,
                             column_config={
                                 "current": st.column_config.NumberColumn("Expected", format=f"{CUR}%.0f"),
                                 "cut_pct": st.column_config.ProgressColumn("Cut", format="%.0f%%", min_value=0, max_value=50),
                                 "saving": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                                 "new_budget": st.column_config.NumberColumn("New budget", format=f"{CUR}%.0f"),
                             })
                st.caption("The GA trims categories that have grown above their usual level first, cuts wants before "
                           "needs, and never touches rent, EMIs, insurance, school fees or healthcare.")
                if st.button("Use this plan as my budgets", type="primary"):
                    for _, r in plan["plan"].iterrows():
                        store.set_budget(r["category"], round(r["new_budget"] / 100) * 100)
                    st.success("Budgets updated - see **🎯 Budgets**.")

    # ------------------------------------------------------------ patterns
    with tabs[3]:
        st.subheader("🧩 Spending patterns · k-Means clustering")
        k = st.slider("Number of clusters (k)", 2, 7, 4, help="See the elbow chart in 🧠 Models for a good k.")
        pr = run_patterns(df, k)
        if pr is None:
            st.info("Needs more expenses to find patterns.")
        else:
            this_month = pr["transactions"][pr["transactions"]["month"] == month]
            month_totals = this_month.groupby("pattern")["amount"].sum()
            cols = st.columns(min(len(pr["summary"]), 4))
            for i, r in pr["summary"].iterrows():
                with cols[i % len(cols)].container(border=True):
                    st.markdown(f"**{r['name']}**")
                    st.metric("This month", money(month_totals.get(r["name"], 0.0)))
                    st.caption(f"{r['transactions']} expenses · typically {money(r['typical_amount'])} · "
                               f"{r['per_month']:.1f}×/month · seen in {r['recurrence_pct']:.0f}% of months")
                    st.caption(f"e.g. {r['examples']}")
            tx = pr["transactions"]
            fig = px.scatter(tx, x="per_month", y="amount", color="pattern", log_y=True, hover_name="description",
                             labels={"per_month": "Times per month", "amount": f"Amount ({CUR}, log scale)"})
            fig.update_traces(marker=dict(size=9, opacity=0.7))
            fig.update_layout(height=420, **CHART)
            st.plotly_chart(fig, use_container_width=True)
            frequent = pr["summary"][pr["summary"]["name"].str.startswith("Frequent")]
            for _, r in frequent.iterrows():
                st.info(f"💡 **{r['name']}** add up to {money(month_totals.get(r['name'], 0.0))} this month. "
                        "Small repeated purchases are the easiest place to save - try a weekly limit.")

    # ------------------------------------------------------------ budgets
    with tabs[4]:
        st.subheader("🎯 Monthly category budgets")
        b = analyzer.category_breakdown(df, month)
        spent = dict(zip(b["category"], b["amount"]))
        suggested = analyzer.suggest_budgets(df, month)
        cats_list = [c for c in EXPENSE_CATEGORIES if c != analyzer.SAVINGS_CATEGORY]
        table = pd.DataFrame({
            "Category": cats_list,
            "Type": [EXPENSE_CATEGORIES[c] for c in cats_list],
            "Spent this month": [spent.get(c, 0.0) for c in cats_list],
            "Suggested": [suggested.get(c, 0.0) for c in cats_list],
            "Budget": [budgets.get(c, 0.0) for c in cats_list],
        })
        edited = st.data_editor(
            table, hide_index=True, use_container_width=True, disabled=["Category", "Type", "Spent this month", "Suggested"],
            column_config={
                "Spent this month": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                "Suggested": st.column_config.NumberColumn(format=f"{CUR}%.0f", help="Recent average; wants trimmed 15%"),
                "Budget": st.column_config.NumberColumn(format=f"{CUR}%.0f", min_value=0, step=100, help="0 = no budget"),
            },
        )
        c1, c2 = st.columns(2)
        if c1.button("💾 Save budgets", type="primary", use_container_width=True):
            for _, row in edited.iterrows():
                if row["Budget"] > 0 or row["Category"] in budgets:
                    store.set_budget(row["Category"], row["Budget"])
            st.rerun()
        if c2.button("✨ Use suggested budgets", use_container_width=True):
            for cat, limit in suggested.items():
                if cat in cats_list and limit > 0:
                    store.set_budget(cat, limit)
            st.rerun()

        active = {c: l for c, l in store.budgets().items() if l > 0}
        if active:
            st.subheader("Progress")
            for cat, limit in sorted(active.items(), key=lambda kv: -spent.get(kv[0], 0) / kv[1]):
                used = spent.get(cat, 0.0)
                pct = used / limit
                icon = "🔴" if pct > 1 else "🟠" if pct > 0.85 else "🟢"
                st.progress(min(pct, 1.0), text=f"{icon} {cat}: {money(used)} of {money(limit)} ({pct:.0%})")

# ---------------------------------------------------------------- add / import
with tabs[5]:
    left, right = st.columns(2)
    with left:
        st.subheader("Add a transaction")
        with st.form("add", clear_on_submit=True):
            t_type = st.radio("Type", ["expense", "income"], horizontal=True)
            desc = st.text_input("Description", placeholder="e.g. Swiggy dinner, Electricity bill, Salary")
            amount = st.number_input(f"Amount ({CUR})", min_value=0.0, step=100.0)
            c1, c2 = st.columns(2)
            when = c1.date_input("Date", date.today())
            member = c2.text_input("Family member", "Family")
            cat_choice = st.selectbox("Category", ["🤖 Auto-detect (k-NN)"] + ALL_CATEGORIES)
            if st.form_submit_button("Add", type="primary"):
                if not desc.strip() or amount <= 0:
                    st.error("Enter a description and an amount above zero.")
                else:
                    if cat_choice.startswith("🤖"):
                        pred = knn.predict(desc, t_type)
                        category, source = pred["category"], "knn"
                        note = f" - k-NN confidence {pred['confidence']:.0%}"
                        if pred["needs_review"]:
                            note += ". ⚠️ Not sure: please check it in 📋 Transactions"
                    else:
                        category, source, note = cat_choice, "manual", ""
                    store.add_transaction(when, desc, amount, t_type, category, member or "Family", source)
                    st.session_state["flash"] = f"Added **{desc}** ({money(amount)}) as **{category}**{note}"
                    st.rerun()
        if msg := st.session_state.pop("flash", None):
            st.success(msg)

        with st.expander("🔎 See how k-NN decides"):
            probe = st.text_input("Try a description", "UPI/BLINKIT/7781")
            probe_type = st.radio("Type ", ["expense", "income"], horizontal=True, key="probe_type")
            if probe:
                pred = knn.predict(probe, probe_type)
                st.markdown(f"Prediction: **{pred['category']}** · confidence {pred['confidence']:.0%}"
                            + (" · ⚠️ needs review" if pred["needs_review"] else ""))
                st.dataframe(pd.DataFrame(pred["neighbours"], columns=["Nearest known description", "Category", "Similarity"]),
                             hide_index=True, use_container_width=True,
                             column_config={"Similarity": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1)})

    with right:
        st.subheader("Import a bank statement (CSV)")
        st.caption("Columns: `date`, `description`, `amount`. Optional: `type` (income/expense), `member`. "
                   "Without `type`, negative amounts are expenses and positive amounts are income.")
        file = st.file_uploader("CSV file", type="csv")
        if file is not None:
            try:
                raw = pd.read_csv(file)
                raw.columns = [c.strip().lower() for c in raw.columns]
                missing = {"date", "description", "amount"} - set(raw.columns)
                if missing:
                    raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
                raw["date"] = pd.to_datetime(raw["date"], dayfirst=True).dt.strftime("%Y-%m-%d")
                raw["amount"] = pd.to_numeric(raw["amount"])
                if "type" not in raw.columns:
                    raw["type"] = raw["amount"].apply(lambda a: "expense" if a < 0 else "income")
                raw["type"] = raw["type"].str.lower().str.strip()
                raw["amount"] = raw["amount"].abs()
                raw["member"] = raw.get("member", "Family")
                raw = raw[(raw["amount"] > 0) & raw["type"].isin(["income", "expense"])].reset_index(drop=True)
                preds = [knn.predict(d, t) for d, t in zip(raw["description"], raw["type"])]
                raw["category"] = [p["category"] for p in preds]
                raw["confidence"] = [p["confidence"] for p in preds]
                raw["source"] = "knn"
                st.dataframe(raw[["date", "description", "amount", "type", "category", "confidence"]], hide_index=True,
                             height=260, column_config={"confidence": st.column_config.ProgressColumn(
                                 format="%.2f", min_value=0, max_value=1)})
                unsure = sum(p["needs_review"] for p in preds)
                st.caption(f"{len(raw)} rows categorized by k-NN · {unsure} low-confidence (check them after import)")
                if st.button(f"Import {len(raw)} transactions", type="primary"):
                    store.add_many(raw[["date", "description", "amount", "type", "category", "member", "source"]]
                                   .to_dict(orient="records"))
                    st.session_state["flash"] = f"Imported {len(raw)} transactions."
                    st.rerun()
            except Exception as e:
                st.error(f"Couldn't read that file: {e}")

# ---------------------------------------------------------------- transactions
with tabs[6]:
    st.subheader("All transactions")
    if df.empty:
        st.info("Nothing here yet.")
    else:
        c1, c2, c3 = st.columns(3)
        f_month = c1.selectbox("Month", ["All"] + month_list, key="tx_month")
        f_cat = c2.selectbox("Category", ["All"] + sorted(df["category"].unique()), key="tx_cat")
        f_text = c3.text_input("Search description")
        view = df
        if f_month != "All":
            view = view[view["month"] == f_month]
        if f_cat != "All":
            view = view[view["category"] == f_cat]
        if f_text:
            view = view[view["description"].str.contains(f_text, case=False, regex=False)]
        view = view[["id", "date", "description", "amount", "type", "category", "necessity", "member", "source"]] \
            .reset_index(drop=True).assign(necessity=lambda d: d["necessity"].fillna(""))
        st.caption("Teach the models: fix a wrong **category** (k-NN learns it) or label an expense **Reasonable / "
                   "Unnecessary** (the decision tree learns it). Tick **Delete** to remove a row.")
        edited = st.data_editor(
            view.assign(delete=False), hide_index=True, use_container_width=True, height=480,
            disabled=["id", "date", "description", "amount", "type", "member", "source"],
            column_config={
                "date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "amount": st.column_config.NumberColumn(format=f"{CUR}%.0f"),
                "category": st.column_config.SelectboxColumn(options=ALL_CATEGORIES),
                "necessity": st.column_config.SelectboxColumn("My label", options=["", "Reasonable", "Unnecessary"]),
                "source": st.column_config.TextColumn(help="manual = you chose · knn = predicted · demo = sample data"),
                "delete": st.column_config.CheckboxColumn("Delete"),
            },
        )
        cat_changed = edited["category"] != view["category"]
        label_changed = edited["necessity"] != view["necessity"]
        changed = edited[cat_changed | label_changed | edited["delete"]]
        if len(changed) and st.button(f"Apply {len(changed)} change(s)", type="primary"):
            for i, row in changed.iterrows():
                if row["delete"]:
                    store.delete_transaction(int(row["id"]))
                    continue
                if cat_changed[i]:
                    store.update_category(int(row["id"]), row["category"], source="manual")
                if label_changed[i]:
                    store.set_necessity(int(row["id"]), row["necessity"])
            st.rerun()
        st.download_button("⬇️ Export CSV", view.to_csv(index=False), "transactions.csv", "text/csv")

# ---------------------------------------------------------------- models
with tabs[7]:
    st.subheader("🧠 The machine-learning models")
    st.caption("Every algorithm is implemented from scratch with NumPy in `budget/ml/`.")

    with st.container(border=True):
        st.markdown("### 1 · k-Nearest Neighbor - expense categorization")
        st.markdown("Each description becomes a TF-IDF vector of words and 3-letter chunks. A new expense gets "
                    "the category its *k* most similar known descriptions vote for, weighted by cosine similarity.")
        ev = knn_evaluation()
        c = st.columns(3)
        c[0].metric("Training examples", f"{knn.n_seed + knn.n_corrections:,}",
                    f"{knn.n_corrections} from your corrections", delta_color="off")
        c[1].metric("Accuracy · new phrasing of known merchants", f"{ev['unseen_phrasing'][5] * 100:.1f}%")
        c[2].metric("Accuracy · completely unseen merchants", f"{ev['unseen_merchant'][5] * 100:.1f}%")
        acc = pd.DataFrame({"k": list(ev["unseen_phrasing"]), "Known merchant, new phrasing": list(ev["unseen_phrasing"].values()),
                            "Unseen merchant": list(ev["unseen_merchant"].values())}).melt("k", var_name="Test", value_name="Accuracy")
        fig = px.line(acc, x="k", y="Accuracy", color="Test", markers=True)
        fig.update_layout(height=260, yaxis_tickformat=".0%", **CHART)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Unseen brand names are hard for any text model, which is why k-NN learns from every category you "
                   "correct: one correction and that merchant is known from then on.")

    if not df.empty:
        fc = forecaster.forecast(df, month_list[0], GOAL, one_off_ids)
        with st.container(border=True):
            st.markdown("### 2 · Locally Weighted Regression - predicting spending")
            st.markdown("For each category, LWR fits a straight line around next month, weighting recent months by "
                        "`w = exp(-(x - x_next)² / 2τ²)`. The bandwidth τ is chosen by back-testing on past months.")
            if fc and fc["tau_scores"]:
                bt = fc["backtest"]
                left, right = st.columns(2)
                with left:
                    fig = px.line(x=list(fc["tau_scores"]), y=list(fc["tau_scores"].values()), markers=True,
                                  labels={"x": "τ (bandwidth)", "y": f"Mean abs. error ({CUR})"})
                    fig.update_layout(height=260, title="Choosing τ", **CHART)
                    st.plotly_chart(fig, use_container_width=True)
                with right:
                    comp = pd.DataFrame({"Method": ["LWR", "Same as last month", "3-month average"],
                                         "MAE": [bt["lwr_mae"], bt["naive_mae"], bt["mean3_mae"]]})
                    fig = px.bar(comp, x="Method", y="MAE", text_auto=".0f")
                    fig.update_layout(height=260, title=f"Back-test error per category-month ({bt['tested_months']} months)",
                                      **CHART)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"Back-testing needs more than {forecaster.MIN_MONTHS} months of data.")

        with st.container(border=True):
            st.markdown("### 3 · ID3 Decision Tree - necessary vs unnecessary")
            feats = necessity.expense_features(df, store.budgets())
            tree = necessity.train_tree(feats)
            n_user = int(feats["necessity"].notna().sum()) if "necessity" in feats else 0
            c = st.columns(3)
            c[0].metric("Tree depth", tree.depth())
            c[1].metric("Rules", len(tree.rules()))
            c[2].metric("Your labels used", n_user, "each counts 3×", delta_color="off")
            root = tree.tree
            if "attribute" in root:
                st.markdown(f"Root split: **{root['attribute'].replace('_', ' ')}** (information gain {root['gain']:.3f} bits)")
            with st.expander("Show all learned rules"):
                st.code("\n".join(tree.rules()), language="text")

        if pattern_result:
            with st.container(border=True):
                st.markdown("### 4 · k-Means - spending patterns")
                st.markdown("Clusters expenses by amount, how often they occur and how regular they are. The SSE "
                            "(within-cluster spread) drops as *k* grows; the bend in the curve, the 'elbow', is a good *k*.")
                fig = px.line(x=pattern_result["elbow"]["k"], y=pattern_result["elbow"]["sse"], markers=True,
                              labels={"x": "k", "y": "SSE"})
                fig.update_layout(height=260, title="Elbow method", **CHART)
                st.plotly_chart(fig, use_container_width=True)

        anomaly = run_anomalies(df, month_list[0])
        if anomaly:
            with st.container(border=True):
                st.markdown("### 5 · Expectation-Maximization - unusual expenses")
                st.markdown("A 3-component Gaussian mixture learns what normal expenses look like. The E-step assigns each "
                            "expense to components softly and the M-step re-estimates the components. Expenses with very "
                            "low likelihood that are far above their category's usual amount are flagged.")
                left, right = st.columns(2)
                with left:
                    fig = px.line(y=anomaly["log_likelihood_history"], markers=True,
                                  labels={"x": "EM iteration", "y": "Log-likelihood"})
                    fig.update_layout(height=260, title=f"Convergence ({anomaly['iterations']} iterations)", **CHART)
                    st.plotly_chart(fig, use_container_width=True)
                with right:
                    fig = px.histogram(anomaly["all"], x="log_likelihood", nbins=40)
                    fig.add_vline(x=anomaly["threshold"], line_dash="dash", annotation_text="anomaly threshold")
                    fig.update_layout(height=260, title="Likelihood of every expense", **CHART)
                    st.plotly_chart(fig, use_container_width=True)

        with st.container(border=True):
            st.markdown("### 6 · Genetic Algorithm - savings plan")
            st.markdown("A population of 80 candidate plans (cut % per category) evolves for 150 generations through "
                        "tournament selection, blend crossover, Gaussian mutation and elitism. Fitness rewards reaching the "
                        "savings target and penalises painful cuts, with needs counting 4× wants.")
            history = st.session_state.get("ga_history")
            if history:
                fig = px.line(y=history, labels={"x": "Generation", "y": "Best fitness"})
                fig.update_layout(height=260, title="Best fitness per generation", **CHART)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Open **🔮 Predictions** with a savings target above the forecast to see the GA converge.")
