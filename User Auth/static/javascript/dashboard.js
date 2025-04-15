// Show toast messages
function showToast(message, type = "info") {
  const toastContainer = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3500);
}

// Function to check if the table has any files and update visibility
function toggleFilePrompt() {
  const fileTableBody = document.querySelector("#file-list tbody");
  const hiddenPrompt = document.getElementById("hidden-prompt");
  const tableContainer = document.querySelector(".table-container");
  if (fileTableBody.rows.length === 0) {
    hiddenPrompt.style.display = "flex";
    tableContainer.style.display = "none";
  } else {
    hiddenPrompt.style.display = "none";
    tableContainer.style.display = "block";
  }
}

// Fetch files from the server and display them
async function fetchFiles() {
  try {
    const response = await fetch("/files/list");
    if (!response.ok) throw new Error("Failed to load files.");
    const data = await response.json();
    const fileTableBody = document.querySelector("#file-list tbody");
    const sortBy = document.getElementById("sort-options").value;
    const fragment = document.createDocumentFragment();
    const displayedFiles = new Set();

    // Pre-compile static elements for action icons
    const createActionIcons = (fileName) => {
      const actionCell = document.createElement("td");

      const downloadIcon = new Image();
      downloadIcon.src = "/static/icons/download.png";
      downloadIcon.alt = "Download";
      downloadIcon.classList.add("action-icon");
      downloadIcon.onclick = () => downloadFile(fileName);
      actionCell.appendChild(downloadIcon);

      const deleteIcon = new Image();
      deleteIcon.src = "/static/icons/delete.png";
      deleteIcon.alt = "Delete";
      deleteIcon.classList.add("action-icon");
      deleteIcon.onclick = () => deleteFile(fileName);
      actionCell.appendChild(deleteIcon);

      return actionCell;
    };

    for (const file of data.files) {
      if (displayedFiles.has(file.name)) continue;
      displayedFiles.add(file.name);
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${file.name}</td>
        <td>${formatFileSize(file.size)}</td>
        <td>${file.type}</td>
        <td>${file.last_modified}</td>
      `;
      row.appendChild(createActionIcons(file.name));
      fragment.appendChild(row);
    }

    fileTableBody.innerHTML = "";
    fileTableBody.appendChild(fragment);
    sortFiles(sortBy);
    toggleFilePrompt();
  } catch (error) {
    showToast("Error fetching files: " + error.message);
  }
}

// Function to download a file
async function downloadFile(fileName) {
  try {
    showToast("Preparing download...", "info");
    const response = await fetch(
      `/files/download/${encodeURIComponent(fileName)}`,
      {
        credentials: "include",
      }
    );
    if (!response.ok) throw new Error("Failed to download file");
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${fileName}.zip`;
    document.body.appendChild(link);
    link.click();
    URL.revokeObjectURL(link.href);
    document.body.removeChild(link);
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
      fetchFiles(); // Refresh file list
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

// Helper to parse file size for sorting
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
        return valueB - valueA; // Largest to smallest
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
        return valueB - valueA; // Most recent to oldest
      default:
        return 0;
    }
  });
  fileTableBody.innerHTML = "";
  rows.forEach((row) => fileTableBody.appendChild(row));
}

// Utility to format file size
function formatFileSize(bytes) {
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  if (bytes === 0) return "0 Bytes";
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + " " + sizes[i];
}

// Function to filter file list based on search query
function filterFileList(query) {
  const tableBody = document.querySelector("#file-list tbody");
  const rows = Array.from(tableBody.querySelectorAll("tr"));
  rows.forEach((row) => {
    const fileNameCell = row.querySelector("td:first-child");
    if (!fileNameCell) return;
    const fileName = fileNameCell.textContent.trim().toLowerCase();
    row.style.display = fileName.includes(query) ? "" : "none";
  });
}

// On page load
document.addEventListener("DOMContentLoaded", async () => {
  // First, fetch and render all files
  await fetchFiles();

  // Check if a search query is present in the URL
  const params = new URLSearchParams(window.location.search);
  const query = params.get("query");
  if (query) {
    filterFileList(query.trim().toLowerCase());
  }

  // Also, add an event listener to the separate search element
  const searchInput = document.querySelector("input.fade-in-1");
  if (searchInput) {
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const searchQuery = searchInput.value.trim();
        if (searchQuery) {
          // Redirect so that the URL reflects the search query; the files page code will auto-filter on load
          window.location.href = `/files?query=${encodeURIComponent(
            searchQuery
          )}`;
        }
      }
    });
  }
});

// A separate call for updating total storage (if used elsewhere)
document.addEventListener("DOMContentLoaded", () => {
  updateTotalStorage();
});

// Function to update percentage if needed
function updatePercentage(usedStorage, totalStorage) {
  const percentageElement = document.querySelector("#percentage");
  if (window.innerWidth < 764) {
    percentageElement.style.fontSize = "1.8em";
  } else {
    percentageElement.style.fontSize = "2.5em";
  }
  const percentage = 100 - (usedStorage / totalStorage) * 1000;
  percentageElement.textContent = `${percentage.toFixed(2)}%`;
}

// Example: Update total storage (assumed to be defined elsewhere)
async function updateTotalStorage() {
  try {
    const response = await fetch("/files/list");
    const data = await response.json();
    if (response.ok) {
      let totalSizeBytes = 0;
      data.files.forEach((file) => {
        totalSizeBytes += file.size;
      });
      const totalSizeGB = (totalSizeBytes / 1024 ** 3).toFixed(1);
      const totalStorageElement = document.querySelector("#total-storage");
      totalStorageElement.textContent = `${totalSizeGB}GB`;
    } else {
      console.error("Failed to load files");
    }
  } catch (error) {
    console.error("Error fetching file list:", error);
  }
}
