import { useEffect, useState } from "react";

import {
  getBusinessContext,
  addMetric,
  deleteMetric,
  addSynonym,
  deleteSynonym,
  addBusinessRule,
  deleteBusinessRule,
} from "../../services/api";

function ContextPanel({ datasetId }) {
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(true);

  const [metricForm, setMetricForm] = useState({ name: "", column: "", aggregation: "sum" });
  const [synonymForm, setSynonymForm] = useState({ alias: "", canonical: "" });
  const [ruleText, setRuleText] = useState("");

  const refresh = () => getBusinessContext(datasetId).then(setContext);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  if (loading) return <div className="panel-loading">Loading business context…</div>;
  if (!context) return null;

  return (
    <div className="context-panel">
      <section>
        <div className="sidebar-label">Metric definitions</div>
        <p className="context-hint">Map a business term to a real column, e.g. "revenue" = sum(Sales).</p>

        <div className="context-list">
          {Object.entries(context.metrics).map(([name, spec]) => (
            <div key={name} className="context-row">
              <span><strong>{name}</strong> = {spec.aggregation}({spec.column})</span>
              <button onClick={() => deleteMetric(datasetId, name).then(refresh)}>Remove</button>
            </div>
          ))}
        </div>

        <form
          className="context-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!metricForm.name || !metricForm.column) return;
            addMetric(datasetId, metricForm).then(() => {
              setMetricForm({ name: "", column: "", aggregation: "sum" });
              refresh();
            });
          }}
        >
          <input placeholder="metric name (e.g. revenue)" value={metricForm.name}
            onChange={(e) => setMetricForm({ ...metricForm, name: e.target.value })} />
          <input placeholder="column name" value={metricForm.column}
            onChange={(e) => setMetricForm({ ...metricForm, column: e.target.value })} />
          <select value={metricForm.aggregation}
            onChange={(e) => setMetricForm({ ...metricForm, aggregation: e.target.value })}>
            <option value="sum">sum</option>
            <option value="mean">mean</option>
            <option value="count">count</option>
            <option value="min">min</option>
            <option value="max">max</option>
          </select>
          <button type="submit">Add</button>
        </form>
      </section>

      <section>
        <div className="sidebar-label">Synonyms</div>
        <p className="context-hint">e.g. "turnover" means "revenue" (or a raw column name).</p>

        <div className="context-list">
          {Object.entries(context.synonyms).map(([alias, canonical]) => (
            <div key={alias} className="context-row">
              <span>"{alias}" → {canonical}</span>
              <button onClick={() => deleteSynonym(datasetId, alias).then(refresh)}>Remove</button>
            </div>
          ))}
        </div>

        <form
          className="context-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!synonymForm.alias || !synonymForm.canonical) return;
            addSynonym(datasetId, synonymForm.alias, synonymForm.canonical).then(() => {
              setSynonymForm({ alias: "", canonical: "" });
              refresh();
            });
          }}
        >
          <input placeholder="alias (e.g. turnover)" value={synonymForm.alias}
            onChange={(e) => setSynonymForm({ ...synonymForm, alias: e.target.value })} />
          <input placeholder="means (e.g. revenue)" value={synonymForm.canonical}
            onChange={(e) => setSynonymForm({ ...synonymForm, canonical: e.target.value })} />
          <button type="submit">Add</button>
        </form>
      </section>

      <section>
        <div className="sidebar-label">Business rules</div>
        <p className="context-hint">Free-text context the agent should account for.</p>

        <div className="context-list">
          {context.rules.map((rule, i) => (
            <div key={i} className="context-row">
              <span>{rule}</span>
              <button onClick={() => deleteBusinessRule(datasetId, i).then(refresh)}>Remove</button>
            </div>
          ))}
        </div>

        <form
          className="context-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ruleText.trim()) return;
            addBusinessRule(datasetId, ruleText.trim()).then(() => {
              setRuleText("");
              refresh();
            });
          }}
        >
          <input placeholder="e.g. Fiscal year starts in April" value={ruleText}
            onChange={(e) => setRuleText(e.target.value)} style={{ flex: 1 }} />
          <button type="submit">Add</button>
        </form>
      </section>
    </div>
  );
}

export default ContextPanel;
