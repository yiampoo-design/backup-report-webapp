const form = document.getElementById("loginForm");
const button = document.getElementById("loginButton");
const error = document.getElementById("loginError");

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.textContent = "";
  button.disabled = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "เข้าสู่ระบบไม่สำเร็จ");
    location.replace("/");
  } catch (exc) {
    error.textContent = exc.message;
    document.getElementById("password").select();
  } finally {
    button.disabled = false;
  }
});
