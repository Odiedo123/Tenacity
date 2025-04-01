// Show toast messages
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

// Function to check if the table has any files and update the visibility of elements
function toggleFilePrompt() {
  const fileTableBody = document.querySelector("#file-list tbody");
  const hiddenPrompt = document.getElementById("hidden-prompt");
  const tableContainer = document.querySelector(".table-container");

  // Check if there are any rows in the table body
  if (fileTableBody.rows.length === 0) {
    // No files, show the hidden prompt and hide the table
    hiddenPrompt.style.display = "flex";
    tableContainer.style.display = "none";
  } else {
    // Files exist, hide the hidden prompt and show the table
    hiddenPrompt.style.display = "none";
    tableContainer.style.display = "block";
  }
}

// Fetch files from the server and display them
async function fetchFiles() {
  try {
    const response = await fetch("/files/list");
    const data = await response.json();

    if (response.ok) {
      const fileTableBody = document.querySelector("#file-list tbody");
      fileTableBody.innerHTML = ""; // Clear the current table body

      // Use a Set to track already displayed files (optional safeguard)
      const displayedFiles = new Set();

      // Loop through each file and create a table row
      data.files.forEach((file) => {
        if (displayedFiles.has(file.name)) return; // Skip duplicates
        displayedFiles.add(file.name);

        const row = document.createElement("tr");

        // File name column
        const nameCell = document.createElement("td");
        nameCell.textContent = file.name;

        // File size column
        const sizeCell = document.createElement("td");
        sizeCell.textContent = formatFileSize(file.size);

        // File type column
        const typeCell = document.createElement("td");
        typeCell.textContent = file.type;

        // Last modified column
        const modifiedCell = document.createElement("td");
        modifiedCell.textContent = file.last_modified;

        // Action column (Download, Delete)
        const actionCell = document.createElement("td");

        // Download icon
        const downloadIcon = document.createElement("img");
        downloadIcon.src = "/static/icons/download.png";
        downloadIcon.alt = "Download";
        downloadIcon.classList.add("action-icon");
        downloadIcon.onclick = () => downloadFile(file.name);
        actionCell.appendChild(downloadIcon);

        // Delete icon
        const deleteIcon = document.createElement("img");
        deleteIcon.src = "/static/icons/delete.png";
        deleteIcon.alt = "Delete";
        deleteIcon.classList.add("action-icon");
        deleteIcon.onclick = () => deleteFile(file.name);
        actionCell.appendChild(deleteIcon);

        // Append all columns to the row
        row.appendChild(nameCell);
        row.appendChild(sizeCell);
        row.appendChild(typeCell);
        row.appendChild(modifiedCell);
        row.appendChild(actionCell);

        // Add the row to the table
        fileTableBody.appendChild(row);
      });

      // Reapply the current sorting criteria
      const currentSortBy = document.getElementById("sort-options").value;
      sortFiles(currentSortBy);

      toggleFilePrompt();
    } else {
      showToast("Failed to load files.");
    }
  } catch (error) {
    showToast("Error fetching files: " + error);
  }
}

// Function to download a file (UPDATED: safer method without iframe)
async function downloadFile(fileName) {
  try {
    showToast("Preparing download...", "info");

    // 1. Get the authenticated download URL from Flask
    const response = await fetch(
      `/files/download/${encodeURIComponent(fileName)}`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || "Failed to prepare download");
    }

    const { download_url, filename } = await response.json();

    // 2. Create an anchor element to trigger download
    const link = document.createElement("a");
    link.href = download_url;
    link.download = filename;
    link.style.display = "none"; // Hide the link

    document.body.appendChild(link);
    link.click(); // Trigger the download
    document.body.removeChild(link); // Cleanup

    showToast("Download started!", "success");
  } catch (error) {
    console.error("Download error:", error);
    showToast(`Download failed: ${error.message}`, "error");
  }
}

// Function to delete a file
async function deleteFile(fileName) {
  const confirmed = confirm("Are you sure you want to delete this file?");
  if (!confirmed) return;

  try {
    const response = await fetch(`/files/delete/${fileName}`, {
      method: "DELETE",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (response.ok) {
      showToast("File deleted successfully!", "success");
      fetchFiles(); // Refresh the file list
    } else {
      const errorData = await response.json();
      console.error("Delete error:", errorData);
      showToast("Failed to delete the file.", "error");
    }
  } catch (error) {
    console.error("Delete error:", error);
    showToast("Error deleting file: " + error, "error");
  }
}

// Helper function to parse file size for sorting
function parseFileSize(sizeStr) {
  const units = {
    Bytes: 1,
    KB: 1024,
    MB: 1024 ** 2,
    GB: 1024 ** 3,
    TB: 1024 ** 4,
  };

  const match = sizeStr.match(/^([\d.]+)\s*(Bytes|KB|MB|GB|TB)$/i);
  if (!match) return 0;
  const [_, value, unit] = match;
  return parseFloat(value) * units[unit.toUpperCase()];
}

// Function to sort files based on selected option
function sortFiles(sortBy) {
  const fileTableBody = document.querySelector("#file-list tbody");
  const rows = Array.from(fileTableBody.querySelectorAll("tr"));

  rows.sort((a, b) => {
    let valueA, valueB;

    switch (sortBy) {
      case "name":
        valueA = a.children[0].textContent.toLowerCase();
        valueB = b.children[0].textContent.toLowerCase();
        return valueA.localeCompare(valueB);

      case "size":
        valueA = parseFileSize(a.children[1].textContent);
        valueB = parseFileSize(b.children[1].textContent);
        return valueB - valueA; // Sort from largest to smallest

      case "type":
        valueA = a.children[2].textContent.toLowerCase();
        valueB = b.children[2].textContent.toLowerCase();
        return valueA.localeCompare(valueB);

      case "date":
        const dateA = a.children[3].textContent.trim();
        const dateB = b.children[3].textContent.trim();
        valueA = new Date(dateA.replace(" ", "T"));
        valueB = new Date(dateB.replace(" ", "T"));
        if (isNaN(valueA.getTime())) valueA = new Date(0);
        if (isNaN(valueB.getTime())) valueB = new Date(0);
        return valueB - valueA; // Sort from most recent to oldest
      default:
        return 0;
    }
  });

  fileTableBody.innerHTML = "";
  rows.forEach((row) => fileTableBody.appendChild(row));
}

// Utility function to format file size
function formatFileSize(bytes) {
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  if (bytes === 0) return "0 Bytes";
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + " " + sizes[i];
}

// Add event listener for sorting files
const sortSelect = document.getElementById("sort-options");
sortSelect.addEventListener("change", function () {
  const selectedSort = sortSelect.value;
  sortFiles(selectedSort);
});

// Call fetchFiles when the page loads
document.addEventListener("DOMContentLoaded", () => {
  fetchFiles();
});
