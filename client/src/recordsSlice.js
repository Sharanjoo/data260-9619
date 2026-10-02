// HW5 Part 1.III: Redux Toolkit slice for the primary domain entity
// (recall_record). Replaces the per-component useState/useEffect data
// fetching from HW4's Home.jsx with centralized Redux state, fed by async
// thunks that call code/db_routes.py's /api/hw4/records* endpoints via axios
// (not the fetch-based api.js wrapper -- the spec asks for axios here
// specifically). Auth/session state is NOT migrated: App.jsx's local
// `user` useState stays as-is, since this step only covers "your data
// layer" for the primary entity, not authentication.
import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import axios from "axios";

const API_BASE = "http://localhost:8619";

// Every call needs withCredentials: true (axios's equivalent of fetch's
// credentials: "include") so the hw4_session cookie is sent/stored on these
// cross-origin requests -- same reason api.js needed credentials: "include".
function errorDetail(err) {
  return err.response?.data?.detail || err.message || "Request failed";
}

export const fetchRecords = createAsyncThunk(
  "records/fetchRecords",
  async (limit = 50, { rejectWithValue }) => {
    try {
      // /records-fixed, not /records -- same N+1-avoidance reasoning as
      // api.js's HW4 listRecords().
      const res = await axios.get(`${API_BASE}/api/hw4/records-fixed`, {
        params: { limit },
        withCredentials: true,
      });
      return res.data;
    } catch (err) {
      return rejectWithValue(errorDetail(err));
    }
  }
);

export const createRecord = createAsyncThunk(
  "records/createRecord",
  async ({ productName, brandName, unitsAffected, sourceId }, { rejectWithValue }) => {
    try {
      const res = await axios.post(
        `${API_BASE}/api/hw4/records`,
        {
          product_name: productName,
          brand_name: brandName,
          units_affected: unitsAffected,
          source_id: sourceId ?? null,
        },
        { withCredentials: true }
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(errorDetail(err));
    }
  }
);

export const updateRecord = createAsyncThunk(
  "records/updateRecord",
  async ({ id, productName, brandName, unitsAffected }, { rejectWithValue }) => {
    try {
      const res = await axios.put(
        `${API_BASE}/api/hw4/records/${id}`,
        {
          product_name: productName,
          brand_name: brandName,
          units_affected: unitsAffected,
        },
        { withCredentials: true }
      );
      return res.data;
    } catch (err) {
      return rejectWithValue(errorDetail(err));
    }
  }
);

export const deleteRecord = createAsyncThunk(
  "records/deleteRecord",
  async (id, { rejectWithValue }) => {
    try {
      await axios.delete(`${API_BASE}/api/hw4/records/${id}`, { withCredentials: true });
      return id;
    } catch (err) {
      return rejectWithValue(errorDetail(err));
    }
  }
);

const recordsSlice = createSlice({
  name: "records",
  initialState: {
    items: [],
    status: "idle", // idle | loading | succeeded | failed
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchRecords.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchRecords.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchRecords.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload;
      })
      .addCase(createRecord.fulfilled, (state, action) => {
        state.items.push(action.payload);
      })
      .addCase(createRecord.rejected, (state, action) => {
        state.error = action.payload;
      })
      .addCase(updateRecord.fulfilled, (state, action) => {
        const idx = state.items.findIndex((r) => r.id === action.payload.id);
        if (idx !== -1) state.items[idx] = action.payload;
      })
      .addCase(updateRecord.rejected, (state, action) => {
        state.error = action.payload;
      })
      .addCase(deleteRecord.fulfilled, (state, action) => {
        state.items = state.items.filter((r) => r.id !== action.payload);
      })
      .addCase(deleteRecord.rejected, (state, action) => {
        state.error = action.payload;
      });
  },
});

export default recordsSlice.reducer;
