/* Auth screens: landing -> signup -> OTP -> app, plus login / forgot / reset.
   Kept separate from app.js so the discovery SPA stays untouched.
   These render into the shared `view` element defined in app.js, which loads
   first -- do not re-declare it here. */

const A = {
  mode: "landing",      // landing | login | signup | otp | forgot | reset
  email: "",
  name: "",
  emailSent: null,      // whether the last OTP actually went out
  busy: false,
};

function shell(inner, opts = {}) {
  return `
  <div class="mx-auto flex min-h-[78vh] max-w-5xl items-center justify-center px-2 py-8">
    <div class="w-full ${opts.wide ? "max-w-4xl" : "max-w-md"}">
      ${opts.back ? `<button data-amode="landing" class="mb-4 text-xs text-slate-400 hover:text-violet-300">← Back to home</button>` : ""}
      ${inner}
    </div>
  </div>`;
}

const field = (label, name, type = "text", ph = "", extra = "") => `
  <label class="block text-sm">${label}
    <input name="${name}" type="${type}" placeholder="${ph}" ${extra}
      class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 outline-none focus:border-violet-500" />
  </label>`;

function alertBox(msg, tone = "error") {
  const toneCls = tone === "ok"
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
    : "border-rose-500/40 bg-rose-500/10 text-rose-300";
  return `<div class="mb-3 rounded-lg border px-3 py-2 text-xs ${toneCls}">${msg}</div>`;
}

/* ---------------------------------------------------------------- landing */
function renderLanding() {
  view.innerHTML = `
  <div class="overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-b from-violet-950/40 to-slate-950">
    <div class="px-6 py-14 text-center sm:px-12">
      <div class="text-5xl">🎓</div>
      <h1 class="mt-4 bg-gradient-to-r from-violet-300 via-cyan-200 to-emerald-300 bg-clip-text text-4xl font-black tracking-tight text-transparent sm:text-5xl">
        OpportunityHub
      </h1>
      <p class="mx-auto mt-4 max-w-2xl text-slate-300">
        Internships, hackathons, scholarships, courses and competitions — all in one place,
        ranked by how well they fit <b>you</b>, with the reasoning shown.
      </p>
      <p class="mt-2 text-sm text-slate-500">
        Built solo for FITFEST 2026 · Flora Institute of Technology, Pune
      </p>

      <div class="mt-8 flex flex-wrap justify-center gap-3">
        <button data-amode="signup" class="rounded-xl bg-violet-600 px-6 py-3 font-semibold hover:bg-violet-500">
          Get started free
        </button>
        <button data-amode="login" class="rounded-xl border border-slate-700 px-6 py-3 font-semibold hover:border-violet-500">
          Log in
        </button>
      </div>

      <p class="mt-6 text-xs text-slate-500">
        Free forever · No card required · 66 verified listings
      </p>
    </div>

    <div class="grid gap-4 border-t border-slate-800 px-6 py-8 sm:grid-cols-2 lg:grid-cols-4 sm:px-12">
      ${[
        ["🎯", "Match scoring", "A percentage on every listing, plus the exact skills and interests that produced it."],
        ["📊", "Skill-gap analysis", "See which missing skills would unlock the most open opportunities."],
        ["⏰", "Deadline tracking", "Countdowns, closing-soon filters, and a dashboard of what's due next."],
        ["🔎", "One search", "7 categories, remote/onsite filters and full-text search across everything."],
      ].map(([i, t, d]) => `
        <div>
          <div class="text-2xl">${i}</div>
          <h3 class="mt-1 font-semibold">${t}</h3>
          <p class="mt-1 text-xs text-slate-400">${d}</p>
        </div>`).join("")}
    </div>

    <div class="border-t border-slate-800 px-6 py-4 text-center sm:px-12">
      <p class="text-xs text-slate-500">66 verified listings · Google Cloud Run · Firestore / MongoDB</p>
    </div>
  </div>`;
}

/* ------------------------------------------------------------------ login */
function renderLogin() {
  view.innerHTML = shell(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
      <h2 class="text-xl font-bold">Welcome back</h2>
      <p class="mt-1 text-sm text-slate-400">Log in to your OpportunityHub account.</p>
      <form id="loginForm" class="mt-5 space-y-3">
        ${field("Email", "email", "email", "you@college.edu")}
        ${field("Password", "password", "password", "••••••••")}
        <div class="flex justify-end">
          <button type="button" data-amode="forgot" class="text-xs text-violet-300 hover:underline">Forgot password?</button>
        </div>
        <button class="w-full rounded-lg bg-violet-600 py-2.5 font-semibold hover:bg-violet-500">Log in</button>
      </form>
      <p class="mt-4 text-center text-sm text-slate-400">
        No account? <button data-amode="signup" class="text-violet-300 hover:underline">Sign up</button>
      </p>
    </div>`, { back: true });
}

/* ----------------------------------------------------------------- signup */
function renderSignup() {
  view.innerHTML = shell(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
      <h2 class="text-xl font-bold">Create your account</h2>
      <p class="mt-1 text-sm text-slate-400">We'll email you a 6-digit code to verify your address.</p>
      <form id="signupForm" class="mt-5 space-y-3">
        ${field("Full name", "name", "text", "Aarav Sharma")}
        ${field("College email", "email", "email", "you@college.edu", "required")}
        ${field("Password", "password", "password", "At least 8 characters", "required minlength=\"8\"")}
        <button class="w-full rounded-lg bg-violet-600 py-2.5 font-semibold hover:bg-violet-500">Create account</button>
      </form>
      <p class="mt-4 text-center text-sm text-slate-400">
        Already registered? <button data-amode="login" class="text-violet-300 hover:underline">Log in</button>
      </p>
    </div>`, { back: true });
}

/* -------------------------------------------------------------------- OTP */
function renderOtp() {
  // The code is never rendered here. If delivery failed, say so plainly rather
  // than leaking the OTP into the page, devtools or a screen share.
  const failed = A.emailSent === false;
  view.innerHTML = shell(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
      <h2 class="text-xl font-bold">Verify your email</h2>
      <p class="mt-1 text-sm text-slate-400">
        We sent a 6-digit code to <b class="text-slate-200">${esc(A.email)}</b>.
        It expires in 10 minutes.
      </p>
      ${failed ? alertBox(
        "⚠ We could not send the email. Check the server logs for the code, and verify the SMTP settings in .env."
      ) : ""}
      <form id="otpForm" class="mt-5 space-y-3">
        <input name="code" inputmode="numeric" maxlength="6" required autofocus
          placeholder="000000"
          class="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-center text-2xl tracking-[0.4em] outline-none focus:border-violet-500" />
        <button class="w-full rounded-lg bg-violet-600 py-2.5 font-semibold hover:bg-violet-500">Verify and continue</button>
      </form>
      <div class="mt-3 flex justify-between text-xs">
        <button id="resend" class="text-slate-400 hover:text-violet-300">Resend code</button>
        <button data-amode="signup" class="text-slate-400 hover:text-violet-300">Use a different email</button>
      </div>
    </div>`, { back: true });
}
/* ----------------------------------------------------------------- forgot */
function renderForgot() {
  view.innerHTML = shell(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
      <h2 class="text-xl font-bold">Reset your password</h2>
      <p class="mt-1 text-sm text-slate-400">Enter your email and we'll send a reset link.</p>
      <form id="forgotForm" class="mt-5 space-y-3">
        ${field("Email", "email", "email", "you@college.edu")}
        <button class="w-full rounded-lg bg-violet-600 py-2.5 font-semibold hover:bg-violet-500">Send reset link</button>
      </form>
      <p class="mt-4 text-center text-sm text-slate-400">
        <button data-amode="login" class="text-violet-300 hover:underline">Back to log in</button>
      </p>
    </div>`, { back: true });
}

/* ------------------------------------------------------------------ reset */
function renderReset(token) {
  view.innerHTML = shell(`
    <div class="rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
      <h2 class="text-xl font-bold">Choose a new password</h2>
      <form id="resetForm" class="mt-5 space-y-3">
        ${field("New password", "password", "password", "At least 8 characters", "required minlength=\"8\"")}
        <button class="w-full rounded-lg bg-violet-600 py-2.5 font-semibold hover:bg-violet-500">Update password</button>
      </form>
      <p class="mt-4 text-center text-sm text-slate-400">
        <button data-amode="login" class="text-violet-300 hover:underline">Back to log in</button>
      </p>
    </div>`);
  $("#resetForm").dataset.token = token || "";
}

/* ----------------------------------------------------------------- router */
function paintAuth() {
  const map = {
    landing: renderLanding,
    login: renderLogin,
    signup: renderSignup,
    otp: renderOtp,
    forgot: renderForgot,
  };
  (map[A.mode] || renderLanding)();
}

function setMode(mode) {
  A.mode = mode;
  paintAuth();
}

document.addEventListener("click", async (e) => {
  const t = e.target;

  const modeBtn = t.closest("[data-amode]");
  if (modeBtn) { setMode(modeBtn.dataset.amode); return; }

  if (t.closest("#resend")) {
    try {
      const r = await api("/auth/resend-otp", {
        method: "POST",
        body: JSON.stringify({ email: A.email }),
      });
      A.emailSent = r.emailSent;
      toast(r.emailSent ? "A new code is on its way." : "Could not send the email. Check the server logs.", r.emailSent ? "ok" : "error");
    } catch (err) { toast(err.message); }
    return;
  }
});

document.addEventListener("submit", async (e) => {
  const form = e.target;
  const fd = new FormData(form);

  if (form.id === "loginForm") {
    e.preventDefault();
    try {
      const r = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
      });
      await enterApp(r);
    } catch (err) { toast(err.message); }
  }

  if (form.id === "signupForm") {
    e.preventDefault();
    try {
      const r = await api("/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"), email: fd.get("email"), password: fd.get("password"),
        }),
      });
      A.email = r.email;
      A.name = fd.get("name");
      A.emailSent = r.emailSent;
      setMode("otp");
    } catch (err) { toast(err.message); }
  }

  if (form.id === "otpForm") {
    e.preventDefault();
    try {
      const r = await api("/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({ email: A.email, code: fd.get("code") }),
      });
      await enterApp(r);
    } catch (err) { toast(err.message); }
  }

  if (form.id === "forgotForm") {
    e.preventDefault();
    const email = fd.get("email");
    try {
      const r = await api("/auth/forgot", { method: "POST", body: JSON.stringify({ email }) });
      if (r.emailSent) {
        toast("If that email is registered, a reset link is on its way.", "ok");
        setMode("login");
      } else {
        toast("Could not send the reset email. Check the server logs.", "error");
      }
    } catch (err) { toast(err.message); }
  }

  if (form.id === "resetForm") {
    e.preventDefault();
    try {
      await api("/auth/reset", {
        method: "POST",
        body: JSON.stringify({ token: form.dataset.token, password: fd.get("password") }),
      });
      toast("Password updated. Please log in.", "ok");
      setMode("login");
    } catch (err) { toast(err.message); }
  }
});
