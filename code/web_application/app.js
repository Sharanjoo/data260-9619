"use strict";

const form = document.getElementById("noticeForm");
const descriptionInput = document.getElementById("description");
const termsInput = document.getElementById("termsAccepted");
const characterCount = document.getElementById("characterCount");
const successMessage = document.getElementById("successMessage");

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

form.addEventListener("submit", (event) => {
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

  const successfulSubmissions = submissionCounter();
  console.log("Successful submission count:", successfulSubmissions);

  successMessage.hidden = false;
  form.reset();
  characterCount.textContent = "0";
  document.getElementById("productName").focus();
});
