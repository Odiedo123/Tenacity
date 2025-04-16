document.addEventListener("DOMContentLoaded", function () {
  function updateBarWidths(data) {
    function setBarWidth(barSelector, value, maxValue) {
      const minPercent = 2;
      const maxPercent = 80;
      const width = Math.max(
        minPercent,
        Math.min(
          maxPercent,
          (value / maxValue) * (maxPercent - minPercent) + minPercent
        )
      );
      document.querySelector(barSelector).style.width = `${width}%`;
    }

    const maxValue = Math.max(data.documents, data.images, data.others);

    setBarWidth("#bar-1", data.documents, maxValue);
    setBarWidth("#bar-2", data.images, maxValue);
    setBarWidth("#bar-3", data.others, maxValue);
  }

  // Function to animate counting
  function animateCount(target, value, duration) {
    let current = parseFloat(document.querySelector(target).textContent) || 0;
    const increment = (value - current) / (duration / 16);
    const element = document.querySelector(target);

    function step() {
      current += increment;
      if (
        (increment > 0 && current >= value) ||
        (increment < 0 && current <= value)
      ) {
        element.textContent = value.toFixed(2);
      } else {
        element.textContent = current.toFixed(2);
        requestAnimationFrame(step);
      }
    }
    step();
  }

  /// Function to fetch storage data from backend
  async function fetchStorageData() {
    try {
      const response = await fetch("/api/storage");
      if (response.ok) {
        const data = await response.json();

        // Optionally animate counts for other stats (files, documents, etc.)
        animateCount(
          "#right > div:nth-child(1) > h3 > span",
          Math.floor(data.files),
          1000
        );

        animateCount(
          "#right > div:nth-child(2) > h3 > span",
          data.documents,
          1000
        );
        animateCount(
          "#right > div:nth-child(3) > h3 > span",
          data.images,
          1000
        );
        animateCount(
          "#right > div:nth-child(4) > h3 > span",
          data.others,
          1000
        );
        updateBarWidths(data);
        updatePercentage(data.usedStorage, data.totalStorage);

        // Update the total storage span with the used storage in GB
        document.querySelector(
          "#total-storage"
        ).textContent = `${data.usedStorage.toFixed(2)}`;
      } else {
        console.error("Failed to fetch storage data");
      }
    } catch (error) {
      console.error("Error fetching storage data:", error);
    }
  }

  // Initial fetch to populate storage data
  fetchStorageData();

  async function updateTotalStorage() {
    try {
      // Make an API call to fetch the file list
      const response = await fetch("/files/list");
      const data = await response.json();

      if (response.ok) {
        // Calculate the total storage size in bytes
        let totalSizeBytes = 0;
        data.files.forEach((file) => {
          totalSizeBytes += file.size;
        });

        // Convert the total size to gigabytes (GB)
        const totalSizeGB = (totalSizeBytes / 1024 ** 3).toFixed(1);

        // Update the element with the total storage size
        const totalStorageElement = document.querySelector("#total-storage");
        totalStorageElement.textContent = `${totalSizeGB}GB`;
      } else {
        console.error("Failed to load files");
      }
    } catch (error) {
      console.error("Error fetching file list:", error);
    }
  }
});

// Function to update the total storage span
// Function to calculate and update the percentage
function updatePercentage(usedStorage, totalStorage) {
  const percentageElement = document.querySelector("#percentage");
  if (window.innerWidth < 764) {
    percentageElement.style.fontSize = "1.8em";
  } else {
    percentageElement.style.fontSize = "2.5em";
  }

  // Calculate the percentage
  const percentage = 100 - (usedStorage / totalStorage) * 1000;
  percentageElement.textContent = `${percentage.toFixed(2)}%`;

  //Adding search functionality
  const searchInput = document.getElementById("fade-in-1");
  if (searchInput) {
    searchInput.addEventListener("keypress", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const searchQuery = encodeURIComponent(searchInput.value.trim());
        if (searchQuery) {
          window.location.href = `/files?q=${searchQuery}`;
        }
      }
    });
  }
}

updatePercentage(usedStorage, totalStorage);

// Call the function when the page loads
document.addEventListener("DOMContentLoaded", updateTotalStorage);
