/* Education Platform Lite · 泪见雪. */
"use strict";

document.querySelectorAll("[data-open]").forEach((button) => {
  button.addEventListener("click", () =>
    document.getElementById(button.dataset.open).showModal(),
  );
});
document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
document.querySelectorAll("[data-back]").forEach((button) => {
  button.addEventListener("click", () => window.history.back());
});

function bindSubjectTeacher(container) {
  const subject = container.querySelector(".subject-select");
  const teacher = container.querySelector(".teacher-select");
  if (!subject || !teacher) return;
  const taught = (option) =>
    (option.dataset.subjects || "").split(",").filter(Boolean);
  const filterTeachers = () => {
    Array.from(teacher.options).forEach((option) => {
      if (!option.value) return;
      option.hidden =
        Boolean(subject.value) && !taught(option).includes(subject.value);
      option.disabled = option.hidden;
    });
    if (teacher.selectedOptions[0]?.disabled) teacher.value = "";
  };
  subject.addEventListener("change", filterTeachers);
  teacher.addEventListener("change", () => {
    const choices = taught(teacher.selectedOptions[0]);
    Array.from(subject.options).forEach((option) => {
      option.disabled = Boolean(
        teacher.value && option.value && !choices.includes(option.value),
      );
    });
    if (teacher.value && choices.length === 1) subject.value = choices[0];
    else if (teacher.value && !choices.includes(subject.value))
      subject.value = "";
    filterTeachers();
  });
  filterTeachers();
}

const lessonForm = document.querySelector('form:has(input[name="starts_at"])');
if (lessonForm) bindSubjectTeacher(lessonForm);
const trialList = document.getElementById("trial-list");
if (trialList) {
  // Keep a pristine template so new rows never inherit earlier filter state.
  const template = trialList.firstElementChild.cloneNode(true);
  const bindTrial = (row) => {
    bindSubjectTeacher(row);
    row
      .querySelector("[data-remove-trial]")
      .addEventListener("click", () => row.remove());
  };
  trialList.querySelectorAll(".trial-form").forEach(bindTrial);
  document.getElementById("add-trial").addEventListener("click", () => {
    if (trialList.children.length >= 20) {
      window.alert("一次最多添加 20 节试听课。");
      return;
    }
    const row = template.cloneNode(true);
    trialList.appendChild(row);
    bindTrial(row);
  });
}

const role = document.getElementById("person-role");
if (role) {
  const refresh = () =>
    document.querySelectorAll("[data-role]").forEach((section) => {
      const hidden = section.dataset.role !== role.value;
      section.hidden = hidden;
      section.querySelectorAll("input,select,textarea").forEach((input) => {
        input.disabled = hidden;
      });
    });
  role.addEventListener("change", refresh);
  refresh();
}
