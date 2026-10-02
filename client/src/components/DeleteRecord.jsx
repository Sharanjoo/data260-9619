import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { deleteRecord } from "../recordsSlice";

// HW4 Part 1.IV / HW5 Part 1.III: rendered on "/delete". Same state-passing
// approach as UpdateRecord -- the record comes from location.state, set by
// Home's "Delete" button; redirect to Home if that state is missing.
//
// Dispatches the deleteRecord thunk instead of calling api.deleteRecord()
// directly. If the backend returns 409 (record still referenced, or any
// other delete-protection conflict), .unwrap() rethrows that detail string
// and it's shown inline instead of silently failing.
export default function DeleteRecord({ user }) {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useDispatch();
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
      await dispatch(deleteRecord(record.id)).unwrap();
      navigate("/");
    } catch (err) {
      setError(typeof err === "string" ? err : "Failed to delete record");
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
