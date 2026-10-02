// HW5 Part 1.III: Redux store. Single "records" slice for the primary
// domain entity (recall_record) -- auth/session stays local useState in
// App.jsx per the migration scope noted in recordsSlice.js.
import { configureStore } from "@reduxjs/toolkit";
import recordsReducer from "./recordsSlice";

export const store = configureStore({
  reducer: {
    records: recordsReducer,
  },
});
