const status = document.querySelector("#copy-status");
const dialog = document.querySelector("#copy-dialog");
const fallback = document.querySelector("#copy-text");

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = label + " copied.";
  } catch {
    fallback.value = text;
    dialog.showModal();
    fallback.focus();
    fallback.select();
  }
}

if (status && dialog && fallback) {
  dialog.addEventListener("close", () => { fallback.value = ""; });
  document.querySelector("[data-copy-url]").addEventListener("click", () => {
    copyText(document.querySelector("#mcp-url").textContent, "MCP URL");
  });
  for (const button of document.querySelectorAll("[data-client]")) {
    button.addEventListener("click", async () => {
      button.disabled = true;
      status.textContent = "";
      try {
        const response = await fetch("/dashboard/connect/copy", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ client: button.dataset.client }),
        });
        if (!response.ok) throw new Error("Copy request failed");
        const result = await response.json();
        await copyText(result.text, button.dataset.client === "token" ? "Bearer token" : "Configuration");
      } catch {
        status.textContent = "Could not copy the connection details. Reload and try again.";
      } finally {
        button.disabled = false;
      }
    });
  }
}
