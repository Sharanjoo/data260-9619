import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useDispatch } from "react-redux";
import { fetchRecordById, updateRecord } from "../recordsSlice";

// HW5 Part 1.III Update screen: "a form to update an existing record
// (select by ID)". The user types a record ID and clicks "Load record" (the
// fetchRecordById thunk calls GET /records/{id}); the edit form is then filled
// from that record. If the page was reached through Home's "Update" button,
// the record is passed via React Router navigation `state` (the HW4 "accept
// props" requirement), so its ID is pre-filled and loaded automatically.
//
// Submitting dispatches the updateRecord thunk; record_code is shown
// read-only since it's a server-assigned unique identifier.
export default function UpdateRecord({ user }) {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const routedRecord = location.state?.record ?? null;

  const [idInput, setIdInput] = useState(routedRecord ? String(routedRecord.id) : "");
  const [record, setRecord] = useState(routedRecord);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const [productName, setProductName] = useState(routedRecord?.product_name ?? "");
  const [brandName, setBrandName] = useState(routedRecord?.brand_name ?? "");
  const [unitsAffected, setUnitsAffected] = useState(
    String(routedRecord?.units_affected ?? 0)
  );
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Whenever a different record is loaded, refill the form fields from it.
  useEffect(() => {
    if (record) {
      setProductName(record.product_name ?? "");
      setBrandName(record.brand_name ?? "");
      setUnitsAffected(String(record.units_affected ?? 0));
    }
  }, [record]);

  if (!user) {
    return (
      <div className="page">
        <p className="notice">Login required to update a record.</p>
      </div>
    );
  }

  async function handleLoad(e) {
    e.preventDefault();
    setLoadError(null);
    setError(null);
    const id = Number(idInput);
    if (!Number.isInteger(id) || id <= 0) {
      setRecord(null);
      setLoadError("Enter a valid record ID (a positive whole number).");
      return;
    }
    setLoading(true);
    try {
      const found = await dispatch(fetchRecordById(id)).unwrap();
      setRecord(found);
    } catch (err) {
      setRecord(null);
      setLoadError(typeof err === "string" ? err : "Could not load that record");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await dispatch(
        updateRecord({
          id: record.id,
          productName,
          brandName,
          unitsAffected: Number(unitsAffected) || 0,
        })
      ).unwrap();
      navigate("/");
    } catch (err) {
      setError(typeof err === "string" ? err : "Failed to update record");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page">
      <h1>Update Recall Notice</h1>

      <form onSubmit={handleLoad} className="form">
        <label>
          Record ID
          <input
            type="number"
            min="1"
            value={idInput}
            onChange={(e) => setIdInput(e.target.value)}
            placeholder="e.g. 15007"
            required
          />
        </label>
        {loadError && <p className="error">{loadError}</p>}
        <button type="submit" disabled={loading}>
          {loading ? "Loading..." : "Load record"}
        </button>
      </form>

      {record && (
        <>
          <h2>Editing #{record.id}</h2>
          {record.record_code && (
            <p className="notice">Code: {record.record_code}</p>
          )}
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
              {submitting ? "Saving..." : "Update Recall Notice"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
