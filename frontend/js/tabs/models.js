// 🧠 Models: how each algorithm works, with evaluation charts.

import { api } from "../api.js";
import { alertBox, esc, metric, plot, state } from "../ui.js";

let data = null;

export async function render(node) {
  data = await api.get("/api/models");
  const d = data;
  const k = d.knn;
  const sections = [];

  sections.push(`<div class="card">
    <h3>1 · k-Nearest Neighbor: expense categorization</h3>
    <p>Each description becomes a TF-IDF vector of words and 3-letter chunks. A new expense gets the category its
      <i>k</i> most similar known descriptions vote for, weighted by cosine similarity.</p>
    <div class="grid cols-3">
      ${metric("Training examples", k.training_examples.toLocaleString(), `${k.corrections} from your corrections`)}
      ${metric("Accuracy · new phrasing of known merchants", `${(k.accuracy_phrasing * 100).toFixed(1)}%`)}
      ${metric("Accuracy · completely unseen merchants", `${(k.accuracy_merchant * 100).toFixed(1)}%`)}
    </div>
    <div id="chart-knn" class="chart h260"></div>
    <p class="muted">Unseen brand names are hard for any text model, which is why k-NN learns from every category you
      correct: one correction and that merchant is known from then on.</p>
  </div>`);

  if (!state.meta.months.length) {
    sections.push(alertBox("info", `The other models need data. Add transactions in <a href="#add">➕ Add / Import</a>,
      or load the demo family from the sidebar.`));
  } else {
    sections.push(`<div class="card">
      <h3>2 · Locally Weighted Regression: predicting spending</h3>
      <p>For each category, LWR fits a straight line around next month, weighting recent months by
        <code>w = exp(-(x - x_next)² / 2τ²)</code>. The bandwidth τ is chosen by back-testing on past months.</p>
      ${d.lwr?.tau_scores.length
        ? `<div class="grid cols-2"><div id="chart-tau" class="chart h260"></div><div id="chart-bt" class="chart h260"></div></div>`
        : alertBox("info", `Back-testing needs more than ${d.lwr?.min_months ?? 3} months of data.`)}
    </div>`);

    const t = d.id3;
    sections.push(`<div class="card">
      <h3>3 · ID3 Decision Tree: necessary vs unnecessary</h3>
      <div class="grid cols-3">
        ${metric("Tree depth", t.depth)}
        ${metric("Rules", t.rules.length)}
        ${metric("Your labels used", t.user_labels, `each counts ${t.user_label_weight}×`)}
      </div>
      ${t.root ? `<p class="mt">Root split: <b>${esc(t.root.attribute.replaceAll("_", " "))}</b>
        (information gain ${t.root.gain.toFixed(3)} bits)</p>` : ""}
      <details class="panel"><summary>Show all learned rules</summary>
        <pre class="rules">${esc(t.rules.join("\n"))}</pre></details>
    </div>`);

    if (d.kmeans) {
      sections.push(`<div class="card">
        <h3>4 · k-Means: spending patterns</h3>
        <p>Clusters expenses by amount, how often they occur and how regular they are. The SSE (within-cluster spread)
          drops as <i>k</i> grows; the bend in the curve, the "elbow", is a good <i>k</i>.</p>
        <div id="chart-elbow" class="chart h260"></div>
      </div>`);
    }

    if (d.em) {
      sections.push(`<div class="card">
        <h3>5 · Expectation-Maximization: unusual expenses</h3>
        <p>A 3-component Gaussian mixture learns what normal expenses look like. The E-step assigns each expense to
          components softly and the M-step re-estimates the components. Expenses with very low likelihood that are far
          above their category's usual amount are flagged.</p>
        <div class="grid cols-2"><div id="chart-em" class="chart h260"></div><div id="chart-ll" class="chart h260"></div></div>
      </div>`);
    }

    sections.push(`<div class="card">
      <h3>6 · Genetic Algorithm: savings plan</h3>
      <p>A population of 80 candidate plans (cut % per category) evolves for 150 generations through tournament
        selection, blend crossover, Gaussian mutation and elitism. Fitness rewards reaching the savings target and
        penalises painful cuts, with needs counting 4× wants.</p>
      ${d.ga?.history.length
        ? `<p class="muted">Run for the latest month with a ${d.ga.target}% target.</p><div id="chart-ga" class="chart h260"></div>`
        : `<p class="muted">The latest forecast already meets the target, so the GA had nothing to optimise.</p>`}
    </div>`);
  }

  node.innerHTML = `<h2>🧠 The machine-learning models</h2>
    <p class="muted">Every algorithm is implemented from scratch with NumPy in <code>budget/ml/</code>.</p>
    <div class="stack">${sections.join("")}</div>`;
}

export function mounted() {
  const d = data;
  const small = { margin: { t: 40, b: 45, l: 60, r: 20 } };
  const curve = d.knn.curve;
  plot("chart-knn", [
    { type: "scatter", mode: "lines+markers", name: "Known merchant, new phrasing", x: curve.map((c) => c.k), y: curve.map((c) => c.phrasing) },
    { type: "scatter", mode: "lines+markers", name: "Unseen merchant", x: curve.map((c) => c.k), y: curve.map((c) => c.merchant) },
  ], { ...small, xaxis: { title: { text: "k" } }, yaxis: { tickformat: ".0%", title: { text: "Accuracy" } } });

  if (d.lwr?.tau_scores.length) {
    plot("chart-tau", [{ type: "scatter", mode: "lines+markers", x: d.lwr.tau_scores.map((t) => t.tau),
      y: d.lwr.tau_scores.map((t) => t.mae) }],
      { ...small, title: { text: "Choosing τ" }, xaxis: { title: { text: "τ (bandwidth)" } },
        yaxis: { title: { text: `Mean abs. error (${state.meta.settings.currency})` } } });
    const bt = d.lwr.backtest;
    const vals = [bt.lwr_mae, bt.naive_mae, bt.mean3_mae];
    plot("chart-bt", [{ type: "bar", x: ["LWR", "Same as last month", "3-month average"], y: vals,
      text: vals.map((v) => v.toFixed(0)), textposition: "auto" }],
      { ...small, title: { text: `Back-test error per category-month (${bt.tested_months} months)` },
        yaxis: { title: { text: "MAE" } } });
  }

  if (d.kmeans) {
    plot("chart-elbow", [{ type: "scatter", mode: "lines+markers", x: d.kmeans.elbow.map((e) => e.k),
      y: d.kmeans.elbow.map((e) => e.sse) }],
      { ...small, title: { text: "Elbow method" }, xaxis: { title: { text: "k" } }, yaxis: { title: { text: "SSE" } } });
  }

  if (d.em) {
    plot("chart-em", [{ type: "scatter", mode: "lines+markers", y: d.em.log_likelihood_history }],
      { ...small, title: { text: `Convergence (${d.em.iterations} iterations)` },
        xaxis: { title: { text: "EM iteration" } }, yaxis: { title: { text: "Log-likelihood" } } });
    plot("chart-ll", [{ type: "histogram", x: d.em.log_likelihoods, nbinsx: 40 }], {
      ...small, title: { text: "Likelihood of every expense" }, xaxis: { title: { text: "log-likelihood" } },
      shapes: [{ type: "line", x0: d.em.threshold, x1: d.em.threshold, yref: "paper", y0: 0, y1: 1,
                 line: { dash: "dash", color: "#e8705f" } }],
      annotations: [{ x: d.em.threshold, yref: "paper", y: 1, text: "anomaly threshold", showarrow: false,
                      xanchor: "left", font: { color: "#e8705f" } }],
    });
  }

  if (d.ga?.history.length) {
    plot("chart-ga", [{ type: "scatter", mode: "lines", y: d.ga.history }],
      { ...small, title: { text: "Best fitness per generation" }, xaxis: { title: { text: "Generation" } },
        yaxis: { title: { text: "Best fitness" } } });
  }
}
