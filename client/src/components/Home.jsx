import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

// HW4 Part 1.I: Home page. Rendered on "/". Lists all recall records when
// logged in; shows "Login required" and hides the Add-Record action when not.
export default function Home({ user }) {
  const [records, setRecords] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) {
      setRecords([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .listRecords()
      .then((data) => {
        if (!cancelled) setRecords(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  if (!user) {
    return (
      <div className="page">
        <h1>Grocery Recall Notices</h1>
        <p className="notice">
          Login required. <Link to="/login">Log in</Link> to view and manage
          recall records.
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Grocery Recall Notices</h1>
        <Link to="/create" className="button-link">
          Add Record
        </Link>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && records.length === 0 && (
        <p>No recall records yet.</p>
      )}

      {records.length > 0 && (
        <table className="records-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Product name</th>
              <th>Brand name</th>
              <th>Source</th>
              <th>Region</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.id}</td>
                <td>{record.product_name}</td>
                <td>{record.brand_name}</td>
                <td>{record.source_name ?? "-"}</td>
                <td>{record.source_region ?? "-"}</td>
                <td className="row-actions">
                  <button
                    type="button"
                    onClick={() => navigate("/update", { state: { record } })}
                  >
                    Update
                  </button>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => navigate("/delete", { state: { record } })}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
