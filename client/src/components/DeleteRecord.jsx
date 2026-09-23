import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";

// HW4 Part 1.IV: rendered on "/delete". Same state-passing approach as
// UpdateRecord -- the record comes from location.state, set by Home's
// "Delete" button; redirect to Home if that state is missing.
export default function DeleteRecord({ user }) {
  const location = useLocation();
  const navigate = useNavigate();
  const record = location.state?.record ?? null;

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
        <p className="notice">Login required to delete a record.</p>
      </div>
    );
  }

  if (!record) {
    return null; // redirecting via the effect above
  }

  async function handleDelete() {
    setError(null);
    setSubmitting(true);
    try {
      await api.deleteRecord(record.id);
      navigate("/");
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Delete Recall Notice #{record.id}</h1>
      <p>
        Product: <strong>{record.product_name}</strong>
        <br />
        Brand: <strong>{record.brand_name}</strong>
      </p>
      {error && <p className="error">{error}</p>}
      <div className="form">
        <button type="button" className="danger" onClick={handleDelete} disabled={submitting}>
          {submitting ? "Deleting..." : "Delete"}
        </button>
        <button type="button" onClick={() => navigate("/")} disabled={submitting}>
          Cancel
        </button>
      </div>
    </div>
  );
}
