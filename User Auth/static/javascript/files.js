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
      { credentials: "include" }
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
      fetchFiles();
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
        return valueB - valueA;

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
        return valueB - valueA;

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

// Function to filter files based on search query
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
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("fade-in-1");

  // Apply search from query string if available
  const urlParams = new URLSearchParams(window.location.search);
  const query = urlParams.get("q");
  if (query) {
    if (searchInput) searchInput.value = query;
  }

  fetchFiles().then(() => {
    if (query) {
      filterFileList(query.toLowerCase());
    }
  });

  if (searchInput) {
    searchInput.addEventListener("keypress", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const searchQuery = searchInput.value.trim().toLowerCase();
        filterFileList(searchQuery);
      }
    });
  }
});
