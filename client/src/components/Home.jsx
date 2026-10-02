import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";
import { fetchRecords } from "../recordsSlice";

// HW4 Part 1.I / HW5 Part 1.III: Home page. Rendered on "/". Lists all
// recall records when logged in; shows "Login required" and hides the
// Add-Record action when not.
//
// Data now comes from the Redux `records` slice (recordsSlice.js) instead
// of local useState + api.listRecords() -- fetchRecords() dispatches the
// axios call to /api/hw4/records-fixed and the slice's extraReducers store
// the result. Auth (`user`) stays a local prop from App.jsx, unmigrated.
export default function Home({ user }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { items: records, status, error } = useSelector((state) => state.records);
  const loading = status === "loading";

  useEffect(() => {
    if (!user) return;
    dispatch(fetchRecords());
  }, [user, dispatch]);

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
              <th>Code</th>
              <th>Product name</th>
              <th>Brand name</th>
              <th>Units Affected</th>
              <th>Source</th>
              <th>Region</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.id}>
                <td>{record.id}</td>
                <td>{record.record_code ?? "-"}</td>
                <td>{record.product_name}</td>
                <td>{record.brand_name}</td>
                <td>{record.units_affected ?? 0}</td>
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
