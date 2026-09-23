import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

// HW4 Part 1.II: rendered on "/create". Adds a new recall record (auto-
// incremented id comes from MySQL) and redirects to Home on success.
export default function CreateRecord({ user }) {
  const [productName, setProductName] = useState("");
  const [brandName, setBrandName] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
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
      await api.createRecord(productName, brandName);
      navigate("/");
    } catch (err) {
      setError(err.message);
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
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Adding..." : "Add Recall Notice"}
        </button>
      </form>
    </div>
  );
}
