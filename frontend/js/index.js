document.getElementById("lookup-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = document.getElementById("lookup-id").value.trim().toUpperCase();
  if (!id) return;
  location.href = id.startsWith("AS-")
    ? `report.html?id=${encodeURIComponent(id)}`
    : `profile.html?id=${encodeURIComponent(id)}`;
});

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    if (!h.ai_configured) document.getElementById("ai-warning").classList.remove("hidden");
  })
  .catch(() => {});
