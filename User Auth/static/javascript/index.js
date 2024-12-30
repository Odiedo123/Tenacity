document.addEventListener("DOMContentLoaded", () => {
  const video = document.getElementById("video"); // No need for "#" here

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("fade-in-1"); // No "." here
          observer.unobserve(entry.target); // Stop observing once visible
        }
      });
    },
    { threshold: 0.1 }
  );

  observer.observe(video);
});
