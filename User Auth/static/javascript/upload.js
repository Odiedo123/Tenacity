// -------- Toast ---------------------------------------------------------- //
function showToast(message, type = "info") {
  const toastContainer = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;

  toastContainer.appendChild(toast);

  // Remove the toast after the animation ends
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

// -------- Uploading ---------------------------------------------------------- //

// Get references to the elements
const dropArea = document.getElementById("drop-area");
const fileInput = document.getElementById("file-input");
const fileList = document.getElementById("file-list");
const uploadButton = document.getElementById("upload-button");
let files = []; // To store the files
const fileHashes = new Set(); // To track unique file hashes
const MAX_TOTAL_STORAGE = 20 * 1024 * 1024 * 1024; // 20GB total storage limit
let totalUploadedSize = 0; // Tracks total uploaded size

// Prevent default drag behaviors
["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
  dropArea.addEventListener(eventName, (e) => e.preventDefault());
  dropArea.addEventListener(eventName, (e) => e.stopPropagation());
});

// Highlight the drop area on drag events
["dragenter", "dragover"].forEach((eventName) => {
  dropArea.addEventListener(eventName, () =>
    dropArea.classList.add("highlight")
  );
});

["dragleave", "drop"].forEach((eventName) => {
  dropArea.addEventListener(eventName, () =>
    dropArea.classList.remove("highlight")
  );
});

// Handle file drop
dropArea.addEventListener("drop", (e) => {
  const droppedFiles = Array.from(e.dataTransfer.files);
  handleFiles(droppedFiles);
});

// Handle file browsing
document
  .getElementById("file-browser-trigger")
  .addEventListener("click", () => {
    fileInput.value = ""; // Clear the input to avoid duplication
    fileInput.click();
  });

fileInput.addEventListener("change", async () => {
  const selectedFiles = Array.from(fileInput.files);
  await handleFiles(selectedFiles);
});

// Function to calculate file hash using FileReader
function calculateFileHash(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    const crypto = window.crypto || window.msCrypto;

    reader.onload = (event) => {
      const buffer = event.target.result;
      const hash = crypto.subtle.digest("SHA-256", buffer);
      hash.then((hashBuffer) => {
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        resolve(hashHex);
      });
    };

    reader.onerror = () => reject(reader.error);

    reader.readAsArrayBuffer(file);
  });
}

// Function to handle files
async function handleFiles(newFiles) {
  for (const file of newFiles) {
    const hash = await calculateFileHash(file);

    if (fileHashes.has(hash)) {
      showToast(`Duplicate detected: ${file.name} ignored`, "warning");
    } else {
      fileHashes.add(hash); // Add unique file hash
      files.push(file); // Add file to the list
    }
  }
  renderFileList();
}

// Render file list
function renderFileList() {
  fileList.innerHTML = ""; // Clear existing list
  files.forEach((file, index) => {
    const listItem = document.createElement("li");
    listItem.textContent = file.name;

    // Add a remove button
    const removeButton = document.createElement("span");
    removeButton.textContent = " Remove";
    removeButton.style.color = "red";
    removeButton.style.cursor = "pointer";
    removeButton.style.display = "block";
    removeButton.addEventListener("click", () => {
      files.splice(index, 1);
      renderFileList();
    });

    listItem.appendChild(removeButton);
    fileList.appendChild(listItem);
  });
}

// Upload files to the backend
uploadButton.addEventListener("click", async () => {
  if (files.length === 0) {
    showToast("No files to upload!");
    return;
  }

  const currentUploadSize = files.reduce((sum, file) => sum + file.size, 0);
  const projectedTotalSize = totalUploadedSize + currentUploadSize;

  // Check if the projected total size exceeds the limit
  if (projectedTotalSize > MAX_TOTAL_STORAGE) {
    showToast("Uploading Files .....");
    showToast(`Total storage will exceed 20GB! Upload not allowed.`, "error");
    return;
  }

  // Disable upload button to prevent duplicate uploads
  uploadButton.disabled = true;

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file)); // Use "files" as the field name
  showToast("Uploading Files .....");
  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    if (response.ok) {
      const result = await response.json();
      showToast("Files uploaded successfully!");
      console.log("Upload response:", result);

      // Update total uploaded size after a successful upload
      totalUploadedSize += currentUploadSize;

      // Clear both files and fileHashes after successful upload
      files = [];
      fileHashes.clear();
      renderFileList(); // Update UI
    } else {
      showToast("Failed to upload files.");
      console.error("Upload error:", await response.text());
    }
  } catch (error) {
    showToast("An error occurred while uploading files.");
    console.error("Error:", error);
  } finally {
    // Re-enable the upload button after processing
    uploadButton.disabled = false;
  }
});
