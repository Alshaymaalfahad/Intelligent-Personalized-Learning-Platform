const OTHER = "__other__";
const MAX_INTERESTS = 6;

const els = {
  form: document.getElementById("profile-form"),
  spec: document.getElementById("specialization"),
  customSpec: document.getElementById("custom-specialization"),
  interestsField: document.getElementById("interests-field"),
  interestsHint: document.getElementById("interests-hint"),
  interestsList: document.getElementById("interests-list"),
  customBox: document.getElementById("custom-interest-box"),
  customInput: document.getElementById("custom-interest-input"),
  customAdd: document.getElementById("custom-interest-add"),
  customList: document.getElementById("custom-interest-list"),
  message: document.getElementById("additional-message"),
  messageCount: document.getElementById("message-count"),
  submit: document.getElementById("submit-btn"),
  specError: document.getElementById("specialization-error"),
  interestsError: document.getElementById("interests-error"),
  formError: document.getElementById("form-error"),
};

let catalog = [];
let currentProfile = null;
let customInterests = []; // areas the trainee typed in

function show(el, visible) {
  el.classList.toggle("hidden", !visible);
}

function clearErrors() {
  [els.specError, els.interestsError, els.formError].forEach((e) => (e.textContent = ""));
}

function selectedSpec() {
  return catalog.find((s) => s.name === els.spec.value);
}

/* ---------- Loading the catalog ---------- */

async function loadCatalog() {
  try {
    const res = await fetch("/api/specializations");
    if (!res.ok) throw new Error(res.status);
    catalog = await res.json();
  } catch {
    els.formError.textContent = "تعذّر تحميل قائمة التخصصات. تأكد من تشغيل الخادم ثم أعد تحميل الصفحة.";
    return;
  }
  for (const s of catalog) els.spec.add(new Option(s.label_ar, s.name));
  els.spec.add(new Option("تخصص آخر", OTHER));
}

/* ---------- Specialization → interests ---------- */

function renderInterests() {
  els.interestsList.replaceChildren();
  const isOther = els.spec.value === OTHER;
  const spec = selectedSpec();

  show(els.customSpec, isOther);
  els.interestsField.disabled = !spec && !isOther;

  if (isOther) {
    els.interestsHint.textContent = `أضف حتى ${MAX_INTERESTS} مجالات تهتم بها.`;
    els.customSpec.focus();
  } else if (!spec) {
    els.interestsHint.textContent = "اختر التخصص أولًا لعرض المجالات.";
  } else {
    els.interestsHint.textContent = `اختر مجالًا أو أكثر، أو أضف مجالاتك (${MAX_INTERESTS} كحد أقصى).`;
    for (const interest of spec.interests) {
      const label = document.createElement("label");
      label.className = "chip";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = interest.name;
      label.append(box, document.createTextNode(interest.label_ar));
      els.interestsList.append(label);
    }
  }
  renderCustomInterests();
}

function renderCustomInterests() {
  els.customList.replaceChildren(
    ...customInterests.map((name) => {
      const chip = document.createElement("span");
      chip.className = "chip chip-custom";
      chip.append(document.createTextNode(name));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "chip-remove";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `حذف ${name}`);
      remove.addEventListener("click", () => {
        customInterests = customInterests.filter((n) => n !== name);
        renderCustomInterests();
      });
      chip.append(remove);
      return chip;
    }),
  );
}

function addCustomInterest() {
  els.interestsError.textContent = "";
  const name = els.customInput.value.trim();
  if (!name) return;
  if (name.length > 60) {
    els.interestsError.textContent = "اسم المجال طويل جدًا (60 حرفًا كحد أقصى).";
    return;
  }
  const all = collectInterests().map((i) => i.toLowerCase());
  const spec = selectedSpec();
  const labels = spec ? spec.interests.flatMap((i) => [i.name.toLowerCase(), i.label_ar]) : [];
  if (all.includes(name.toLowerCase()) || labels.includes(name.toLowerCase()) || labels.includes(name)) {
    els.interestsError.textContent = "هذا المجال موجود بالفعل.";
    return;
  }
  if (all.length >= MAX_INTERESTS) {
    els.interestsError.textContent = `يمكنك اختيار ${MAX_INTERESTS} مجالات كحد أقصى.`;
    return;
  }
  customInterests.push(name);
  els.customInput.value = "";
  renderCustomInterests();
  els.customInput.focus();
}

function collectInterests() {
  const checked = [...els.interestsList.querySelectorAll("input:checked")].map((b) => b.value);
  return [...checked, ...customInterests];
}

/* ---------- Validation & submit ---------- */

function validate() {
  clearErrors();
  let ok = true;

  const specialization = els.spec.value === OTHER ? els.customSpec.value.trim() : els.spec.value;
  if (!specialization || specialization.length < 2) {
    els.specError.textContent = els.spec.value === OTHER ? "اكتب اسم التخصص (حرفان على الأقل)." : "اختر تخصصك.";
    ok = false;
  }

  const interests = collectInterests();
  if (interests.length === 0) {
    els.interestsError.textContent = "اختر مجالًا واحدًا على الأقل.";
    ok = false;
  } else if (interests.length > MAX_INTERESTS) {
    els.interestsError.textContent = `يمكنك اختيار ${MAX_INTERESTS} مجالات كحد أقصى.`;
    ok = false;
  } else if (interests.some((i) => i.length > 60)) {
    els.interestsError.textContent = "اسم المجال طويل جدًا (60 حرفًا كحد أقصى).";
    ok = false;
  }

  return ok ? { specialization, interests, additional_message: els.message.value.trim() || null } : null;
}

async function submitProfile(e) {
  e.preventDefault();
  const payload = validate();
  if (!payload) return;

  els.submit.disabled = true;
  els.submit.textContent = "جارٍ الحفظ…";
  try {
    const res = await fetch("/api/trainees", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 422) {
      els.formError.textContent = "البيانات المدخلة غير صالحة، راجعها ثم حاول مرة أخرى.";
      return;
    }
    if (!res.ok) throw new Error(res.status);
    const profile = await res.json();
    try {
      localStorage.setItem("trainee_id", profile.trainee_id);
    } catch {
      /* storage unavailable — the ID is still shown on screen */
    }
    showResult(profile);
  } catch {
    els.formError.textContent = "تعذّر حفظ الملف. تأكد من تشغيل الخادم ثم حاول مرة أخرى.";
  } finally {
    els.submit.disabled = false;
    els.submit.textContent = "حفظ الملف";
  }
}

/* ---------- Result ---------- */

function labelFor(specName, interestName) {
  const spec = catalog.find((s) => s.name === specName);
  if (!interestName) return spec ? spec.label_ar : specName;
  const interest = spec?.interests.find((i) => i.name === interestName);
  return interest ? interest.label_ar : interestName;
}

function showResult(profile) {
  currentProfile = profile;
  document.getElementById("r-id").textContent = profile.trainee_id;
  document.getElementById("r-spec").textContent = labelFor(profile.specialization);
  document.getElementById("r-interests").textContent = profile.interests
    .map((i) => labelFor(profile.specialization, i))
    .join("، ");
  document.getElementById("r-message").textContent = profile.additional_message || "—";
  document.getElementById("r-status").textContent = profile.profile_status === "completed" ? "مكتمل" : profile.profile_status;
  show(document.getElementById("form-section"), false);
  show(document.getElementById("result-section"), true);
}

async function loadExistingProfile(id) {
  try {
    const res = await fetch(`/api/trainees/${encodeURIComponent(id)}`);
    if (res.status === 404) {
      els.formError.textContent = `لا يوجد ملف بالرقم ${id}.`;
      return;
    }
    if (!res.ok) throw new Error(res.status);
    showResult(await res.json());
  } catch {
    els.formError.textContent = "تعذّر استرجاع الملف. تأكد من تشغيل الخادم.";
  }
}

/* ---------- Start assessment ---------- */

async function startAssessment() {
  const btn = document.getElementById("start-btn");
  const error = document.getElementById("start-error");
  error.textContent = "";
  btn.disabled = true;
  try {
    const res = await fetch("/api/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trainee_id: currentProfile.trainee_id }),
    });
    if (!res.ok) throw new Error(res.status);
    const assessment = await res.json();
    location.href = `assessment.html?id=${encodeURIComponent(assessment.assessment_id)}`;
  } catch {
    error.textContent = "تعذّر بدء التقييم. تأكد من تشغيل الخادم ثم حاول مرة أخرى.";
    btn.disabled = false;
  }
}

/* ---------- Init ---------- */

els.spec.addEventListener("change", () => {
  clearErrors();
  renderInterests();
});
els.message.addEventListener("input", () => {
  els.messageCount.textContent = els.message.value.length;
});
els.form.addEventListener("submit", submitProfile);
els.customAdd.addEventListener("click", addCustomInterest);
els.customInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault(); // Enter adds the area instead of submitting the form
    addCustomInterest();
  }
});
document.getElementById("start-btn").addEventListener("click", startAssessment);

(async () => {
  await loadCatalog();
  const id = new URLSearchParams(location.search).get("id");
  if (id) loadExistingProfile(id);
})();
