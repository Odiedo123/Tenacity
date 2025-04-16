document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.querySelector(".fade-in-1");
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
});
