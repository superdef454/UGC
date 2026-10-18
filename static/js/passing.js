// Одиночный выбор: radio нельзя снять штатно, поэтому повторный клик снимает отметку,
// а свой ответ и вариант взаимоисключают друг друга - как и проверяет сервер.
(() => {
  const form = document.querySelector("form.question");
  if (!form) return;

  const radios = [...form.querySelectorAll("input[type=radio][name=option]")];
  const custom = form.querySelector("textarea[name=custom_text]");
  if (!radios.length) return;

  // Состояние до клика: к моменту события click браузер уже отметил radio.
  const remember = () => radios.forEach((r) => (r.dataset.wasChecked = r.checked ? "1" : ""));
  remember();

  radios.forEach((radio) => {
    radio.addEventListener("click", () => {
      if (radio.dataset.wasChecked) radio.checked = false;
      if (radio.checked && custom) custom.value = "";
      remember();
    });
  });

  custom?.addEventListener("input", () => {
    if (!custom.value.trim()) return;
    radios.forEach((r) => (r.checked = false));
    remember();
  });
})();
