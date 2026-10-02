import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { createRecord } from "../recordsSlice";

// HW4 Part 1.II / HW5 Part 1.III: rendered on "/create". Adds a new recall
// record (auto-incremented id, and now an auto-generated record_code, come
// from the backend) and redirects to Home on success.
//
// Dispatches the createRecord thunk instead of calling api.createRecord()
// directly. .unwrap() rethrows the thunk's rejectWithValue payload (a
// string, built in recordsSlice.js from the axios error) so the existing
// try/catch here still works the same way it did against api.js.
export default function CreateRecord({ user }) {
  const [productName, setProductName] = useState("");
  const [brandName, setBrandName] = useState("");
  const [unitsAffected, setUnitsAffected] = useState("0");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const dispatch = useDispatch();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div className="page">
        <p className="notice">Login required to add a record.</p>
      </div>
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await dispatch(
        createRecord({
          productName,
          brandName,
          unitsAffected: Number(unitsAffected) || 0,
        })
      ).unwrap();
      navigate("/");
    } catch (err) {
      setError(typeof err === "string" ? err : "Failed to add record");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Add Recall Notice</h1>
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
        <label>
          Units affected
          <input
            type="number"
            min="0"
            value={unitsAffected}
            onChange={(e) => setUnitsAffected(e.target.value)}
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Adding..." : "Add Recall Notice"}
        </button>
      </form>
    </div>
  );
}
