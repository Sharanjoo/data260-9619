"use strict";

const form = document.getElementById("noticeForm");
const descriptionInput = document.getElementById("description");
const termsInput = document.getElementById("termsAccepted");
const characterCount = document.getElementById("characterCount");
const successMessage = document.getElementById("successMessage");

const NOTICES_API = "/api/notices";

const noticesLoading = document.getElementById("noticesLoading");
const noticesEmpty = document.getElementById("noticesEmpty");
const noticesError = document.getElementById("noticesError");
const noticesTable = document.getElementById("noticesTable");
const noticesTableBody = document.getElementById("noticesTableBody");
const retryNoticesBtn = document.getElementById("retryNotices");

const updateProductNameInput = document.getElementById("updateProductName");
const updateBrandNameInput = document.getElementById("updateBrandName");
const updateNoticeBtn = document.getElementById("updateNoticeBtn");
const deleteNoticeBtn = document.getElementById("deleteNoticeBtn");
const searchQueryInput = document.getElementById("searchQuery");
const searchNoticeBtn = document.getElementById("searchNoticeBtn");
const clearSearchBtn = document.getElementById("clearSearchBtn");

// Closure: count is private and survives between successful submissions.
const submissionCounter = (() => {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
})();

// Required arrow function validation for the content and terms fields.
const validateForm = () => {
  if (descriptionInput.value.trim().length <= 25) {
    alert("The notice description must contain more than 25 characters.");
    descriptionInput.focus();
    return false;
  }
  if (!termsInput.checked) {
    alert("You must agree to the terms and conditions before submitting.");
    termsInput.focus();
    return false;
  }
  if (!form.checkValidity()) {
    form.reportValidity();
    return false;
  }
  return true;
};

descriptionInput.addEventListener("input", () => {
  characterCount.textContent = String(descriptionInput.value.length);
});

// ---- Notices list: loading / empty / error / data states ----

function showNoticesState(state) {
  noticesLoading.hidden = state !== "loading";
  noticesEmpty.hidden = state !== "empty";
  noticesError.hidden = state !== "error";
  noticesTable.hidden = state !== "data";
}

function renderNotices(list) {
  noticesTableBody.innerHTML = "";
  list.forEach((notice) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${notice.id}</td>
      <td>${notice.productName}</td>
      <td>${notice.brandName}</td>
      <td>${notice.category ?? ""}</td>
    `;
    noticesTableBody.appendChild(row);
  });
}

async function loadNotices(query = "") {
  showNoticesState("loading");
  await new Promise(resolve => setTimeout(resolve, 3000)); 
  try {
    const url = query
      ? `${NOTICES_API}?q=${encodeURIComponent(query)}`
      : NOTICES_API;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const list = await response.json();
    if (!Array.isArray(list) || list.length === 0) {
      showNoticesState("empty");
      return;
    }
    renderNotices(list);
    showNoticesState("data");
  } catch (error) {
    console.error("Error loading notices:", error);
    showNoticesState("error");
  }
}

retryNoticesBtn.addEventListener("click", () => {
  loadNotices(searchQueryInput.value.trim());
});

searchNoticeBtn.addEventListener("click", () => {
  loadNotices(searchQueryInput.value.trim());
});

clearSearchBtn.addEventListener("click", () => {
  searchQueryInput.value = "";
  loadNotices();
});

updateNoticeBtn.addEventListener("click", async () => {
  const productName = updateProductNameInput.value.trim();
  const brandName = updateBrandNameInput.value.trim();
  if (!productName || !brandName) {
    alert("Enter both a product name and a brand or supplier to update notice ID 1.");
    return;
  }
  try {
    const response = await fetch(`${NOTICES_API}/1`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ productName, brandName }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to update notice");
    }
    const updated = await response.json();
    console.log("Updated notice:", updated);
    updateProductNameInput.value = "";
    updateBrandNameInput.value = "";
    await loadNotices();
    alert(`Notice ID 1 updated to "${updated.productName}".`);
  } catch (error) {
    console.error("Error updating notice:", error);
    alert("Failed to update notice: " + error.message);
  }
});

deleteNoticeBtn.addEventListener("click", async () => {
  if (!confirm("Delete the recall notice with the highest ID?")) {
    return;
  }
  try {
    const response = await fetch(`${NOTICES_API}/highest`, { method: "DELETE" });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to delete notice");
    }
    const deleted = await response.json();
    console.log("Deleted highest-ID notice:", deleted);
    await loadNotices();
    alert(`Deleted notice ID ${deleted.id} ("${deleted.productName}").`);
  } catch (error) {
    console.error("Error deleting notice:", error);
    alert("Failed to delete notice: " + error.message);
  }
});

// ---- Form submission: validate, persist to the API, refresh the list ----

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  successMessage.hidden = true;

  if (!validateForm()) {
    return;
  }

  const formData = Object.fromEntries(new FormData(form).entries());
  formData.termsAccepted = termsInput.checked;

  // Convert successful form data to a JSON string and log it.
  const jsonString = JSON.stringify(formData);
  console.log("Form data JSON string:", jsonString);
  const parsedNotice = JSON.parse(jsonString);

  // Object destructuring: extract the primary field and submitter email.
  const { productName, submitterEmail } = parsedNotice;
  console.log("Primary field (productName):", productName);
  console.log("Submitter email:", submitterEmail);

  // Spread operator: copy the parsed object and add an ISO timestamp.
  const datedNotice = {
    ...parsedNotice,
    submissionDate: new Date().toISOString(),
  };
  console.log("Updated notice object:", datedNotice);

  try {
    const response = await fetch(NOTICES_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datedNotice),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to save notice");
    }
    const savedNotice = await response.json();
    console.log("Saved notice (from server):", savedNotice);

    const successfulSubmissions = submissionCounter();
    console.log("Successful submission count:", successfulSubmissions);

    successMessage.hidden = false;
    form.reset();
    characterCount.textContent = "0";
    document.getElementById("productName").focus();
    await loadNotices();
  } catch (error) {
    console.error("Error saving notice:", error);
    alert("Failed to submit notice: " + error.message);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  loadNotices();
});