import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";

// HW4 Part 1.III: rendered on "/update". The record to edit is passed via
// React Router's navigation `state` (set by Home's "Update" button) rather
// than a URL param, per the spec's literal "/update route" + "accept props"
// wording. If someone lands here without that state (direct visit, hard
// refresh), there is nothing to edit, so redirect back to Home instead of
// showing a broken blank form.
export default function UpdateRecord({ user }) {
  const location = useLocation();
  const navigate = useNavigate();
  const record = location.state?.record ?? null;

  const [productName, setProductName] = useState(record?.product_name ?? "");
  const [brandName, setBrandName] = useState(record?.brand_name ?? "");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!record) {
      navigate("/", { replace: true });
    }
  }, [record, navigate]);

  if (!user) {
    return (
      <div className="page">
        <p className="notice">Login required to update a record.</p>
      </div>
    );
  }

  if (!record) {
    return null; // redirecting via the effect above
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.updateRecord(record.id, productName, brandName);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Update Recall Notice #{record.id}</h1>
      <form onSubmit={handleSubmit} className="form">
        <label>
          Product name
          <input
            type="text"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            required
          />
        </label>
        <label>
          Brand name
          <input
            type="text"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Saving..." : "Update Recall Notice"}
        </button>
      </form>
    </div>
  );
}
