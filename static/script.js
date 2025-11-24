// Updated API endpoint to be relative.
// This will work on "localhost" and on your deployed "render.com" address.
const api = "/recommend";

const statusEl = document.getElementById("status");
const tbody = document.querySelector("#results tbody");

document.getElementById("btn").onclick = async () => {
  const q = document.getElementById("query").value.trim();
  const k = parseInt(document.getElementById("topk").value) || 7;

  // Replaced alert() with a status message
  if (!q) {
    statusEl.innerText = "Please enter a query in the text box.";
    statusEl.style.color = "red";
    return;
  }

  // Reset status and clear old results
  statusEl.style.color = "black";
  statusEl.innerText = "Searching...";
  tbody.innerHTML = "";

  try {
    const res = await fetch(api, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, top_k: k }),
    });

    if (!res.ok) {
      // Handle server errors
      const errData = await res.json();
      throw new Error(errData.error || `Server responded with ${res.status}`);
    }

    const data = await res.json();
    statusEl.innerText = `Results for: ${data.query}`;

    if (data.recommendations.length === 0) {
        statusEl.innerText = `No results found for: ${data.query}`;
    }

    data.recommendations.forEach((r, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${i + 1}</td>
        <td><a href="${r.canonical_url}" target="_blank">${
        r.assessment_name
      }</a></td>
        <td>${r.test_type}</td>
        <td>${r.skills_tags}</td>
        <td>${r.score.toFixed(3)}</td>`;
      tbody.appendChild(tr);
    });
  } catch (err) {
    // Show fetch or server errors to the user
    console.error("Fetch error:", err);
    statusEl.innerText = `Error: ${err.message}. Check console for details.`;
    statusEl.style.color = "red";
  }
};